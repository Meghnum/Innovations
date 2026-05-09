import re

# Only validate numbers that look like financial/statistical claims:
# - $1,234.56 / $1234 / $1,234
# - 12.5% / -7%
# - 1,234,567 (with comma separators)
# Skip bare integers (years, ordinals, counts).
NUMBER_RX = re.compile(
    r"-?\$\d{1,3}(?:,\d{3})*(?:\.\d+)?"  # $1,234.56 or $1234
    r"|-?\d+(?:\.\d+)?%"                  # 12.5% or -7%
    r"|-?\d{1,3}(?:,\d{3})+(?:\.\d+)?"    # 1,234,567 (must have at least one comma)
)
TOLERANCE = 0.0001  # 0.01%
SSN_RX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
EMAIL_RX = re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b")


def _normalize_number(s: str) -> float | None:
    s = s.replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def _matches_kv(claim: float, kv_values: list) -> bool:
    for v in kv_values:
        if v == 0:
            if abs(claim) < 0.01:
                return True
            continue
        # also accept absolute value match (e.g. "Down 7%" referencing -7.0)
        if abs(claim - v) / abs(v) < TOLERANCE:
            return True
        if abs(v) != 0 and abs(abs(claim) - abs(v)) / abs(v) < TOLERANCE:
            return True
    return False


def validate_narrative(narrative: dict, kv: dict, pii_columns: list | None = None) -> dict:
    mismatches = []
    text = " ".join(str(narrative.get(k, "")) for k in ("observe", "analyze"))
    kv_values = [float(v) for v in kv.values() if isinstance(v, (int, float))]
    for raw in NUMBER_RX.findall(text):
        n = _normalize_number(raw)
        if n is None:
            continue
        if not _matches_kv(n, kv_values):
            mismatches.append(f"fabricated number: {raw}")

    # PII guards: scan all narrative tiers
    full_text = " ".join(str(narrative.get(k, "")) for k in ("observe", "analyze", "synthesize"))
    if pii_columns:
        for col in pii_columns:
            pattern = r"\b" + re.escape(col) + r"\b"
            if re.search(pattern, full_text, re.IGNORECASE):
                mismatches.append(f"PII column reference: {col}")
    if SSN_RX.search(full_text):
        mismatches.append("PII: SSN pattern in narrative")
    if EMAIL_RX.search(full_text):
        mismatches.append("PII: email pattern in narrative")

    return {"valid": len(mismatches) == 0, "mismatches": mismatches}


PROMPT_TEMPLATE = """You are an executive presentation analyst. Generate a 3-tier narrative for this slide.

SLIDE TITLE: {title}
AUDIENCE: {audience}

DATA FACTS (use ONLY these values; do not invent numbers):
{facts}

Produce exactly three statements following the Observe → Analyze → Synthesize chain:

1. OBSERVE: State the most important raw fact from the DATA FACTS (single sentence, include the literal number).
2. ANALYZE: State the comparative or trend context (single sentence, include the literal number for any delta or comparison).
3. SYNTHESIZE: State the business implication — the "So What?" (single sentence, no new numbers).

Constraints:
- Every numeric claim in OBSERVE and ANALYZE must appear verbatim in DATA FACTS above (rounding to nearest whole percent or dollar is allowed).
- Total ≤ 6 bullet points across the three tiers.
- Synthesize must be actionable for the AUDIENCE.
- Output as JSON: {{"observe": "...", "analyze": "...", "synthesize": "..."}}
"""


def build_prompt(kv: dict, slide_ctx: dict) -> str:
    facts_lines = [f"- {k}: {v}" for k, v in kv.items()]
    facts = "\n".join(facts_lines)
    return PROMPT_TEMPLATE.format(
        title=slide_ctx.get("title", "Untitled"),
        audience=slide_ctx.get("audience", "general"),
        facts=facts,
    )
