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
