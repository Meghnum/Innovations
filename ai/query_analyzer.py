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

OLLAMA_MODEL: str = _AI.get("ollama_model", "llama3.2:3b")
OLLAMA_HOST: str = _AI.get("ollama_host", "http://localhost:11434")
QUERY_ANALYZER_TIMEOUT: int = _AI.get("query_analyzer_timeout", 8)

# ---------------------------------------------------------------------------
# Valid value sets
# ---------------------------------------------------------------------------
VALID_INTENTS = {"aggregation", "lookup", "search", "trend", "comparison", "unknown"}

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

# ===========================================================================
# Column Synonym Dictionary — injected into LLM prompt as a cheat sheet
# ===========================================================================
COLUMN_SYNONYMS = {
    # Identifiers
    "Claim Number": ["claim id", "reference number", "file number", "case number"],
    "Policy Number": ["policy id", "contract number", "binder number"],
    "MAR Fast Track Flag": ["fast track", "stp", "straight-through", "auto-approved"],

    # Dates
    "Event Date": ["dol", "date of loss", "accident date", "incident date", "occurrence date"],
    "Reported Date": ["date reported", "notification date", "fnol", "submission date"],
    "Claim Closed Date": ["closed date", "settlement date", "resolution date"],
    "Claim Life Days": ["days open", "claim age", "duration", "time to close"],
    "Policy UWY": ["uwy", "underwriting year", "policy year"],
    "Accident Year": ["ay", "loss year"],

    # People/Entities
    "Responsible Adjuster": ["adjuster", "handler", "examiner", "case manager", "claim owner"],
    "Policy Holder Name": ["insured", "client", "policyholder", "customer"],
    "Producer Name": ["broker", "agent", "intermediary"],
    "Claim Office": ["branch", "handling office"],

    # Financials
    "Indemnity Paid USD": ["payout", "settlement", "loss paid", "damages paid", "indemnity"],
    "Expense Paid USD": ["legal fees", "defense costs", "alae", "expert fees"],
    "Outstanding Reserve USD": ["reserves", "outstanding", "case reserve", "current reserve"],
    "Recoveries USD": ["subro", "subrogation", "salvage", "recovery"],
    "Incurred USD": ["total incurred", "gross incurred", "total cost"],
    "Company Share": ["net share", "our share", "retention", "line size"],

    # Categories
    "Major LOB": ["lob", "line of business", "class of business", "product line"],
    "Cause Of Loss Descr": ["peril", "cause", "reason for loss", "incident type"],
    "Condition Injury Damage Name": ["injury", "damage type", "diagnosis", "medical condition"],
    "Catastrophe Description": ["cat", "catastrophe", "natural disaster", "named storm"],
    "Loss Description": ["narrative", "loss details", "adjuster notes", "description"],
    "Location of Loss": ["accident site", "venue", "loss location"],
}

# Build reverse lookup: synonym → official column name (longest first)
_SYN_TO_COL = {}
for _col_name, _syns in COLUMN_SYNONYMS.items():
    for _s in sorted(_syns, key=len, reverse=True):
        _SYN_TO_COL[_s.lower()] = _col_name

# Format dictionary into readable string for LLM prompt injection
MAPPING_RULES = "\n".join(
    f'- Official Name "{k}": matches words like {", ".join(v)}'
    for k, v in COLUMN_SYNONYMS.items()
)

# ---------------------------------------------------------------------------
# LLM prompt — with synonym cheat sheet injected
# ---------------------------------------------------------------------------
ANALYSIS_PROMPT = """\
You are a claims-data assistant. Classify the user question and extract entities.

COLUMN SYNONYM MAPPING CHEAT SHEET:
{mapping_rules}

CRITICAL RULES FOR EXTRACTION:
- ONLY extract a region/country if the user EXPLICITLY types the name of the country in their prompt.
- NEVER assume "US" or "United States" by default. If no country is mentioned, region MUST be null.
- ONLY extract a status if explicitly mentioned. Otherwise, status MUST be null.
- Read the user's question. If they use any slang or terms found in the "CHEAT SHEET" above, you MUST map it to the Official Name and add it to the `columns_mentioned` array.
- If the user's question is completely unrelated to insurance claims, policies, reserves, financials, or data analysis (e.g., asking for a recipe, writing code, general chat, sports, weather), you MUST set the intent to "unknown".

Return ONLY a JSON object (no markdown, no explanation) with these keys:
- intent: one of {intents}
- claim_id: string like "CLM12345" or null
- status: one of {statuses} or null
- region: one of {regions} or null
- claim_type: one of {types} or null
- date_range: object with "start" and "end" ISO dates, or null
- high_value: boolean (true if asking about large / high-value claims)
- columns_mentioned: [Array of string Official Names identified in the question]

User question: {{question}}
""".format(
    mapping_rules=MAPPING_RULES,
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
# Complexity guardrail — decides when an aggregation query needs the Pandas Agent
# ---------------------------------------------------------------------------
# Philosophy: deterministic handlers own 80% of queries (fast, exact).
# Escalate ONLY for patterns the heuristic genuinely cannot compute:
#   - Derived numeric metrics (reporting lag in days)
#   - Ratios / percentage-of-total
#   - 3+ predicate WHERE clauses (status AND reserve>X AND paid=0)
# Deliberately NOT triggering on: "distribution", "split", "vs", "by",
# "between", "unique", "bottom" — those are now covered by Tier 1 handlers.

_DERIVED_METRIC_PHRASES = [
    "reporting lag", "reporting delay", "report delay",
    "cycle time", "cycle-time", "days to close", "days open",
    "time to settle", "settlement time", "time to close",
]

_RATIO_PHRASES = [
    "percentage of", "percent of", "% of", " pct of",
    "ratio of", "share of", "proportion of",
    "what percent", "what percentage", "what % ",
    "what fraction",
]

# Regex for 3+ filter predicates. Two patterns:
#   a) (where|with) … and … and …          — explicit conjunctions
#   b) (where|with) … <cmp> … (but|and) no/not  — mixed conjunction with
#      a comparison plus a negation (typical "pending AND x>50k AND paid=0"
#      phrasing users write as "where x>50k but no y paid yet").
_MULTI_PREDICATE_RE = re.compile(
    r"\b(where|with)\b.*\band\b.*\band\b",
    re.IGNORECASE | re.DOTALL,
)
_MIXED_PREDICATE_RE = re.compile(
    r"\b(where|with)\b.*(greater than|less than|more than|over|under|above|below|>|<)"
    r".*\b(but|and)\b\s+(no|not|zero|none)\b",
    re.IGNORECASE | re.DOTALL,
)

# Regex for "took more than N days" / "took over N days" — relative time filters
_RELATIVE_TIME_RE = re.compile(
    r"\b(took|takes|taking)\s+(more than|over|greater than|at least)\s+\d+\s+days?\b",
    re.IGNORECASE,
)

# Regex for set-exclusion like "excluding the Casualty and Auto LOBs" /
# "except the X and Y" / "other than A, B". Heuristic handlers don't support
# multi-value NOT-IN, so escalate.
_EXCLUSION_RE = re.compile(
    r"\b(excluding|except(?:\s+for)?|other than|not\s+in|aside from)\b.*\b(and|,|or)\b",
    re.IGNORECASE | re.DOTALL,
)

# Regex for disjunction: "either A or B", "A or B" when paired with 2+
# comparison/status predicates. Triggers on "either…or" unambiguously;
# otherwise requires an explicit "or" joining two comparison-ish phrases.
_DISJUNCTION_EITHER_RE = re.compile(
    r"\beither\b.*\bor\b",
    re.IGNORECASE | re.DOTALL,
)
_DISJUNCTION_PREDICATE_RE = re.compile(
    r"\b(closed|open|pending|reopened|paid|unpaid|reserve|indemnity|expense|incurred)\b"
    r".*\bor\b.*"
    r"\b(closed|open|pending|reopened|paid|unpaid|reserve|indemnity|expense|incurred)\b",
    re.IGNORECASE | re.DOTALL,
)

# Date-type ambiguity — query references a year/quarter/month WITHOUT saying
# whether it means Reported Date or Event Date. Must escalate so the Pandas
# Agent can ask a CLARIFY question instead of the heuristic silently
# returning the total count.
_YEAR_RE    = re.compile(r"\b(19|20)\d{2}\b")
_QUARTER_RE = re.compile(r"\bq[1-4]\b|\b(first|second|third|fourth)\s+quarter\b", re.IGNORECASE)
_MONTH_RE   = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
    re.IGNORECASE,
)
# Anything that disambiguates which date column the user means.
_DATE_TYPE_SPECIFIED_RE = re.compile(
    r"\b(reported|report(?:ing)?\s+date|event\s+date|date\s+of\s+loss|dol|fnol|"
    r"notified|notification|received|inflow|new\s+claims?|submitted|"
    r"accident\s+year|report\s+year|underwriting\s+year|uwy|"
    r"closed(?:\s+date)?|settlement\s+date)\b",
    re.IGNORECASE,
)


def assess_query_complexity(query: str) -> tuple:
    """Decide whether an aggregation query needs the Pandas Agent instead of
    the heuristic handler.

    Returns:
        (should_escalate: bool, reason: str)
    """
    q = (query or "").lower().strip()
    if not q:
        return False, ""

    # 1. Derived numeric metrics (need date math)
    for phrase in _DERIVED_METRIC_PHRASES:
        if phrase in q:
            return True, f"derived-metric: '{phrase}'"

    # 2. Ratios / percentage-of-total
    for phrase in _RATIO_PHRASES:
        if phrase in q:
            return True, f"ratio: '{phrase.strip()}'"

    # 3. Relative-time filter (e.g., "took more than 30 days between event and reported")
    if _RELATIVE_TIME_RE.search(q):
        return True, "relative-time filter"

    # 4. Triple-predicate WHERE clause (explicit "and…and")
    if _MULTI_PREDICATE_RE.search(q):
        return True, "3+ filter predicates"

    # 5. Mixed predicate (e.g. "where reserve > 50k but no indemnity paid")
    if _MIXED_PREDICATE_RE.search(q):
        return True, "3+ filter predicates"

    # 6. Set exclusion: "excluding the Casualty and Auto LOBs" — heuristic
    #    handler can only filter-include one LOB at a time.
    if _EXCLUSION_RE.search(q):
        return True, "set-exclusion (excluding/except/not-in)"

    # 7. Disjunction: "either Closed with no Paid OR Open with over 100k".
    #    Heuristic handler AND-combines all entities, so OR logic must escalate.
    if _DISJUNCTION_EITHER_RE.search(q):
        return True, "disjunction: 'either…or'"
    if _DISJUNCTION_PREDICATE_RE.search(q):
        return True, "disjunction: OR across status/amount predicates"

    # 8. Any year/quarter/month filter — heuristic aggregation handler ignores
    #    date_range entirely and returns total_claims, so we always route these
    #    to the Pandas Agent. If no Reported/Event disambiguator is present,
    #    the agent will CLARIFY; otherwise it filters on the specified column.
    if _YEAR_RE.search(q) or _QUARTER_RE.search(q) or _MONTH_RE.search(q):
        if _DATE_TYPE_SPECIFIED_RE.search(q):
            return True, "date filter (year/quarter/month with reported/event disambiguator)"
        return True, "date-type ambiguity (year/quarter/month w/o Reported vs Event)"

    # 9. Currency & ledger differentiation — the heuristic aggregation handler
    #    only knows the *_USD columns. When the user asks for ledger / local /
    #    converted currency we must escalate so the agent uses *_Ledger columns.
    ledger_keywords = ("ledger", "local currency", "local",
                       "exchange", "converted", "reporting currency")
    if any(kw in q for kw in ledger_keywords):
        return True, "currency/ledger differentiation (user asked for Ledger/Local, not USD)"

    return False, ""


# ---------------------------------------------------------------------------
# QueryAnalyzer
# ---------------------------------------------------------------------------
class QueryAnalyzer:
    """Classify a natural-language question into intent + entities."""

    # ── public API ────────────────────────────────────────────────────────

    def analyze(self, question: str) -> Dict[str, Any]:
        """Return an analysis dict.  LLM first, keyword fallback on error.

        If LLM returns 'search' but keyword detector finds aggregation
        keywords, override to 'aggregation' (LLM often misclassifies
        complex financial queries).
        """
        try:
            llm_result = self._llm_analyze(question)
        except Exception:
            return self._keyword_fallback(question)

        # Cross-check LLM result with keyword fallback
        kw_result = self._keyword_fallback(question)

        # If LLM said "search" but keywords detect aggregation or lookup
        if llm_result.get("intent") == "search":
            if kw_result["intent"] == "aggregation":
                llm_result["intent"] = "aggregation"
            elif kw_result["intent"] == "lookup":
                llm_result["intent"] = "lookup"
                if kw_result.get("claim_id"):
                    llm_result["claim_id"] = kw_result["claim_id"]
                if kw_result.get("policy_id"):
                    llm_result["policy_id"] = kw_result["policy_id"]

        # If LLM said "lookup" but there's no claim_id/policy_id, and keywords
        # detect aggregation, override (e.g. "what are the different UWY?")
        if llm_result.get("intent") == "lookup":
            if not llm_result.get("claim_id") and not llm_result.get("policy_id"):
                if kw_result["intent"] == "aggregation":
                    llm_result["intent"] = "aggregation"

        return llm_result

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
        # Helper: LLMs often return the string "null" instead of actual null
        def _clean_null(val):
            if val is None:
                return None
            if isinstance(val, str) and val.strip().lower() in ("null", "none", "n/a", ""):
                return None
            return val

        result: Dict[str, Any] = {
            "intent": parsed.get("intent"),
            "claim_id": _clean_null(parsed.get("claim_id")),
            "status": _clean_null(parsed.get("status")),
            "region": _clean_null(parsed.get("region")),
            "claim_type": _clean_null(parsed.get("claim_type")),
            "date_range": _clean_null(parsed.get("date_range")),
            "high_value": bool(parsed.get("high_value")),
            "columns_mentioned": parsed.get("columns_mentioned", []),
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

        # --- out-of-scope detection ---
        # If question has zero insurance/claims/data keywords, flag as unknown
        _domain_words = [
            "claim", "claims", "policy", "policies", "reserve", "reserves",
            "incurred", "paid", "loss", "losses",
            "adjuster", "handler", "examiner", "indemnity", "expense",
            "recovery", "recoveries", "subro", "subrogation",
            "lob", "line of business", "insured", "policyholder",
            "premium", "coverage", "underwriting", "uwy",
            "status", "open", "closed", "pending", "rejected",
            "region", "country", "broker", "producer",
            "breakdown", "how many", "how much",
            "fast track", "stp", "catastrophe", "peril",
            "cause of loss", "clm", "pol-",
            "accident", "event date", "settlement", "payout",
            "alae", "defense cost", "salvage", "deductible",
            "reinsurance", "retention", "exposure", "portfolio",
        ]
        if not any(dw in q_lower for dw in _domain_words):
            return {
                "intent": "unknown",
                "claim_id": None,
                "policy_id": None,
                "status": None,
                "region": None,
                "claim_type": None,
                "date_range": None,
                "high_value": False,
                "columns_mentioned": [],
            }

        # --- intent ---
        intent = "search"  # default

        aggregation_kw = [
            "how many", "how much", "total", "count", "sum", "average",
            "number of", "breakdown", "by status", "by region", "by type",
            "top", "biggest", "largest", "highest", "lowest",
            "bottom", "least", "fewest", "smallest", "worst",
            "recoveries", "incurred", "indemnity", "reserve", "expense",
            "exposure", "net position", "gross", "what is our",
            "what are the different", "what are the distinct", "what are the unique",
            "what are different", "what are distinct", "what are unique",
            "what different", "what distinct",
            "list all", "list the", "show me all", "show all", "show me",
            "which regions", "which countries", "which statuses", "which types",
            "which lob", "which uwy", "which year",
        ]
        trend_kw = ["trend", "over time", "month over month", "year over year"]
        comparison_kw = ["compare", "comparison", "versus", "vs"]

        # Claim-id lookup
        claim_id_match = re.search(r"(CLM[\-]?[\d]+[\-A-Za-z\d]*)", question, re.IGNORECASE)
        # Policy number lookup (POL-xxx pattern, requires hyphen or digit after POL)
        policy_id_match = re.search(r'\b(POL\-[A-Za-z0-9][\-A-Za-z0-9]*)\b', question, re.IGNORECASE)

        if claim_id_match or policy_id_match:
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
        # Note: "major" only triggers high-value when NOT part of "major lob" / "major line"
        high_value = bool(
            re.search(r"high.?value|large|big|expensive", q_lower)
        ) or bool(
            re.search(r"\bmajor\b(?!\s+(lob|line))", q_lower)
        )

        # Policy ID
        policy_id: Optional[str] = (
            policy_id_match.group(1).upper() if policy_id_match else None
        )

        # Column synonym detection (deterministic fallback)
        # Short synonyms (<=3 chars) use word boundary to avoid false positives
        columns_mentioned = []
        for syn, official in _SYN_TO_COL.items():
            if len(syn) <= 3:
                if re.search(r'\b' + re.escape(syn) + r'\b', q_lower) and official not in columns_mentioned:
                    columns_mentioned.append(official)
            else:
                if syn in q_lower and official not in columns_mentioned:
                    columns_mentioned.append(official)

        return {
            "intent": intent,
            "claim_id": claim_id,
            "policy_id": policy_id,
            "status": status,
            "region": region,
            "claim_type": claim_type,
            "date_range": None,
            "high_value": high_value,
            "columns_mentioned": columns_mentioned,
        }
