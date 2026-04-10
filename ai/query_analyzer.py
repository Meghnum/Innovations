"""QueryAnalyzer — LLM-based intent classification and entity extraction.

Tries a fast structured LLM call first (Ollama). If that fails or times out,
falls back to deterministic keyword matching.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import yaml

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------
_CFG_PATH = "config/config.yaml"

def _load_config() -> dict:
    try:
        with open(_CFG_PATH, "r") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}

_CFG = _load_config()
_AI = _CFG.get("ai", {})

OLLAMA_MODEL: str = _AI.get("ollama_model", "gemma3:4b")
OLLAMA_HOST: str = _AI.get("ollama_host", "http://localhost:11434")
QUERY_ANALYZER_TIMEOUT: int = _AI.get("query_analyzer_timeout", 8)

# ---------------------------------------------------------------------------
# Valid value sets
# ---------------------------------------------------------------------------
VALID_INTENTS = {"aggregation", "lookup", "search", "trend", "comparison"}

VALID_STATUSES = {"Open", "Closed", "Pending", "Rejected", "Under Review"}

VALID_REGIONS = {
    "US", "UK", "Canada", "Australia", "Germany", "France",
    "Japan", "India", "Brazil", "Mexico", "Spain", "Italy",
    "Netherlands", "Singapore", "Hong Kong",
}

VALID_TYPES = {
    "Property Damage", "Bodily Injury", "General Liability",
    "Professional Liability", "Workers Compensation",
    "Auto Liability", "Product Liability", "Marine",
    "Medical Malpractice", "Cyber Liability",
}

# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------
ANALYSIS_PROMPT = """\
You are a claims-data assistant. Classify the user question and extract entities.

Return ONLY a JSON object (no markdown, no explanation) with these keys:
- intent: one of {intents}
- claim_id: string like "CLM12345" or null
- status: one of {statuses} or null
- region: one of {regions} or null
- claim_type: one of {types} or null
- date_range: object with "start" and "end" ISO dates, or null
- high_value: boolean (true if asking about large / high-value claims)

User question: {{question}}
""".format(
    intents=", ".join(sorted(VALID_INTENTS)),
    statuses=", ".join(sorted(VALID_STATUSES)),
    regions=", ".join(sorted(VALID_REGIONS)),
    types=", ".join(sorted(VALID_TYPES)),
)

# ---------------------------------------------------------------------------
# Lazy-loaded ollama reference (set on first LLM call)
# ---------------------------------------------------------------------------
ollama: Any = None  # module-level placeholder for mocking / lazy import


def _ensure_ollama() -> None:
    """Import ollama on first use so startup stays fast."""
    global ollama
    if ollama is None:
        import ollama as _ollama  # type: ignore
        ollama = _ollama


# ---------------------------------------------------------------------------
# QueryAnalyzer
# ---------------------------------------------------------------------------
class QueryAnalyzer:
    """Classify a natural-language question into intent + entities."""

    # ── public API ────────────────────────────────────────────────────────

    def analyze(self, question: str) -> Dict[str, Any]:
        """Return an analysis dict.  LLM first, keyword fallback on error."""
        try:
            return self._llm_analyze(question)
        except Exception:
            return self._keyword_fallback(question)

    # ── LLM path ─────────────────────────────────────────────────────────

    def _llm_analyze(self, question: str) -> Dict[str, Any]:
        _ensure_ollama()

        prompt = ANALYSIS_PROMPT.replace("{question}", question)

        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )

        raw: str = response["message"]["content"]

        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            # Remove opening fence (```json or ```)
            raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
            # Remove closing fence
            raw = re.sub(r"\n?```\s*$", "", raw)

        parsed = json.loads(raw)
        return self._validate(parsed)

    # ── validation / normalisation ────────────────────────────────────────

    def _validate(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise and fill missing keys."""
        result: Dict[str, Any] = {
            "intent": parsed.get("intent"),
            "claim_id": parsed.get("claim_id"),
            "status": parsed.get("status"),
            "region": parsed.get("region"),
            "claim_type": parsed.get("claim_type"),
            "date_range": parsed.get("date_range"),
            "high_value": bool(parsed.get("high_value")),
        }

        # Validate intent
        if result["intent"] not in VALID_INTENTS:
            result["intent"] = "search"

        # Validate status
        if result["status"] and result["status"] not in VALID_STATUSES:
            # Try case-insensitive match
            for s in VALID_STATUSES:
                if s.lower() == str(result["status"]).lower():
                    result["status"] = s
                    break
            else:
                result["status"] = None

        # Validate region
        if result["region"] and result["region"] not in VALID_REGIONS:
            for r in VALID_REGIONS:
                if r.lower() == str(result["region"]).lower():
                    result["region"] = r
                    break
            else:
                result["region"] = None

        return result

    # ── keyword fallback ─────────────────────────────────────────────────

    def _keyword_fallback(self, question: str) -> Dict[str, Any]:
        """Deterministic keyword-based classification."""
        q_lower = question.lower()

        # --- intent ---
        intent = "search"  # default

        aggregation_kw = [
            "how many", "total", "count", "sum", "average", "number of",
        ]
        trend_kw = ["trend", "over time", "month over month", "year over year"]
        comparison_kw = ["compare", "comparison", "versus", "vs"]

        # Claim-id lookup
        claim_id_match = re.search(r"(CLM\d+)", question, re.IGNORECASE)

        if claim_id_match:
            intent = "lookup"
        elif any(kw in q_lower for kw in aggregation_kw):
            intent = "aggregation"
        elif any(kw in q_lower for kw in trend_kw):
            intent = "trend"
        elif any(kw in q_lower for kw in comparison_kw):
            intent = "comparison"

        # --- entities ---
        claim_id: Optional[str] = (
            claim_id_match.group(1).upper() if claim_id_match else None
        )

        # Status extraction
        status: Optional[str] = None
        for s in VALID_STATUSES:
            if s.lower() in q_lower:
                status = s
                break

        # Region extraction
        region: Optional[str] = None
        for r in VALID_REGIONS:
            # Use word boundary to avoid partial matches
            if re.search(r"\b" + re.escape(r) + r"\b", question, re.IGNORECASE):
                region = r
                break

        # Claim type extraction
        claim_type: Optional[str] = None
        for ct in VALID_TYPES:
            if ct.lower() in q_lower:
                claim_type = ct
                break

        # High-value flag
        high_value = bool(
            re.search(r"high.?value|large|big|expensive|major", q_lower)
        )

        return {
            "intent": intent,
            "claim_id": claim_id,
            "status": status,
            "region": region,
            "claim_type": claim_type,
            "date_range": None,
            "high_value": high_value,
        }
