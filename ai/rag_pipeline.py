# =============================================================================
# ai/rag_pipeline.py
# RAG Pipeline with QueryAnalyzer-based intent routing
# =============================================================================
# Flow:
#   QueryAnalyzer.analyze(question)
#     -> route by intent: aggregation | lookup | search
#   Aggregation -> handle_aggregation (summary stats, entity-aware)
#   Lookup      -> handle_lookup (direct DataFrame row by claim_id)
#   Search      -> pre-filter by entities -> FAISS -> score threshold -> LLM
# =============================================================================

import logging
import re
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from ai.query_analyzer import QueryAnalyzer

logger = logging.getLogger("claims.rag")


# ---------------------------------------------------------------------------
# Column Synonyms — maps real column names to user-friendly aliases
# ---------------------------------------------------------------------------
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
    "Minor LOB": ["minor lob", "minor line"],
    "Executive LOB": ["executive lob"],
    "Cause Of Loss Descr": ["peril", "cause of loss", "reason for loss", "incident type"],
    "Condition Injury Damage Name": ["injury", "damage type", "diagnosis", "medical condition"],
    "Catastrophe Description": ["cat event", "catastrophe", "natural disaster", "named storm"],
    "Loss Description": ["narrative", "loss details", "adjuster notes", "loss description"],
    "Location of Loss": ["accident site", "venue", "loss location"],
    "Country": ["region", "country", "geography"],
    "Business Entity": ["entity", "business entity", "subsidiary"],
    "Claim Status Derived": ["status", "claim status"],
}

# Build reverse lookup: synonym → actual column name (longest synonyms first)
_SYNONYM_TO_COLUMN = {}
for _col_name, _synonyms in COLUMN_SYNONYMS.items():
    for _syn in sorted(_synonyms, key=len, reverse=True):
        _SYNONYM_TO_COLUMN[_syn.lower()] = _col_name


def resolve_column_synonym(query_lower: str, df_columns: set = None) -> dict:
    """Find all column synonyms mentioned in the query.

    Returns dict of {actual_column_name: matched_synonym}.
    Only returns columns that exist in df_columns (if provided).
    """
    found = {}
    for syn, col_name in _SYNONYM_TO_COLUMN.items():
        if syn in query_lower:
            if df_columns is None or col_name in df_columns:
                if col_name not in found:
                    found[col_name] = syn
    return found


def resolve_groupby_column(query_lower: str, df, col: dict) -> tuple:
    """Detect which column the user wants to group by using synonyms.

    Returns (actual_col_name, display_label) or (None, None).
    """
    # Check synonym matches in query, sorted by synonym length desc (longest match wins)
    matches = resolve_column_synonym(query_lower, set(df.columns) if df is not None else None)

    # Prioritise "by X" patterns
    by_match = re.search(r'\bby\s+(.+?)(?:\s+for\b|\s+in\b|\s+where\b|\?|$)', query_lower)
    if by_match:
        by_phrase = by_match.group(1).strip()
        for syn, col_name in _SYNONYM_TO_COLUMN.items():
            if syn in by_phrase:
                if df is not None and col_name in df.columns:
                    return col_name, col_name
    return None, None


# ---------------------------------------------------------------------------
# Zero-results guard — explains WHY a query returned 0 rows
# ---------------------------------------------------------------------------
def _zero_results_message(entities: dict, question: str = "") -> str:
    """Build a helpful message when filters produce 0 matching claims."""
    active_filters = []
    if entities.get("status"):
        active_filters.append(f"Status = **{entities['status']}**")
    if entities.get("region"):
        active_filters.append(f"Region = **{entities['region']}**")
    if entities.get("claim_type"):
        active_filters.append(f"Claim Type = **{entities['claim_type']}**")
    if entities.get("high_value"):
        active_filters.append("High-value claims only")
    if entities.get("date_range"):
        dr = entities["date_range"]
        if isinstance(dr, dict):
            active_filters.append(f"Date range = {dr.get('start', '?')} to {dr.get('end', '?')}")

    # Detect date/year keywords from the question itself
    q = question.lower()
    year_match = re.search(r'\b(20\d{2})\b', q)
    if year_match:
        active_filters.append(f"Year = **{year_match.group(1)}**")
    for phrase in ["this year", "last year", "last quarter", "ytd"]:
        if phrase in q:
            active_filters.append(f"Time period = **{phrase}**")
            break

    filter_str = "\n".join(f"- {f}" for f in active_filters) if active_filters else "- *(no explicit filters detected)*"

    return (
        f"I found **0 claims** matching your exact criteria.\n\n"
        f"**Active filters:**\n{filter_str}\n\n"
        f"This usually means the combination of filters doesn't overlap in the data. "
        f"Try relaxing one filter (e.g., remove the date or change the region)."
    )


# ---------------------------------------------------------------------------
# Aggregation handler
# ---------------------------------------------------------------------------

def handle_aggregation(
    question: str,
    summary: dict,
    df: pd.DataFrame = None,
    col: dict = None,
    entities: dict = None,
) -> str:
    """Answer aggregation questions from summary stats or DataFrame group-bys.

    Uses *entities* (from QueryAnalyzer) for entity-aware filtering when a
    specific status, region, or type is mentioned.

    Args:
        question:  User question.
        summary:   Pre-computed summary from ClaimsDataLoader.
        df:        Full DataFrame (optional, needed for group-by).
        col:       Column mapping dict.
        entities:  Dict with keys status/region/claim_type/high_value from
                   QueryAnalyzer (may be None).

    Returns:
        Formatted answer string using $ for currency.
    """
    q = question.lower()
    ent = entities or {}

    # Side-channel flags populated by _apply_filters so outer handlers can
    # produce user-friendly messages (e.g., "LOB not found").
    _filter_flags: Dict[str, Any] = {}

    # Helper: word-boundary check to avoid substring matches like
    # "count" inside "countries".
    def _has_word(word: str) -> bool:
        return bool(re.search(rf'\b{re.escape(word)}\b', q))

    # -----------------------------------------------------------------------
    # Helper: pre-filter DataFrame based on entities + keyword patterns.
    # Returns a filtered copy of df (or df unchanged if no filters apply).
    # Safe to call when df or col is None (returns df as-is).
    # -----------------------------------------------------------------------
    def _apply_filters(dframe: pd.DataFrame) -> pd.DataFrame:
        if dframe is None or col is None:
            return dframe

        mask = pd.Series(True, index=dframe.index)
        filtered = False

        # --- Status filter ---
        status_col = col.get("status", "Claim Status Derived")
        if status_col in dframe.columns:
            status_val = ent.get("status")
            if not status_val:
                for kw in ["open", "closed", "pending", "rejected", "under review"]:
                    if _has_word(kw):
                        status_val = kw.title()
                        break
            if status_val:
                mask &= dframe[status_col].str.lower() == status_val.lower()
                filtered = True

        # --- Region / Country filter ---
        # Alias map: short names → possible full names (tried in order)
        _region_aliases = {
            "uk": ["United Kingdom", "UK"],
            "us": ["USA", "US", "United States"],
            "usa": ["USA", "US", "United States"],
            "uae": ["United Arab Emirates", "UAE"],
            "sa": ["South Africa", "SA"],
        }
        region_col = col.get("region", "Country")
        if region_col in dframe.columns:
            actual_regions = set(dframe[region_col].dropna().unique())
            actual_lower = {r.lower(): r for r in actual_regions}

            region_val = ent.get("region")
            if not region_val:
                for kw in ["uk", "us", "usa", "uae", "sa", "canada", "australia",
                           "germany", "france", "japan", "brazil", "india",
                           "netherlands", "italy", "spain", "switzerland",
                           "ireland", "south africa"]:
                    if _has_word(kw):
                        region_val = kw
                        break

            if region_val:
                rv_lower = region_val.lower()
                resolved = None
                # Try alias list first
                for alias_key, candidates in _region_aliases.items():
                    if rv_lower == alias_key:
                        for candidate in candidates:
                            if candidate.lower() in actual_lower:
                                resolved = actual_lower[candidate.lower()]
                                break
                        break
                # Try direct match against actual data
                if not resolved:
                    if rv_lower in actual_lower:
                        resolved = actual_lower[rv_lower]
                    else:
                        # Substring search as last resort
                        for actual_r in actual_regions:
                            if rv_lower in actual_r.lower() or actual_r.lower() in rv_lower:
                                resolved = actual_r
                                break

                if resolved:
                    mask &= dframe[region_col] == resolved
                    filtered = True
                # If not resolved, skip filter (don't zero out results)

        # --- Minor LOB filter ---
        # Dynamic: match against actual values in the Minor LOB column
        minor_lob_col = col.get("minor_lob", "Minor LOB")
        minor_lob_fired = False
        if minor_lob_col in dframe.columns:
            # Static keywords (longer first to avoid substring issues)
            minor_lob_keywords = [
                "commercial fire", "marine cargo", "professional indemnity",
                "auto liability", "workers comp", "workers compensation",
                "cyber liability", "product liability", "general liability",
                "employers liability", "business interruption",
                "commercial property", "personal accident", "corporate health",
                "travel medical",
            ]
            # Also add actual LOB values from data (lowered, sorted longest first)
            actual_lobs = sorted(
                dframe[minor_lob_col].dropna().unique(),
                key=lambda x: -len(str(x))
            )
            for lob in actual_lobs:
                lob_lower = str(lob).lower()
                if lob_lower not in minor_lob_keywords:
                    minor_lob_keywords.append(lob_lower)

            for kw in minor_lob_keywords:
                if kw in q:
                    mask &= dframe[minor_lob_col].str.lower().str.contains(
                        re.escape(kw), na=False
                    )
                    minor_lob_fired = True
                    filtered = True
                    break

        # --- Fix 3: Major LOB inline filter (incl. excluding/except) ---
        major_lob_col_f3 = col.get("major_lob", "Major LOB")
        if major_lob_col_f3 in dframe.columns and not minor_lob_fired:
            actual_major = sorted(
                [str(v) for v in dframe[major_lob_col_f3].dropna().unique()],
                key=lambda x: -len(x),
            )
            # Detect exclusion phrasing
            excl_match = re.search(
                r'(?:excluding|except(?:\s+for)?|other\s+than|not\s+in|without)\s+(?:the\s+)?(.+?)(?:\s+lob[s]?\b|\.|$|\?)',
                q,
            )
            requested = []  # list of (lob_name, matched_phrase)
            # Scan for LOB names - both exact (from data) AND common names not in data
            scan_targets = list(actual_major)
            # Also add common LOB names that may not be in the data (for "not found" UX)
            for extra in ["cyber", "aviation", "energy", "financial lines", "workers compensation"]:
                if extra not in [a.lower() for a in scan_targets]:
                    scan_targets.append(extra)
            # Sort longest first to avoid substring collisions (e.g. "a&h" before "h")
            scan_targets = sorted(scan_targets, key=lambda x: -len(str(x)))

            search_zone = excl_match.group(1) if excl_match else q
            for lob in scan_targets:
                lob_lower = str(lob).lower()
                # Require word-ish boundary for short tokens to avoid false hits
                if len(lob_lower) <= 3:
                    pattern = rf'\b{re.escape(lob_lower)}\b'
                    if re.search(pattern, search_zone):
                        requested.append(lob)
                else:
                    if lob_lower in search_zone:
                        requested.append(lob)

            # De-dup (longest-first scanning already avoided substring dupes)
            seen = set()
            requested_unique = []
            for r in requested:
                rl = str(r).lower()
                if rl not in seen:
                    seen.add(rl)
                    requested_unique.append(r)

            if requested_unique:
                # Resolve each requested name to actual data value (case-insensitive)
                actual_lower_map = {str(v).lower(): str(v) for v in actual_major}
                resolved = []
                not_found = []
                for r in requested_unique:
                    rl = str(r).lower()
                    if rl in actual_lower_map:
                        resolved.append(actual_lower_map[rl])
                    else:
                        not_found.append(str(r))

                if excl_match and resolved:
                    mask &= ~dframe[major_lob_col_f3].isin(resolved)
                    filtered = True
                elif resolved:
                    mask &= dframe[major_lob_col_f3].isin(resolved)
                    filtered = True

                # If user explicitly asked for an LOB we don't have, flag it.
                # Only flag when NO valid LOB was also present (otherwise silently drop).
                if not_found and not resolved and not excl_match:
                    _filter_flags["major_lob_not_found"] = not_found
                    _filter_flags["major_lob_available"] = [str(v) for v in sorted(actual_major, key=lambda x: str(x))]
                    # Force empty frame so outer handler uses the message
                    mask &= False
                    filtered = True

        # --- Cause of loss filter ---
        # Skip "fire" if Minor LOB already matched "commercial fire" to avoid double-filter
        cause_col = col.get("cause_of_loss_descr", "Cause Of Loss Descr")
        # minor_lob_fired already set above in Minor LOB filter section
        if cause_col in dframe.columns:
            cause_keywords = [
                "water damage", "slip and fall", "windstorm", "theft",
                "collision", "workplace injury", "equipment failure",
                "professional error", "cyber breach",
                "fire",
            ]
            for kw in cause_keywords:
                if kw in q:
                    # Skip bare "fire" if it's part of a Minor LOB match like "commercial fire"
                    if kw == "fire" and minor_lob_fired:
                        continue
                    mask &= dframe[cause_col].str.lower().str.contains(
                        re.escape(kw), na=False
                    )
                    filtered = True
                    break

        # --- Claim type filter (skip if Minor LOB already matched) ---
        if not minor_lob_fired:
            claim_type_col = col.get("claim_type", "Claim Type Description")
            if claim_type_col in dframe.columns:
                claim_type_val = ent.get("claim_type")
                if not claim_type_val:
                    for kw in ["bodily injury", "property damage", "motor",
                               "liability", "cyber"]:
                        if kw in q:
                            claim_type_val = kw
                            break
                if claim_type_val:
                    ct_mask = dframe[claim_type_col].str.lower().str.contains(
                        re.escape(claim_type_val.lower()), na=False
                    )
                    # If no matches in claim_type_col, try Minor LOB as fallback
                    if not ct_mask.any() and minor_lob_col in dframe.columns:
                        ct_mask = dframe[minor_lob_col].str.lower().str.contains(
                            re.escape(claim_type_val.lower()), na=False
                        )
                    if ct_mask.any():
                        mask &= ct_mask
                        filtered = True

        # --- Catastrophe filter (hurricane, earthquake, wildfire, storm, flood, etc.) ---
        cat_col = col.get("catastrophe_description", "Catastrophe Description")
        if cat_col in dframe.columns:
            cat_keywords = [
                "hurricane", "earthquake", "wildfire", "flood", "tornado",
                "tsunami", "winter storm", "hailstorm", "cyclone",
                "storm", "freeze", "windstorm", "fire season",
            ]
            for kw in cat_keywords:
                if kw in q:
                    mask &= dframe[cat_col].str.lower().str.contains(
                        re.escape(kw), na=False
                    )
                    filtered = True
                    break
            # Also match specific named events (e.g., "Storm Eunice", "Ahr Valley")
            if not filtered:
                cat_name_match = re.search(
                    r'(?:tied to|from|during|related to|for)\s+(?:the\s+)?(?:recent\s+)?([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)',
                    question
                )
                if cat_name_match:
                    event_name = cat_name_match.group(1).lower()
                    if len(event_name) > 3:
                        has_cat = dframe[cat_col].str.lower().str.contains(
                            re.escape(event_name), na=False
                        )
                        if has_cat.any():
                            mask &= has_cat
                            filtered = True

        # --- Accident Year filter ---
        accident_year_col = col.get("accident_year", "Accident Year")
        if accident_year_col in dframe.columns:
            ay_match = re.search(r'\baccident\s+(?:year\s+)?(?:in\s+|happened\s+in\s+)?(\d{4})\b', q)
            if not ay_match:
                ay_match = re.search(r'\bay\s+(\d{4})\b', q)
            if ay_match:
                ay_val = int(ay_match.group(1))
                mask &= dframe[accident_year_col] == ay_val
                filtered = True

        # --- Policy UWY filter (Type-Safe) ---// added by gemini
        policy_uwy_col = col.get("policy_uwy", "Policy UWY")
        uwy_match = re.search(r'\b(?:uwy|underwriting\s+year)\s+(\d{4})\b', q)
        
        uwy_val = None 
        
        if uwy_match:
            uwy_val = int(uwy_match.group(1))
            if policy_uwy_col in dframe.columns:
                safe_uwy = pd.to_numeric(dframe[policy_uwy_col], errors='coerce').fillna(0).astype(int)
                mask &= (safe_uwy == uwy_val)
                filtered = True

        # --- Relative Accident Year filter (Type-Safe) ---
        accident_year_col = col.get("accident_year", "Accident Year")
        if uwy_val and any(phrase in q for phrase in ["a year prior", "year prior", "previous year", "year before"]):
            ay_val = uwy_val - 1
            if accident_year_col in dframe.columns:
                safe_ay = pd.to_numeric(dframe[accident_year_col], errors='coerce').fillna(0).astype(int)
                mask &= (safe_ay == ay_val)
                filtered = True

        # --- Closed / Paid Year filter (Bulletproof) ---
        # Catches "pay", "paid", "pay out", "closed" in all tenses
        payment_match = re.search(r'(?:pay(?: out)?|paid(?: out)?|closed)(?: in)?\s+(\d{4})', q)
        if payment_match:
            payment_yr = str(payment_match.group(1)) 
            closed_col = col.get("claim_closed_date", "Claim Closed Date") 
            if closed_col in dframe.columns:
                mask &= dframe[closed_col].astype(str).str.contains(payment_yr, case=False, na=False)
                filtered = True

        # --- Date range filter (last quarter, this year, etc.) ---
        from datetime import datetime, timedelta
        # Pick the right date column: use Claim Closed Date for "closed" queries,
        # otherwise default to Reported Date
        _closed_words = ["closed", "close", "closing"]
        _use_closed = any(w in q for w in _closed_words)
        if _use_closed:
            date_filter_col = col.get("claim_closed_date", "Claim Closed Date")
        else:
            date_filter_col = col.get("submitted_date", "Reported Date")
        # Fallback to submitted if chosen column missing
        if date_filter_col not in dframe.columns:
            date_filter_col = col.get("submitted_date", "Reported Date")
        if date_filter_col in dframe.columns:
            today = datetime.now()
            _date_series = pd.to_datetime(dframe[date_filter_col], errors="coerce")
            if "last quarter" in q:
                # Previous calendar quarter
                q_month = ((today.month - 1) // 3) * 3  # start of current quarter
                if q_month == 0:
                    q_start = datetime(today.year - 1, 10, 1)
                    q_end = datetime(today.year - 1, 12, 31)
                else:
                    q_start = datetime(today.year, q_month - 2, 1)
                    q_end = datetime(today.year, q_month, 1) - timedelta(days=1)
                mask &= _date_series >= q_start
                mask &= _date_series <= q_end
                filtered = True
            elif "this year" in q or "ytd" in q:
                # Data may not have current year — find the latest year in data
                _max_year = _date_series.dropna().dt.year.max()
                _target_year = today.year if _date_series.dt.year.eq(today.year).any() else _max_year
                mask &= _date_series.dt.year == _target_year
                filtered = True
                if _target_year != today.year:
                    logger.info(f"'this year' adjusted to {_target_year} (latest in data)")
            elif "last year" in q:
                _max_year = _date_series.dropna().dt.year.max()
                _target_year = today.year - 1 if _date_series.dt.year.eq(today.year).any() else _max_year - 1
                mask &= _date_series.dt.year == _target_year
                filtered = True

        # --- Fix 2: Explicit date range filter ("between X and Y", "from X to Y") ---
        # Choose date col based on keywords
        if any(w in q for w in ["event", "loss", "accident"]) and col.get("event_date", "Event Date") in dframe.columns:
            _range_col = col.get("event_date", "Event Date")
        elif _use_closed and col.get("claim_closed_date", "Claim Closed Date") in dframe.columns:
            _range_col = col.get("claim_closed_date", "Claim Closed Date")
        else:
            _range_col = col.get("submitted_date", "Reported Date")

        if _range_col in dframe.columns:
            _date_series_range = pd.to_datetime(dframe[_range_col], errors="coerce")
            # Pattern: "between <X> and <Y>" or "from <X> to <Y>"
            # Grab the raw (case-preserving) question to parse month names correctly.
            _range_match = re.search(
                r'(?:between|from)\s+(.+?)\s+(?:and|to|through)\s+(.+?)(?:\.|\?|$|\s+for\s|\s+where\s|\s+in\s+the\s|\s+excluding\s)',
                question,
                re.IGNORECASE,
            )
            if not _range_match:
                _range_match = re.search(
                    r'(?:between|from)\s+(.+?)\s+(?:and|to|through)\s+(.+)',
                    question,
                    re.IGNORECASE,
                )
            if _range_match:
                _s_raw = _range_match.group(1).strip().rstrip(",")
                _e_raw = _range_match.group(2).strip().rstrip(".?,")
                # If just a year like "2020", treat as Jan 1 / Dec 31
                _year_only_s = re.fullmatch(r'(\d{4})', _s_raw)
                _year_only_e = re.fullmatch(r'(\d{4})', _e_raw)
                try:
                    if _year_only_s:
                        _start_dt = pd.Timestamp(int(_year_only_s.group(1)), 1, 1)
                    else:
                        _start_dt = pd.to_datetime(_s_raw, errors="coerce")
                    if _year_only_e:
                        _end_dt = pd.Timestamp(int(_year_only_e.group(1)), 12, 31)
                    else:
                        _end_dt = pd.to_datetime(_e_raw, errors="coerce")
                except Exception:
                    _start_dt = _end_dt = pd.NaT
                if pd.notna(_start_dt) and pd.notna(_end_dt):
                    mask &= _date_series_range >= _start_dt
                    mask &= _date_series_range <= _end_dt
                    filtered = True

        # --- Reporting delay filter ---
        if "month" in q and "report" in q:
            delay_match = re.search(r'(?:more than|over|>\s*)(\d+)\s*months?\s*to\s*report', q)
            if delay_match:
                delay_months = int(delay_match.group(1))
                loss_date_col = col.get("date_of_loss", "Date Of Loss")
                report_date_col = col.get("submitted_date", "Reported Date")
                if loss_date_col in dframe.columns and report_date_col in dframe.columns:
                    loss_dt = pd.to_datetime(dframe[loss_date_col], errors='coerce')
                    report_dt = pd.to_datetime(dframe[report_date_col], errors='coerce')
                    delay_days = (report_dt - loss_dt).dt.days
                    mask &= delay_days > (delay_months * 30)
                    filtered = True

        # --- Bulk claim indicator filter ---
        # Detect "exclude bulk" vs "only bulk" vs just "bulk"
        bulk_col = col.get("bulk_claim_indicator", "Bulk Claim Indicator")
        if bulk_col in dframe.columns and _has_word("bulk"):
            is_bulk = dframe[bulk_col].astype(str).str.lower().isin(
                ["y", "yes", "true", "1"]
            )
            exclude_bulk = any(w in q for w in ["exclude", "excluding", "without",
                                                 "not bulk", "non-bulk", "no bulk",
                                                 "remove bulk", "filter out bulk"])
            if exclude_bulk:
                mask &= ~is_bulk
            else:
                mask &= is_bulk
            filtered = True

        # --- Reserve / amount threshold filter ---
        # Matches: "reserve over 1000", "nominal reserve under $5k",
        #          "reserve is under a thousand bucks", "amount > 50000"
        _word_numbers = {
            "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000,
            "hundred": 100, "ten": 10, "fifty": 50, "twenty": 20,
        }
        # Try digit-based pattern first
        threshold_match = re.search(
            r'(?:over|above|greater than|more than|under|below|less than|at least|exceeds?|>\s*|<\s*)\s*'
            r'\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|thousand|million|M)?\s*(?:bucks?|dollars?|usd)?',
            q
        )
        # Try word-based pattern: "under a thousand", "over five hundred"
        word_threshold_match = re.search(
            r'(?:over|above|greater than|more than|under|below|less than|at least)\s+'
            r'(?:a\s+)?(\w+)\s*(?:bucks?|dollars?|usd)?',
            q
        ) if not threshold_match else None

        thresh = None
        thresh_context = ""
        if threshold_match:
            raw_val = threshold_match.group(1).replace(",", "")
            thresh = float(raw_val)
            thresh_context = q[max(0, threshold_match.start()-20):threshold_match.end()+10].lower()
            # Multiplier detection
            post = q[threshold_match.end()-15:threshold_match.end()+5].lower()
            if any(m in post for m in ["k", "thousand"]):
                thresh *= 1000
            elif "million" in post or "m" in post.split()[-1:]:
                thresh *= 1_000_000
        elif word_threshold_match:
            word = word_threshold_match.group(1).lower()
            if word in _word_numbers:
                thresh = float(_word_numbers[word])
            thresh_context = q[max(0, word_threshold_match.start()-20):word_threshold_match.end()+10].lower()

        if thresh is not None:
            is_under = any(w in thresh_context for w in ["under", "below", "less than", "<"])

            # Pick the right column to threshold on
            thresh_col = None
            if "nominal" in q and col.get("nominal_reserve") and col["nominal_reserve"] in dframe.columns:
                thresh_col = col["nominal_reserve"]
            elif "nominal" in q:
                # Fallback: use outstanding reserve if nominal doesn't exist
                thresh_col = col.get("outstanding_reserve_usd", col.get("reserve_amount"))
            elif "incurred" in q:
                thresh_col = col.get("incurred_usd", col.get("claim_amount"))
            else:
                thresh_col = col.get("outstanding_reserve_usd", col.get("reserve_amount"))

            if thresh_col and thresh_col in dframe.columns:
                if is_under:
                    # "exclude where under X" → keep >= X
                    if any(w in q for w in ["exclude", "excluding", "without",
                                             "filter out", "completely exclude"]):
                        mask &= dframe[thresh_col] >= thresh
                    else:
                        mask &= dframe[thresh_col] < thresh
                else:
                    mask &= dframe[thresh_col] >= thresh
                filtered = True

        # --- MAR fast track filter ---
        mar_col = col.get("mar_fast_track_flag", "MAR Fast Track Flag")
        if mar_col in dframe.columns and (
            "fast track" in q or _has_word("mar")
        ):
            mask &= dframe[mar_col].astype(str).str.lower().isin(
                ["y", "yes", "true", "1"]
            )
            filtered = True

        # --- Business Entity filter ---
        entity_col = col.get("business_entity", "Business Entity")
        if entity_col in dframe.columns:
            # Match "for <Company Name>" pattern with 2+ words
            ent_match = re.search(
                r'(?:for|from|at)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]*)*(?:\s+(?:Inc|Ltd|Corp|LLC|GmbH|SA|AG|NV|BV|SE|plc)\.?)?)',
                question
            )
            if ent_match:
                ent_name = ent_match.group(1)
                has_entity = dframe[entity_col].str.contains(ent_name, case=False, na=False)
                if has_entity.any():
                    mask &= has_entity
                    filtered = True

        # --- Policyholder name filter ---
        # Only trigger on quoted names or very explicit "for <Name>" patterns
        # Exclude known entity/dimension keywords to avoid false positives
        _entity_words = {
            "open", "closed", "pending", "rejected", "under", "review",
            "uk", "us", "usa", "canada", "australia", "germany", "france",
            "japan", "brazil", "india", "commercial", "marine", "cyber",
            "motor", "property", "bodily", "injury", "liability", "auto",
            "general", "product", "workers", "professional", "fire",
            "claim", "claims", "all", "each", "every", "total", "the",
            "top", "biggest", "volume", "factor", "factors", "type",
            "status", "region", "country", "lob", "bulk", "average",
        }
        ph_col = col.get("policy_holder_name", "Policy Holder Name")
        if ph_col in dframe.columns:
            # Prefer quoted names: "for 'Alice Corp'" or 'for "Alice Corp"'
            ph_match = re.search(r'(?:for|from|by)\s+["\']([^"\']+)["\']', question)
            if not ph_match:
                # Unquoted: require at least 2-word proper name to reduce false positives
                ph_match = re.search(r'\bfor\s+([A-Z][a-z]+\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)', question)
            if ph_match:
                ph_name = ph_match.group(1)
                first_word = ph_name.split()[0].lower()
                if first_word not in _entity_words:
                    mask &= dframe[ph_col].str.contains(ph_name, case=False, na=False)
                    filtered = True

        if not filtered:
            return dframe
        return dframe[mask]

    # --- Fix 3 (outer): handle "Major LOB not found" message ---
    # Call _apply_filters early only to detect flags; actual handlers will
    # call it again as needed. This is cheap because subsequent calls are
    # idempotent (same question text).
    if df is not None and col is not None:
        _probe = _apply_filters(df)
        if _filter_flags.get("major_lob_not_found"):
            _missing = _filter_flags["major_lob_not_found"]
            _avail = _filter_flags.get("major_lob_available", [])
            _m = ", ".join(f"'{m}'" for m in _missing)
            _a = ", ".join(_avail)
            return (
                f"No claims found for LOB {_m} — available LOBs: {_a}."
            )

    # --- Fix 1a: Bottom-N row-level ("bottom 10 claims by <metric>") ---
    if df is not None and col is not None:
        _bottom_match = re.search(
            r'\b(?:bottom|lowest|smallest|least|worst|fewest)\s+(\d+)\s+claim',
            q,
        )
        if _bottom_match:
            _n = int(_bottom_match.group(1))
            # Determine which metric column
            _metric_col = None
            _metric_label = None
            for _kw, (_cfg_key, _disp) in [
                ("incurred", ("incurred_usd", "Incurred USD")),
                ("indemnity", ("indemnity_paid_usd", "Indemnity Paid USD")),
                ("expense", ("expense_paid_usd", "Expense Paid USD")),
                ("outstanding reserve", ("outstanding_reserve_usd", "Outstanding Reserve USD")),
                ("nominal reserve", ("nominal_reserve", "Nominal Reserve")),
                ("reserve", ("outstanding_reserve_usd", "Outstanding Reserve USD")),
                ("paid", ("indemnity_paid_usd", "Indemnity Paid USD")),
            ]:
                if _kw in q:
                    _actual = col.get(_cfg_key, _disp)
                    if _actual in df.columns:
                        _metric_col = _actual
                        _metric_label = _disp
                        break
            if _metric_col is None:
                _metric_col = col.get("incurred_usd", col.get("claim_amount", "Incurred USD"))
                _metric_label = _metric_col
            fdf = _apply_filters(df)
            if _metric_col in fdf.columns and len(fdf) > 0:
                _sub = fdf.nsmallest(_n, _metric_col)
                _id_col = col.get("claim_id", "Claim Number")
                _lines = []
                for _, _row in _sub.iterrows():
                    _cid = _row.get(_id_col, "?")
                    _val = _row.get(_metric_col, 0)
                    _lines.append(f"- {_cid}: ${_val:,.2f}")
                _filter_desc = f" (from {len(fdf):,} matching)" if len(fdf) < len(df) else ""
                return (
                    f"**Bottom {_n} claims by {_metric_label}{_filter_desc}:**\n"
                    + "\n".join(_lines)
                )

    # --- Fix 4: Generalized unique/distinct count ---
    # "how many unique X" / "number of unique X" / "count of distinct X"
    # Also: "unique X with more than N claims"
    if df is not None and col is not None:
        _uc_match = re.search(
            r'(?:how\s+many|number\s+of|count\s+of)\s+(?:unique|distinct|different)\s+(.+?)(?:\?|\.|$|\s+have\b|\s+with\b|\s+that\b|\s+which\b)',
            q,
        )
        if _uc_match:
            _phrase = _uc_match.group(1).strip()
            _resolved = resolve_column_synonym(_phrase, set(df.columns))
            _target = None
            for _c in _resolved:
                if _c in df.columns:
                    _target = _c
                    break
            # Fallback: try known column names directly
            if _target is None:
                for _candidate in ["Policy Number", "Claim Number", "Responsible Adjuster",
                                   "Major LOB", "Minor LOB", "Country", "Business Entity",
                                   "Accident Year", "Policy UWY", "Claim Status Derived"]:
                    if _candidate in df.columns and _candidate.lower() in _phrase:
                        _target = _candidate
                        break
            # Shortcuts for multi-word phrases missed above
            if _target is None and "policy" in _phrase and col.get("policy_number", "Policy Number") in df.columns:
                _target = col.get("policy_number", "Policy Number")

            if _target is not None:
                fdf = _apply_filters(df)
                # "with more than N claims" pattern
                _more_than_match = re.search(r'(?:more\s+than|greater\s+than|over|>\s*)\s*(\d+)\s*claim', q)
                _has_filed_many = "filed" in q or "have filed" in q or "with more than" in q or "more than one claim" in q
                if _more_than_match or "more than one claim" in q:
                    _threshold = int(_more_than_match.group(1)) if _more_than_match else 1
                    _counts = fdf.groupby(_target).size()
                    _n = int((_counts > _threshold).sum())
                    return (
                        f"**{_n:,}** unique {_target} values have more than {_threshold} claims."
                    )
                _n = int(fdf[_target].nunique())
                return f"There are **{_n:,}** unique {_target} values."

    # --- List unique / distinct values for a column ---
    # Handles: "what are the different UWY", "list all regions", "show unique statuses"
    if df is not None and col is not None and any(
        phrase in q for phrase in [
            "what are the different", "what are the distinct", "what are the unique",
            "what are different", "what are distinct", "what are unique",
            "what different", "what distinct",
            "how many distinct", "how many different", "how many unique",
            "number of distinct", "number of different", "number of unique",
            "count of distinct", "count of different", "count of unique",
            "list all", "list the", "show all", "show me all",
            "which regions", "which countries", "which statuses", "which types",
            "which lob", "which uwy", "which year", "what regions", "what countries",
            "what types", "what statuses", "what lob",
        ]
    ):
        # Map question keywords to column config keys
        _distinct_col_map = [
            (["uwy", "underwriting year", "policy year"], "policy_uwy", "Policy UWY"),
            (["accident year", "ay", "loss year"], "accident_year", "Accident Year"),
            (["region", "country", "countries", "geography"], "region", "Country"),
            (["status", "statuses", "claim status"], "status", "Claim Status"),
            (["minor lob", "minor line"], "claim_type", "Minor LOB"),
            (["major lob", "major line", "lob", "line of business", "class of business", "product line"], "major_lob", "Major LOB"),
            (["executive lob"], "executive_lob", "Executive LOB"),
            (["currency", "currencies"], "ledger_currency", "Ledger Currency"),
            (["cause of loss", "cause", "peril", "reason for loss", "incident type"], "cause_of_loss_descr", "Cause of Loss"),
            (["injury", "condition", "damage", "damage type", "diagnosis", "medical condition"], "condition_injury_damage_name", "Condition/Injury"),
            (["contributing factor", "factor"], "contributing_factor_descr", "Contributing Factor"),
            (["catastrophe", "cat event", "natural disaster", "named storm"], "catastrophe_description", "Catastrophe"),
            (["entity", "entities", "business entity", "subsidiary"], "business_entity", "Business Entity"),
            (["adjuster", "handler", "examiner", "case manager", "claim owner"], "responsible_adjuster", "Responsible Adjuster"),
            (["broker", "agent", "intermediary", "producer"], "producer_name", "Producer"),
            (["branch", "handling office", "claim office"], "claim_office", "Claim Office"),
            (["insured", "client", "policyholder", "customer", "policy holder"], "policy_holder_name", "Policy Holder"),
            (["fast track", "stp", "straight-through", "auto-approved"], "mar_fast_track_flag", "Fast Track Flag"),
            (["coverage", "coverage code"], "coverage_code", "Coverage Code"),
            (["location of loss", "loss location", "accident site", "venue"], "location_of_loss", "Location of Loss"),
            (["date reported", "reported date", "notification date", "fnol", "submission date"], "submitted_date", "Reported Date"),
            (["event date", "date of loss", "dol", "accident date", "incident date", "occurrence date"], "event_date", "Event Date"),
            (["closed date", "settlement date", "resolution date"], "claim_closed_date", "Claim Closed Date"),
            (["reserving class"], "reserving_class", "Reserving Class"),
            (["reserving line"], "reserving_line", "Reserving Line"),
            (["claim type", "claim type description"], "claim_type_description", "Claim Type Description"),
            (["catastrophe code"], "catastrophe_code", "Catastrophe Code"),
        ]

        target_col = None
        target_label = None
        for keywords, cfg_key, label in _distinct_col_map:
            if any(kw in q for kw in keywords):
                actual = col.get(cfg_key, label)
                if actual in df.columns:
                    target_col = actual
                    target_label = label
                    break

        if target_col:
            # Don't apply entity filters for the dimension being listed
            # (e.g. don't filter by status when asking "which statuses exist")
            saved_ent = dict(ent)
            status_col_name = col.get("status", "Claim Status Derived")
            region_col_name = col.get("region", "Country")
            type_col_name = col.get("claim_type", "Minor LOB")
            if target_col == status_col_name:
                ent.pop("status", None)
            if target_col == region_col_name:
                ent.pop("region", None)
            if target_col == type_col_name:
                ent.pop("claim_type", None)

            fdf = _apply_filters(df)
            ent.update(saved_ent)  # restore

            filter_desc = f" (filtered to {len(fdf):,} claims)" if len(fdf) < len(df) else ""
            unique_vals = fdf[target_col].dropna().unique()
            unique_sorted = sorted(unique_vals, key=lambda x: str(x))
            lines = [f"- {v}" for v in unique_sorted]
            return (
                f"**{target_label} — {len(unique_sorted)} distinct values{filter_desc}:**\n\n"
                + "\n".join(lines)
            )
        else:
            # Column not found — provide smart fallback with alternatives
            _fallback_suggestions = {
                "policy_uwy": ("Underwriting Year (UWY)", [
                    ("accident_year", "Accident Year"),
                    ("submitted_date", "Reported Date (year)"),
                ]),
                "nominal_reserve": ("Nominal Reserve", [
                    ("outstanding_reserve_usd", "Outstanding Reserve USD"),
                    ("reserve_amount", "Outstanding Reserve USD"),
                ]),
                "recoveries_usd": ("Recoveries USD", [
                    ("incurred_usd", "Incurred USD"),
                ]),
                "bulk_claim_indicator": ("Bulk Claim Indicator", []),
                "responsible_adjuster": ("Responsible Adjuster", [
                    ("business_entity", "Business Entity"),
                ]),
                "company_share": ("Company Share", []),
            }

            # Find which config key was requested
            matched_cfg = None
            for keywords, cfg_key, label in _distinct_col_map:
                if any(kw in q for kw in keywords):
                    matched_cfg = cfg_key
                    break

            if matched_cfg and matched_cfg in _fallback_suggestions:
                label, alts = _fallback_suggestions[matched_cfg]
                msg = f"**{label}** column is not available in the current dataset.\n\n"
                # Try to show alternative
                for alt_cfg, alt_label in alts:
                    alt_col = col.get(alt_cfg, alt_label)
                    if alt_col in df.columns:
                        unique_vals = df[alt_col].dropna().unique()
                        unique_sorted = sorted(unique_vals, key=lambda x: str(x))
                        lines = [f"- {v}" for v in unique_sorted]
                        msg += (
                            f"However, **{alt_label}** is available "
                            f"({len(unique_sorted)} distinct values):\n\n"
                            + "\n".join(lines)
                        )
                        return msg
                msg += (
                    f"Available columns: "
                    f"{', '.join(sorted(c for c in df.columns if not c.startswith('_')))}"
                )
                return msg

            return (
                "That column doesn't exist in the current dataset.\n\n"
                f"Available dimensions: {', '.join(sorted(df.columns))}"
            )

    # --- Fix 5 (early): Multi-dim pivot "by X and by Y" / "per X and per Y" ---
    # Placed BEFORE single-dim groupby handlers so 2D queries aren't caught by 1D.
    if df is not None and col is not None:
        _pivot_match_e = re.search(
            r'\bby\s+(.+?)\s+and\s+by\s+(.+?)(?:\?|\.|$|\s+for\s|\s+where\s|\s+in\s+)',
            q,
        )
        if not _pivot_match_e:
            _pivot_match_e = re.search(
                r'\bper\s+(.+?)\s+and\s+per\s+(.+?)(?:\?|\.|$)',
                q,
            )
        if not _pivot_match_e:
            _pivot_match_e = re.search(
                r'\bby\s+(.+?)\s*,\s*by\s+(.+?)(?:\?|\.|$)',
                q,
            )
        if _pivot_match_e:
            _a_phrase = _pivot_match_e.group(1).strip()
            _b_phrase = _pivot_match_e.group(2).strip()
            _a_res = resolve_column_synonym(_a_phrase, set(df.columns))
            _b_res = resolve_column_synonym(_b_phrase, set(df.columns))
            _col_a = next(iter(_a_res), None)
            _col_b = next(iter(_b_res), None)
            if _col_a and _col_b and _col_a != _col_b:
                fdf = _apply_filters(df)
                if len(fdf) > 0:
                    _pivot = fdf.groupby([_col_a, _col_b]).size().unstack(fill_value=0)
                    _cols = list(_pivot.columns)
                    _header = f"| {_col_a} \\ {_col_b} | " + " | ".join(str(c) for c in _cols) + " |"
                    _sep = "|" + "|".join(["---"] * (len(_cols) + 1)) + "|"
                    _rows = []
                    for _idx, _row in _pivot.iterrows():
                        _rows.append(
                            f"| {_idx} | " + " | ".join(f"{int(v):,}" for v in _row.values) + " |"
                        )
                    _filter_desc = f" ({len(fdf):,} matching)" if len(fdf) < len(df) else ""
                    return (
                        f"**Claims by {_col_a} and {_col_b}{_filter_desc}:**\n\n"
                        + "\n".join([_header, _sep] + _rows)
                    )

    # --- Entity-aware status count ---
    if ent.get("status") and ("how many" in q or _has_word("count")
                              or "show me" in q or "show" in q
                              or "list" in q or "give me" in q
                              or "get me" in q or "find" in q):
        # Check if there are additional filters beyond just status
        fdf = _apply_filters(df) if df is not None else None
        if fdf is not None and len(fdf) == 0:
            return _zero_results_message(ent, question)
        if fdf is not None and len(fdf) < len(df):
            # Additional filters present — use filtered count
            status_val = ent["status"]
            return f"There are **{len(fdf):,}** {status_val} claims matching your criteria."
        status_val = ent["status"]
        count = summary["status_counts"].get(status_val, 0)
        return f"There are **{count:,}** {status_val} claims in the current dataset."

    # --- Count BY region ---
    if df is not None and col is not None and (
        ("how many" in q or _has_word("count")) and "region" in q
    ):
        fdf = _apply_filters(df)
        result = fdf.groupby(col["region"])[col["claim_id"]].count().sort_values(ascending=False)
        lines = [f"- {r}: {c:,}" for r, c in result.items()]
        return "**Claims Count by Region:**\n" + "\n".join(lines)

    # --- Count BY type ---
    if df is not None and col is not None and (
        ("how many" in q or _has_word("count")) and "type" in q
    ):
        fdf = _apply_filters(df)
        result = fdf.groupby(col["claim_type"])[col["claim_id"]].count().sort_values(ascending=False)
        lines = [f"- {t}: {c:,}" for t, c in result.items()]
        return "**Claims Count by Claim Type:**\n" + "\n".join(lines)

    # --- Average BY type ---
    if df is not None and col is not None and (
        ("average" in q or "avg" in q) and "type" in q
    ):
        fdf = _apply_filters(df)
        result = fdf.groupby(col["claim_type"])[col["claim_amount"]].mean().sort_values(ascending=False)
        lines = [f"- {t}: ${v:,.2f}" for t, v in result.items()]
        return "**Average Claim Value by Claim Type:**\n" + "\n".join(lines)

    # --- Average BY region ---
    if df is not None and col is not None and (
        ("average" in q or "avg" in q) and "region" in q
    ):
        fdf = _apply_filters(df)
        result = fdf.groupby(col["region"])[col["claim_amount"]].mean().sort_values(ascending=False)
        lines = [f"- {r}: ${v:,.2f}" for r, v in result.items()]
        return "**Average Claim Value by Region:**\n" + "\n".join(lines)

    # --- Total value BY claim type ---
    if df is not None and col is not None and (
        "by claimtype" in q or "by claim type" in q or "per type" in q or
        ("type" in q and ("total" in q or "value" in q or "amount" in q))
    ):
        fdf = _apply_filters(df)
        result = fdf.groupby(col["claim_type"])[col["claim_amount"]].sum().sort_values(ascending=False)
        lines = [f"- {t}: ${v:,.2f}" for t, v in result.items()]
        return "**Total Claim Value by Claim Type:**\n" + "\n".join(lines)

    # --- Total value BY region ---
    if df is not None and col is not None and (
        "by region" in q or "per region" in q or
        ("region" in q and ("total" in q or "value" in q or "amount" in q))
    ):
        fdf = _apply_filters(df)
        result = fdf.groupby(col["region"])[col["claim_amount"]].sum().sort_values(ascending=False)
        lines = [f"- {r}: ${v:,.2f}" for r, v in result.items()]
        return "**Total Claim Value by Region:**\n" + "\n".join(lines)

    # --- Total value BY status ---
    if df is not None and col is not None and (
        ("by status" in q or "per status" in q) and
        ("total" in q or "value" in q or "amount" in q)
    ) or (
        df is not None and col is not None and
        "status" in q and ("total" in q or "value" in q or "amount" in q)
    ):
        fdf = _apply_filters(df)
        result = fdf.groupby(col["status"])[col["claim_amount"]].sum().sort_values(ascending=False)
        lines = [f"- {s}: ${v:,.2f}" for s, v in result.items()]
        return "**Total Claim Value by Status:**\n" + "\n".join(lines)

    # --- Currency / ledger currency handler ---
    if df is not None and col is not None and (
        "currency" in q or "ledger" in q or "local currency" in q
    ):
        currency_col = col.get("ledger_currency", "ledger Currency")
        if currency_col in df.columns:
            fdf = _apply_filters(df)
            filter_desc = f" ({len(fdf):,} matching claims)" if len(fdf) < len(df) else ""

            # Determine which financial column to group
            fin_col = None
            fin_label = "Amount"
            for kw, (cfg, label) in [
                ("expense", ("expense_paid_usd", "Expense Paid USD")),
                ("indemnity", ("indemnity_paid_usd", "Indemnity Paid USD")),
                ("incurred", ("incurred_usd", "Incurred USD")),
                ("reserve", ("outstanding_reserve_usd", "Outstanding Reserve USD")),
            ]:
                if kw in q:
                    actual = col.get(cfg, label)
                    if actual in fdf.columns:
                        fin_col = actual
                        fin_label = label
                        break

            if fin_col is None:
                fin_col = col.get("incurred_usd", "Incurred USD")
                if fin_col not in fdf.columns:
                    fin_col = col["claim_amount"]
                fin_label = "Total Value"

            result = fdf.groupby(currency_col)[fin_col].sum().sort_values(ascending=False)
            lines = [f"- {c}: {v:,.2f}" for c, v in result.items()]
            return f"**{fin_label} by Currency{filter_desc}:**\n" + "\n".join(lines)

    # --- Multi-column comparison: "Incurred vs Reserves by Major LOB" etc. ---
    if df is not None and col is not None and (
        ("versus" in q or " vs " in q or " vs." in q or "compared to" in q or "breakdown" in q)
        and any(kw in q for kw in ["incurred", "reserve", "indemnity", "expense", "paid"])
    ):
        # Detect which financial columns to compare
        fin_cols_to_show = []
        fin_map = [
            ("incurred", "incurred_usd", "Incurred USD"),
            ("outstanding reserve", "outstanding_reserve_usd", "Outstanding Reserve USD"),
            ("reserve", "outstanding_reserve_usd", "Outstanding Reserve USD"),
            ("indemnity", "indemnity_paid_usd", "Indemnity Paid USD"),
            ("expense paid", "expense_paid_usd", "Expense Paid USD"),
            ("expense reserve", "expense_reserve_usd", "Expense Reserve USD"),
        ]
        for kw, cfg_key, display in fin_map:
            if kw in q:
                actual = col.get(cfg_key, display)
                if actual in df.columns and (actual, display) not in fin_cols_to_show:
                    fin_cols_to_show.append((actual, display))

        # Detect group-by dimension
        group_col = None
        group_label = ""
        if "major lob" in q or "major line" in q:
            group_col = col.get("major_lob", "Major LOB")
            group_label = "Major LOB"
        elif "minor lob" in q or "minor line" in q:
            group_col = col.get("minor_lob", "Minor LOB")
            group_label = "Minor LOB"
        elif "lob" in q or "line of business" in q:
            group_col = col.get("major_lob", "Major LOB")
            group_label = "LOB"
        elif "region" in q or "country" in q:
            group_col = col.get("region", "Country")
            group_label = "Country"
        elif "status" in q:
            group_col = col.get("status", "Claim Status Derived")
            group_label = "Status"

        if len(fin_cols_to_show) >= 1 and group_col and group_col in df.columns:
            fdf = _apply_filters(df)
            if len(fdf) == 0:
                return "No claims found matching your filters. Try broadening your criteria."
            filter_desc = f" ({len(fdf):,} matching claims)" if len(fdf) < len(df) else ""

            grouped = fdf.groupby(group_col)
            lines = []
            for grp_name in grouped[group_col].count().sort_values(ascending=False).index:
                grp = grouped.get_group(grp_name)
                vals = []
                for actual_col, display in fin_cols_to_show:
                    vals.append(f"{display}: ${grp[actual_col].sum():,.2f}")
                lines.append(f"- **{grp_name}** ({len(grp):,} claims): " + " | ".join(vals))

            col_names = " vs ".join(d for _, d in fin_cols_to_show)
            return f"**{col_names} by {group_label}{filter_desc}:**\n\n" + "\n".join(lines)

    # --- By Major LOB handler (single financial metric) ---
    # Skip when user is asking for a superlative — Fix 1b / top-N handlers own that.
    _lob_superlative = any(w in q for w in [
        "least", "fewest", "lowest", "smallest", "worst", "bottom",
        "most", "highest", "largest", "biggest", "top",
    ])
    if df is not None and col is not None and (
        "major lob" in q or "major line" in q
    ) and not _lob_superlative:
        major_lob_col = col.get("major_lob", "Major LOB")
        if major_lob_col in df.columns:
            fdf = _apply_filters(df)
            if len(fdf) == 0:
                return "No claims found matching your filters. Try broadening your criteria."
            filter_desc = f" ({len(fdf):,} matching claims)" if len(fdf) < len(df) else ""

            # Detect financial column or default to count
            fin_col = None
            fin_label = "Claims"
            for kw, cfg_key, display in [
                ("incurred", "incurred_usd", "Incurred USD"),
                ("reserve", "outstanding_reserve_usd", "Outstanding Reserve USD"),
                ("indemnity", "indemnity_paid_usd", "Indemnity Paid USD"),
                ("expense", "expense_paid_usd", "Expense Paid USD"),
            ]:
                if kw in q:
                    actual = col.get(cfg_key, display)
                    if actual in fdf.columns:
                        fin_col = actual
                        fin_label = display
                        break

            if fin_col:
                result = fdf.groupby(major_lob_col)[fin_col].sum().sort_values(ascending=False)
                lines = [f"- {lob}: ${v:,.2f}" for lob, v in result.items()]
                return f"**{fin_label} by Major LOB{filter_desc}:**\n" + "\n".join(lines)
            else:
                result = fdf.groupby(major_lob_col)[col["claim_id"]].count().sort_values(ascending=False)
                lines = [f"- {lob}: {c:,}" for lob, c in result.items()]
                return f"**Claims by Major LOB{filter_desc}:**\n" + "\n".join(lines)

    # --- Net exposure / gross-net calculation ---
    # "Net exposure" = Outstanding Reserve × Company Share
    # "Gross exposure" = Outstanding Reserve (without share adjustment)
    if df is not None and col is not None and (
        "exposure" in q or "net position" in q or "net reserve" in q
    ):
        reserve_col = col.get("outstanding_reserve_usd", "Outstanding Reserve USD")
        share_col = col.get("company_share", "Company Share")
        fdf = _apply_filters(df)
        filter_desc = f" ({len(fdf):,} matching claims)" if len(fdf) < len(df) else ""

        if reserve_col in fdf.columns:
            if len(fdf) == 0:
                return f"No claims found matching your filters{filter_desc}. Try broadening your criteria."

            gross = fdf[reserve_col].sum()

            if ("net" in q or "company share" in q or "our share" in q or "factoring" in q) and share_col in fdf.columns:
                # Net = sum(Outstanding Reserve × Company Share) per row
                net = (fdf[reserve_col] * fdf[share_col]).sum()
                avg_share = fdf[share_col].mean() * 100
                return (
                    f"**Net Exposure{filter_desc}:**\n\n"
                    f"- Gross Outstanding Reserve: **${gross:,.2f}**\n"
                    f"- Average Company Share: **{avg_share:.1f}%**\n"
                    f"- **Net Exposure (Reserve × Share): ${net:,.2f}**\n\n"
                    f"_Net = Outstanding Reserve × Company Share per claim_"
                )
            else:
                return (
                    f"**Gross Exposure{filter_desc}:**\n\n"
                    f"- Outstanding Reserve: **${gross:,.2f}**"
                )

    # --- Specific financial column queries ---
    # Maps keyword patterns to (config_key, display_name)
    _fin_columns = {
        # Longer/more-specific keys MUST come before shorter ones
        "outstanding reserve": ("outstanding_reserve_usd", "Outstanding Reserve USD"),
        "case reserve": ("outstanding_reserve_usd", "Outstanding Reserve USD"),
        "current reserve": ("outstanding_reserve_usd", "Outstanding Reserve USD"),
        "nominal reserve": ("nominal_reserve", "Nominal Reserve"),
        "expense reserve": ("expense_reserve_usd", "Expense Reserve USD"),
        "expense paid": ("expense_paid_usd", "Expense Paid USD"),
        "defense costs": ("expense_paid_usd", "Expense Paid USD"),
        "legal fees": ("expense_paid_usd", "Expense Paid USD"),
        "expert fees": ("expense_paid_usd", "Expense Paid USD"),
        "reserve": ("reserve_amount", "Outstanding Reserve USD"),
        "reserves": ("reserve_amount", "Outstanding Reserve USD"),
        "recoveries": ("recoveries_usd", "Recoveries USD"),
        "recovery": ("recoveries_usd", "Recoveries USD"),
        "subrogation": ("recoveries_usd", "Recoveries USD"),
        "subro": ("recoveries_usd", "Recoveries USD"),
        "salvage": ("recoveries_usd", "Recoveries USD"),
        "alae": ("expense_paid_usd", "Expense Paid USD"),
        "legal": ("expense_paid_usd", "Expense Paid USD"),
        "indemnity": ("indemnity_paid_usd", "Indemnity Paid USD"),
        "payout": ("indemnity_paid_usd", "Indemnity Paid USD"),
        "settlement": ("indemnity_paid_usd", "Indemnity Paid USD"),
        "loss paid": ("indemnity_paid_usd", "Indemnity Paid USD"),
        "damages paid": ("indemnity_paid_usd", "Indemnity Paid USD"),
        "total incurred": ("incurred_usd", "Incurred USD"),
        "gross incurred": ("incurred_usd", "Incurred USD"),
        "total cost": ("incurred_usd", "Incurred USD"),
        "incurred": ("incurred_usd", "Incurred USD"),
    }

    # Skip financial handler when "top N [dimension]" detected — let top handler handle it
    _skip_fin_for_top = bool(re.search(r'\btop\s+\d+', q)) and resolve_column_synonym(q, set(df.columns) if df is not None else None)
    if df is not None and col is not None and not _skip_fin_for_top:
        for fin_kw, (cfg_key, display) in _fin_columns.items():
            if fin_kw in q:
                actual_col = col.get(cfg_key, display)
                if actual_col not in df.columns:
                    continue
                fdf = _apply_filters(df)
                filter_desc = f" ({len(fdf):,} matching claims)" if len(fdf) < len(df) else ""

                # --- Zero-results guard ---
                if len(fdf) == 0:
                    return _zero_results_message(ent, question)

                # --- Groupby checks FIRST (before total/average) ---
                if "by status" in q or "per status" in q:
                    result = fdf.groupby(col["status"])[actual_col].sum().sort_values(ascending=False)
                    lines = [f"- {s}: ${v:,.2f}" for s, v in result.items()]
                    return f"**{display} by Status{filter_desc}:**\n" + "\n".join(lines)

                if "by region" in q or "by country" in q:
                    result = fdf.groupby(col["region"])[actual_col].sum().sort_values(ascending=False)
                    lines = [f"- {r}: ${v:,.2f}" for r, v in result.items()]
                    return f"**{display} by Country{filter_desc}:**\n" + "\n".join(lines)

                if "by type" in q or "by claim type" in q:
                    result = fdf.groupby(col["claim_type"])[actual_col].sum().sort_values(ascending=False)
                    lines = [f"- {t}: ${v:,.2f}" for t, v in result.items()]
                    return f"**{display} by Claim Type{filter_desc}:**\n" + "\n".join(lines)

                # Synonym-aware "by X" groupby (catches "by adjuster", "by broker", etc.)
                by_match = re.search(r'\bby\s+(.+?)(?:\s+for\b|\s+in\b|\s+where\b|\?|$)', q)
                if by_match:
                    by_phrase = by_match.group(1).strip()
                    for syn, grp_col_name in _SYNONYM_TO_COLUMN.items():
                        if syn in by_phrase and grp_col_name in fdf.columns:
                            agg = "mean" if ("average" in q or "avg" in q or "mean" in q) else "sum"
                            result = fdf.groupby(grp_col_name)[actual_col].agg(agg).sort_values(ascending=False)
                            lines = [f"- {g}: ${v:,.2f}" for g, v in result.head(15).items()]
                            agg_label = "Average" if agg == "mean" else display
                            return f"**{agg_label} by {grp_col_name}{filter_desc}:**\n" + "\n".join(lines)

                # --- Aggregate checks (no groupby) ---
                if "average" in q or "avg" in q or "mean" in q:
                    val = fdf[actual_col].mean()
                    return f"Average {display}{filter_desc}: **${val:,.2f}**"

                # Default: show total
                val = fdf[actual_col].sum()
                return f"Total {display}{filter_desc}: **${val:,.2f}**"

    # --- Status count (generic) ---
    # Skip if user wants "by X" grouping or "top N" — those are handled later
    _has_groupby = ("by " in q and resolve_column_synonym(q.split("by ")[-1].lower(), set(df.columns) if df is not None else None)) if "by " in q else False
    _has_top = bool(re.search(r'\btop\s+\d+', q))
    if ("how many" in q or _has_word("count")) and not _has_groupby and not _has_top:
        # Detect status keyword for labeling
        detected_status = None
        for status in ["open", "closed", "pending", "rejected", "under review"]:
            if status in q:
                detected_status = status.title()
                break

        # Try _apply_filters to handle combined filters (status+region etc.)
        fdf = _apply_filters(df) if df is not None else None
        if fdf is not None and len(fdf) == 0:
            return _zero_results_message(ent, question)
        if fdf is not None and len(fdf) < len(df):
            label = f"{detected_status} " if detected_status else "matching "
            return f"There are **{len(fdf):,}** {label}claims in the current dataset."

        # Simple status count from summary
        if detected_status:
            count = summary["status_counts"].get(detected_status, 0)
            return f"There are **{count:,}** {detected_status} claims in the current dataset."
        if "claim" in q:
            return f"There are **{summary['total_claims']:,}** claims in the current dataset."

    # --- Total value ---
    if "total" in q and ("value" in q or "amount" in q or "claim" in q):
        fdf = _apply_filters(df) if df is not None else None
        if fdf is not None and len(fdf) == 0:
            return _zero_results_message(ent, question)
        if fdf is not None and len(fdf) < len(df):
            filter_desc = f" ({len(fdf):,} matching claims)"
            return (
                f"Total claim value{filter_desc}: **${fdf[col['claim_amount']].sum():,.2f}**\n\n"
                f"- Total paid: ${fdf[col['paid_amount']].sum():,.2f}\n"
                f"- Total reserves: ${fdf[col['reserve_amount']].sum():,.2f}"
            )
        return (
            f"The total claim value across all {summary['total_claims']:,} claims is "
            f"**${summary['total_claim_amount']:,.2f}**.\n\n"
            f"- Total paid: ${summary['total_paid_amount']:,.2f}\n"
            f"- Total reserves: ${summary['total_reserve_amount']:,.2f}"
        )

    # --- Average ---
    if "average" in q or "avg" in q:
        # "days open" is a metric name, not a status filter — detect it first
        is_days_query = "day" in q or "life" in q or "claim life" in q or (
            "open" in q and ("day" in q or "long" in q or "average" in q)
        )

        if is_days_query:
            # For "average days open", only apply filters that aren't status="open"
            # since "open" here means the metric, not a status filter
            return f"The average number of days a claim is open is **{summary['avg_days_open']}** days."

        fdf = _apply_filters(df) if df is not None else None
        filter_desc = f" ({len(fdf):,} matching claims)" if fdf is not None and len(fdf) < len(df) else ""

        if fdf is not None and len(fdf) < len(df):
            avg_val = round(fdf[col["claim_amount"]].mean(), 2)
            return f"Average claim value{filter_desc}: **${avg_val:,.2f}**."
        return f"The average claim value is **${summary['avg_claim_amount']:,.2f}**."

    # --- Fix 5: Multi-dimensional pivot ("by X and by Y" / "per X and per Y") ---
    if df is not None and col is not None:
        _pivot_match = re.search(
            r'\bby\s+(.+?)\s+(?:and\s+by|,\s*by|\s+and)\s+(.+?)(?:\?|\.|$|\s+for\s|\s+where\s)',
            q,
        )
        if not _pivot_match:
            _pivot_match = re.search(
                r'\bper\s+(.+?)\s+and\s+per\s+(.+?)(?:\?|\.|$)',
                q,
            )
        if _pivot_match:
            _a_phrase = _pivot_match.group(1).strip()
            _b_phrase = _pivot_match.group(2).strip()
            _a_res = resolve_column_synonym(_a_phrase, set(df.columns))
            _b_res = resolve_column_synonym(_b_phrase, set(df.columns))
            _col_a = next(iter(_a_res), None)
            _col_b = next(iter(_b_res), None)
            if _col_a and _col_b and _col_a != _col_b:
                fdf = _apply_filters(df)
                if len(fdf) > 0:
                    _pivot = fdf.groupby([_col_a, _col_b]).size().unstack(fill_value=0)
                    _cols = list(_pivot.columns)
                    _header = f"| {_col_a} \\ {_col_b} | " + " | ".join(str(c) for c in _cols) + " |"
                    _sep = "|" + "|".join(["---"] * (len(_cols) + 1)) + "|"
                    _rows = []
                    for _idx, _row in _pivot.iterrows():
                        _rows.append(
                            f"| {_idx} | " + " | ".join(f"{int(v):,}" for v in _row.values) + " |"
                        )
                    _filter_desc = f" ({len(fdf):,} matching)" if len(fdf) < len(df) else ""
                    return (
                        f"**Claims by {_col_a} and {_col_b}{_filter_desc}:**\n\n"
                        + "\n".join([_header, _sep] + _rows)
                    )

    # --- Fix 1b: Grouped bottom-N / least / fewest (single-dimension) ---
    # e.g. "Which Major LOB has the least open claims?"
    if df is not None and col is not None and any(
        w in q for w in ["least", "fewest", "lowest", "smallest", "worst", "bottom"]
    ):
        _matched = resolve_column_synonym(q, set(df.columns))
        _groupable_b = {
            "Responsible Adjuster", "Policy Holder Name", "Producer Name",
            "Claim Office", "Country", "Major LOB", "Minor LOB", "Executive LOB",
            "Cause Of Loss Descr", "Condition Injury Damage Name",
            "Catastrophe Description", "Coverage Code", "Business Entity",
            "Location of Loss", "Claim Status Derived",
        }
        _grp_col = None
        for _mc in _matched:
            if _mc in _groupable_b:
                _grp_col = _mc
                break
        if _grp_col:
            fdf = _apply_filters(df)
            if len(fdf) > 0:
                # Detect financial metric
                _fin_col_b = None
                _fin_label_b = None
                for _kw, (_cfg, _disp) in [
                    ("outstanding reserve", ("outstanding_reserve_usd", "Outstanding Reserve USD")),
                    ("incurred", ("incurred_usd", "Incurred USD")),
                    ("indemnity", ("indemnity_paid_usd", "Indemnity Paid USD")),
                    ("expense", ("expense_paid_usd", "Expense Paid USD")),
                    ("reserve", ("outstanding_reserve_usd", "Outstanding Reserve USD")),
                ]:
                    if _kw in q:
                        _actual = col.get(_cfg, _disp)
                        if _actual in fdf.columns:
                            _fin_col_b = _actual
                            _fin_label_b = _disp
                            break
                _top_n_m = re.search(r'(?:bottom|least|lowest|fewest|smallest)\s+(\d+)', q)
                _n = int(_top_n_m.group(1)) if _top_n_m else 1
                _filter_desc = f" ({len(fdf):,} matching)" if len(fdf) < len(df) else ""
                if _fin_col_b:
                    _res = fdf.groupby(_grp_col)[_fin_col_b].sum().sort_values(ascending=True).head(_n)
                    _lines = [f"- {g}: ${v:,.2f}" for g, v in _res.items()]
                    if _n == 1 and not _res.empty:
                        _g, _v = _res.index[0], _res.iloc[0]
                        return f"**{_g}** has the least {_fin_label_b} at **${_v:,.2f}**{_filter_desc}."
                    return f"**Bottom {_n} {_grp_col} by {_fin_label_b}{_filter_desc}:**\n" + "\n".join(_lines)
                else:
                    _res = fdf.groupby(_grp_col)[col["claim_id"]].count().sort_values(ascending=True).head(_n)
                    if _n == 1 and not _res.empty:
                        _g, _v = _res.index[0], _res.iloc[0]
                        return f"**{_g}** has the fewest claims with **{_v:,}** claims{_filter_desc}."
                    _lines = [f"- {g}: {c:,}" for g, c in _res.items()]
                    return f"**Bottom {_n} {_grp_col} by Claim Count{_filter_desc}:**\n" + "\n".join(_lines)

    # --- Contributing Factor breakdown ---
    if df is not None and col is not None and (
        "contributing factor" in q or "contributing" in q and "factor" in q
    ):
        cf_col = col.get("contributing_factor_descr", "Contributing Factor Descr")
        if cf_col in df.columns:
            fdf = _apply_filters(df)
            filter_desc = f" ({len(fdf):,} matching)" if len(fdf) < len(df) else ""
            result = fdf.groupby(cf_col)[col["claim_id"]].count().sort_values(ascending=False)
            lines = [f"- {c}: {cnt:,}" for c, cnt in result.items()]
            return f"**Claims by Contributing Factor{filter_desc}:**\n" + "\n".join(lines)

    # --- Cause of loss breakdown (explicit phrases only) ---
    if df is not None and col is not None and (
        "cause of loss" in q or "loss cause" in q
    ):
        cause_col = col.get("cause_of_loss_descr", "Cause Of Loss Descr")
        if cause_col in df.columns:
            fdf = _apply_filters(df)
            filter_desc = f" ({len(fdf):,} matching)" if len(fdf) < len(df) else ""
            result = fdf.groupby(cause_col)[col["claim_id"]].count().sort_values(ascending=False)
            lines = [f"- {c}: {cnt:,}" for c, cnt in result.items()]
            return f"**Claims by Cause of Loss{filter_desc}:**\n" + "\n".join(lines)

    # --- LOB breakdown ---
    if df is not None and col is not None and (
        "lob" in q or "line of business" in q
    ):
        lob_col = col.get("executive_lob", "Executive LOB")
        if lob_col in df.columns:
            fdf = _apply_filters(df)
            filter_desc = f" ({len(fdf):,} matching)" if len(fdf) < len(df) else ""
            result = fdf.groupby(lob_col)[col["claim_id"]].count().sort_values(ascending=False)
            lines = [f"- {l}: {cnt:,}" for l, cnt in result.items()]
            return f"**Claims by Line of Business{filter_desc}:**\n" + "\n".join(lines)

    # --- Country / Region breakdown ---
    if df is not None and col is not None and (
        _has_word("country") or _has_word("countries") or _has_word("region") or _has_word("regions")
    ):
        fdf = _apply_filters(df)
        filter_desc = f" ({len(fdf):,} matching)" if len(fdf) < len(df) else ""
        result = fdf.groupby(col["region"])[col["claim_id"]].count().sort_values(ascending=False)

        # Superlative detection: "which region has the most/least claims?"
        _superlative_most = any(w in q for w in ["most", "highest", "largest", "biggest", "top"])
        _superlative_least = any(w in q for w in ["least", "lowest", "smallest", "fewest", "bottom"])
        if _superlative_most and not result.empty:
            top_region = result.index[0]
            top_count = result.iloc[0]
            return f"**{top_region}** has the most claims with **{top_count:,}** claims{filter_desc}."
        if _superlative_least and not result.empty:
            bot_region = result.index[-1]
            bot_count = result.iloc[-1]
            return f"**{bot_region}** has the fewest claims with **{bot_count:,}** claims{filter_desc}."

        lines = [f"- {r}: {c:,}" for r, c in result.items()]
        return f"**Claims by Country{filter_desc}:**\n" + "\n".join(lines)

    # --- Smart "biggest / top / most / contributing factor" detector ---
    # Must be ABOVE generic breakdown handlers to catch "breakdown by contributing factor"
    if df is not None and col is not None and any(
        w in q for w in ["biggest", "largest", "top", "most", "highest",
                         "contributing", "driver", "factor", "volume",
                         "dominant", "major", "leading"]
    ):
        fdf = _apply_filters(df)
        filter_desc = f" (filtered to {len(fdf):,} claims)" if len(fdf) < len(df) else ""

        # Extract "top N" count
        top_n_match = re.search(r'top\s+(\d+)', q)
        top_n = int(top_n_match.group(1)) if top_n_match else 5

        # Check if user specified a specific dimension via synonyms
        # e.g. "top 5 adjusters", "top brokers by claim count"
        matched_syn_cols = resolve_column_synonym(q, set(fdf.columns))
        # Filter to only groupable (categorical) columns, not financials/dates
        _groupable = {
            "Responsible Adjuster", "Policy Holder Name", "Producer Name",
            "Claim Office", "Country", "Major LOB", "Minor LOB", "Executive LOB",
            "Cause Of Loss Descr", "Condition Injury Damage Name",
            "Catastrophe Description", "Coverage Code", "Business Entity",
            "Location of Loss", "Claim Status Derived", "Reserving Class",
            "Reserving Line",
        }
        specific_col = None
        for mc in matched_syn_cols:
            if mc in _groupable:
                specific_col = mc
                break

        if specific_col:
            # Single-dimension "top N by X"
            # Detect if user wants financial metric or count
            fin_col_name = None
            for fin_kw, (cfg_key, _disp) in _fin_columns.items():
                if fin_kw in q:
                    candidate = col.get(cfg_key, _disp)
                    if candidate in fdf.columns:
                        fin_col_name = candidate
                        break

            if fin_col_name:
                result = fdf.groupby(specific_col)[fin_col_name].sum().sort_values(ascending=False).head(top_n)
                lines = [f"- {g}: ${v:,.2f}" for g, v in result.items()]
                return f"**Top {top_n} {specific_col} by {fin_col_name}{filter_desc}:**\n" + "\n".join(lines)
            else:
                result = fdf.groupby(specific_col)[col["claim_id"]].count().sort_values(ascending=False).head(top_n)
                lines = [f"- {g}: {c:,}" for g, c in result.items()]
                return f"**Top {top_n} {specific_col} by Claim Count{filter_desc}:**\n" + "\n".join(lines)

        # Fallback: show top contributors across multiple dimensions
        sections = []

        # By claim type
        type_result = fdf.groupby(col["claim_type"])[col["claim_id"]].count().sort_values(ascending=False).head(5)
        lines = [f"- {t}: {c:,}" for t, c in type_result.items()]
        sections.append("**By Claim Type:**\n" + "\n".join(lines))

        # By cause of loss
        cause_col = col.get("cause_of_loss_descr", "Cause Of Loss Descr")
        if cause_col in fdf.columns:
            cause_result = fdf.groupby(cause_col)[col["claim_id"]].count().sort_values(ascending=False).head(5)
            lines = [f"- {c}: {cnt:,}" for c, cnt in cause_result.items()]
            sections.append("**By Cause of Loss:**\n" + "\n".join(lines))

        # By country
        region_result = fdf.groupby(col["region"])[col["claim_id"]].count().sort_values(ascending=False).head(5)
        lines = [f"- {r}: {c:,}" for r, c in region_result.items()]
        sections.append("**By Country:**\n" + "\n".join(lines))

        # By LOB
        lob_col = col.get("executive_lob", "Executive LOB")
        if lob_col in fdf.columns:
            lob_result = fdf.groupby(lob_col)[col["claim_id"]].count().sort_values(ascending=False).head(5)
            lines = [f"- {l}: {cnt:,}" for l, cnt in lob_result.items()]
            sections.append("**By Line of Business:**\n" + "\n".join(lines))

        total_label = f"{len(fdf):,}" if len(fdf) < len(df) else f"{summary['total_claims']:,}"
        return f"**Top Contributing Factors by Claim Volume ({total_label} total){filter_desc}:**\n\n" + "\n\n".join(sections)

    # --- Region breakdown ---
    if "region" in q and "breakdown" in q:
        lines = [f"- {r}: {c:,}" for r, c in summary["region_counts"].items()]
        return "**Claims by Region:**\n" + "\n".join(lines)

    # --- Type breakdown (must be above status to avoid "type breakdown" -> status) ---
    if "type" in q and ("breakdown" in q or "by type" in q):
        lines = [f"- {t}: {c:,}" for t, c in summary["type_counts"].items()]
        return "**Claims by Type:**\n" + "\n".join(lines)

    # --- Status breakdown ---
    if "status" in q or ("breakdown" in q and "cause" not in q and "lob" not in q
                         and "country" not in q and "type" not in q):
        lines = [f"- {s}: {c:,}" for s, c in summary["status_counts"].items()]
        return "**Claims by Status:**\n" + "\n".join(lines)

    # --- Type (generic, no "breakdown" keyword) ---
    if "type" in q:
        lines = [f"- {t}: {c:,}" for t, c in summary["type_counts"].items()]
        return "**Claims by Type:**\n" + "\n".join(lines)

    # --- Fallback full summary ---
    return (
        f"**Claims Summary** (as of {summary.get('data_loaded_at', 'unknown')}):\n\n"
        f"- Total claims: {summary['total_claims']:,}\n"
        f"- Total value: ${summary['total_claim_amount']:,.2f}\n"
        f"- Total paid: ${summary['total_paid_amount']:,.2f}\n"
        f"- Total reserves: ${summary['total_reserve_amount']:,.2f}\n"
        f"- Average claim: ${summary['avg_claim_amount']:,.2f}\n"
        f"- Average days open: {summary['avg_days_open']} days\n"
        f"- Date range: {summary['date_range_start']} -> {summary['date_range_end']}"
    )


# ---------------------------------------------------------------------------
# Lookup handler
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Insurance abbreviation / slang mappings
# ---------------------------------------------------------------------------
_CLAIM_TYPE_ABBREVS = {
    "b.i.": "bodily injury", "bi": "bodily injury",
    "p.d.": "property damage", "pd": "property damage",
    "g.l.": "general liability", "gl": "general liability",
    "p.i.": "professional indemnity", "pi": "professional indemnity",
    "w.c.": "workers compensation", "wc": "workers compensation",
    "e.l.": "employers liability", "el": "employers liability",
    "b.i": "business interruption",
}

_FINANCIAL_SLANG = {
    "outside counsel": "expense_paid_usd",
    "burned on": "expense_paid_usd",
    "legal fees": "expense_paid_usd",
    "legal spend": "expense_paid_usd",
    "defense costs": "expense_paid_usd",
    "alae": "expense_paid_usd",
    "subro": "recoveries_usd",
    "subrogation": "recoveries_usd",
    "recovery": "recoveries_usd",
    "payout": "indemnity_paid_usd",
    "settlement": "indemnity_paid_usd",
    "indemnity": "indemnity_paid_usd",
    "total incurred": "incurred_usd",
    "reserves": "outstanding_reserve_usd",
}

_INJURY_KEYWORDS = {
    "c-spine": "c-spine", "cervical": "c-spine", "cspine": "c-spine",
    "fracture": "fracture", "fractured": "fracture", "broken": "fracture",
    "concussion": "concussion", "head injury": "concussion",
    "amputation": "amputation", "amputat": "amputation",
    "burn": "burn", "laceration": "laceration", "contusion": "contusion",
    "sprain": "sprain", "strain": "strain", "herniat": "herniat",
    "dislocation": "dislocation", "whiplash": "whiplash",
    "tbi": "brain", "traumatic brain": "brain",
}


# ---------------------------------------------------------------------------
# Fuzzy Descriptive Lookup
# ---------------------------------------------------------------------------
def handle_fuzzy_lookup(
    question: str,
    df: pd.DataFrame,
    col: dict,
) -> Optional[str]:
    """Find a claim by description across multiple columns using fuzzy matching.

    Extracts entities like company names, adjuster names, injury types, claim
    type abbreviations from natural language and progressively filters.

    Returns:
        Formatted answer string if matches found, or None to fall through.
    """
    if df is None or col is None:
        return None

    q = question.lower()
    mask = pd.Series(True, index=df.index)
    filters_applied = []

    # --- Expand abbreviations for matching context ---
    q_expanded = q
    for abbrev, full in _CLAIM_TYPE_ABBREVS.items():
        if abbrev in q:
            q_expanded = q_expanded.replace(abbrev, full)

    # --- 1. Business Entity / Company Name ---
    entity_col = col.get("business_entity", "Business Entity")
    ph_col = col.get("policy_holder_name", "Policy Holder Name")
    company_match = re.search(
        r'(?:under|for|from|at|handled by|with|client)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]*)*'
        r'(?:\s+(?:Inc|Ltd|Corp|LLC|GmbH|SA|AG|NV|BV|SE|plc)\.?)?)',
        question
    )
    if not company_match:
        # Try looser pattern for "Acme Corp" anywhere
        company_match = re.search(
            r'\b([A-Z][a-z]+\s+(?:Corp|Inc|Ltd|LLC|GmbH|Insurance|Ins)\b\.?)',
            question
        )
    if company_match:
        company_name = company_match.group(1).strip().rstrip(".")
        for target_col in [entity_col, ph_col]:
            if target_col in df.columns:
                # Try full name first, then first word
                for search_term in [company_name, company_name.split()[0]]:
                    company_mask = df[target_col].str.contains(
                        re.escape(search_term), case=False, na=False
                    )
                    match_pct = company_mask.sum() / len(df)
                    # Skip if matches >80% of records (not a useful filter)
                    if company_mask.any() and match_pct < 0.8:
                        mask &= company_mask
                        filters_applied.append(f"Company ~ '{search_term}'")
                        break
                break

    # --- 2. Responsible Adjuster / Handler name ---
    adjuster_col = col.get("responsible_adjuster", "Responsible Adjuster")
    # Extract person names: "handled by Sarah", "adjuster Sarah", "sarah's"
    adj_match = re.search(
        r"(?:handled by|adjuster|by|assigned to)\s+([A-Z][a-z]+)",
        question, re.IGNORECASE
    )
    if adj_match and adjuster_col in df.columns:
        adj_name = adj_match.group(1)
        adj_mask = df[adjuster_col].str.contains(adj_name, case=False, na=False)
        if adj_mask.any():
            mask &= adj_mask
            filters_applied.append(f"Adjuster ~ '{adj_name}'")

    # --- 3. Claim Type / LOB (with abbreviation expansion) ---
    claim_type_col = col.get("claim_type", "Minor LOB")
    major_lob_col = col.get("major_lob", "Major LOB")
    for abbrev, full in _CLAIM_TYPE_ABBREVS.items():
        if abbrev in q:
            for target_col in [claim_type_col, major_lob_col]:
                if target_col in df.columns:
                    type_mask = df[target_col].str.contains(
                        re.escape(full), case=False, na=False
                    )
                    if type_mask.any():
                        mask &= type_mask
                        filters_applied.append(f"Type ~ '{full}'")
                        break
            break  # Only apply first matching abbreviation

    # --- 4. Condition / Injury / Damage ---
    cid_col = col.get("condition_injury_damage_name", "Condition Injury Damage Name")
    cause_col = col.get("cause_of_loss_descr", "Cause Of Loss Descr")
    if cid_col in df.columns:
        for keyword, search_term in _INJURY_KEYWORDS.items():
            if keyword in q:
                inj_mask = df[cid_col].str.contains(search_term, case=False, na=False)
                if inj_mask.any():
                    mask &= inj_mask
                    filters_applied.append(f"Injury ~ '{search_term}'")
                    break

    # --- 5. "Big" / high-value indicator ---
    if re.search(r'\bbig\b|\blarge\b|\bhuge\b|\bmajor\b|\bhigh.?value\b', q):
        # Sort by incurred descending later, and/or filter top quartile
        amount_col = col.get("incurred_usd", col.get("claim_amount", "Incurred USD"))
        if amount_col in df.columns:
            q75 = df[amount_col].quantile(0.75)
            mask &= df[amount_col] >= q75
            filters_applied.append(f"High-value (≥${q75:,.0f})")

    # --- 6. Status keywords (for context, not filtering) ---
    # "current status" just means show the status field, don't filter

    # --- Apply mask ---
    if not filters_applied:
        return None  # No fuzzy criteria detected, fall through

    matches = df[mask]

    if len(matches) == 0:
        return (
            f"No claims found matching your description:\n"
            + "\n".join(f"- {f}" for f in filters_applied)
            + "\n\nTry relaxing some criteria or check spelling."
        )

    # --- Detect what info the user wants ---
    requested_fields = []
    wants_status = any(w in q for w in ["status", "curret", "current"])

    for slang, cfg_key in _FINANCIAL_SLANG.items():
        if slang in q:
            actual_col = col.get(cfg_key, "")
            if actual_col in df.columns:
                requested_fields.append((cfg_key, actual_col, slang.title()))
            break

    # Always include these base fields
    base_fields = [
        ("claim_id", col.get("claim_id", "Claim Number"), "Claim Number"),
        ("status", col.get("status", "Claim Status Derived"), "Status"),
        ("claim_type", col.get("claim_type", "Minor LOB"), "Type"),
    ]

    # Add business entity
    if entity_col in df.columns:
        base_fields.append(("business_entity", entity_col, "Entity"))
    # Add condition injury
    if cid_col in df.columns:
        base_fields.append(("cid", cid_col, "Injury/Condition"))

    # Sort by incurred descending (biggest first, as user asked for "big")
    amount_col = col.get("incurred_usd", col.get("claim_amount", "Incurred USD"))
    if amount_col in matches.columns:
        matches = matches.sort_values(amount_col, ascending=False)

    # --- Format response ---
    if len(matches) == 1:
        r = matches.iloc[0]
        claim_num = r.get(col.get("claim_id", ""), "N/A")
        lines = [f"**Found Claim {claim_num}**", ""]
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")

        # Show all meaningful columns
        show_cols = [
            ("Claim Number", col.get("claim_id", "")),
            ("Status", col.get("status", "")),
            ("Type (Minor LOB)", col.get("claim_type", "")),
            ("Major LOB", col.get("major_lob", "")),
            ("Entity", entity_col),
            ("Country", col.get("region", "")),
            ("Injury/Condition", cid_col),
            ("Cause of Loss", cause_col),
            ("Incurred USD", col.get("incurred_usd", "")),
            ("Indemnity Paid USD", col.get("indemnity_paid_usd", "")),
            ("Expense Paid USD", col.get("expense_paid_usd", "")),
            ("Outstanding Reserve", col.get("outstanding_reserve_usd", "")),
            ("Reported Date", col.get("submitted_date", "")),
            ("Days Open", col.get("days_open", "")),
        ]
        for label, c_name in show_cols:
            if c_name in r.index:
                val = r[c_name]
                if pd.isna(val):
                    val = "N/A"
                elif isinstance(val, float):
                    val = f"${val:,.2f}" if any(kw in label.lower() for kw in ["usd","paid","reserve","incurred"]) else f"{val:,.0f}"
                else:
                    val = str(val)[:50]
                lines.append(f"| {label} | {val} |")

        # Highlight specifically requested info
        if wants_status:
            status_col_name = col.get("status", "Claim Status Derived")
            if status_col_name in r.index:
                lines.append(f"\n➜ **Current Status**: {r[status_col_name]}")
        if requested_fields:
            lines.append("")
            for _, fc, label in requested_fields:
                if fc in r.index:
                    val = r[fc]
                    if isinstance(val, (int, float)) and not pd.isna(val):
                        lines.append(f"➜ **{label}**: ${val:,.2f}")
                    else:
                        lines.append(f"➜ **{label}**: {val}")

        lines.append(f"\n_Matched on: {', '.join(filters_applied)}_")
        return "\n".join(lines)

    elif len(matches) <= 10:
        # Show summary table and ask to clarify if > 1
        lines = [
            f"**Found {len(matches)} claims matching your description:**",
            f"_Filters: {', '.join(filters_applied)}_\n",
        ]
        lines.append("| # | Claim | Status | Type | Entity | Injury | Incurred |")
        lines.append("|---|-------|--------|------|--------|--------|----------|")

        for i, (_, r) in enumerate(matches.head(10).iterrows(), 1):
            cnum = r.get(col.get("claim_id", ""), "?")
            stat = r.get(col.get("status", ""), "?")
            ctype = str(r.get(col.get("claim_type", ""), "?"))[:20]
            entity = str(r.get(entity_col, "?"))[:20] if entity_col in r.index else "?"
            injury = str(r.get(cid_col, "?"))[:20] if cid_col in r.index else "?"
            inc = r.get(col.get("incurred_usd", ""), 0)
            inc_str = f"${inc:,.2f}" if isinstance(inc, (int, float)) and not pd.isna(inc) else "N/A"
            lines.append(f"| {i} | {cnum} | {stat} | {ctype} | {entity} | {injury} | {inc_str} |")

        # Show requested info summaries
        if wants_status and len(matches) > 1:
            status_col_name = col.get("status", "Claim Status Derived")
            if status_col_name in matches.columns:
                status_dist = matches[status_col_name].value_counts()
                dist_str = ", ".join(f"{s}: {c:,}" for s, c in status_dist.items())
                lines.append(f"\n➜ **Status breakdown**: {dist_str}")

        if requested_fields:
            lines.append("")
            for _, fc, label in requested_fields:
                if fc in matches.columns:
                    numeric = pd.to_numeric(matches[fc], errors='coerce')
                    lines.append(f"➜ **{label}** across matches: "
                                 f"${numeric.sum():,.2f} total, "
                                 f"${numeric.mean():,.2f} avg")

        if len(matches) > 1:
            lines.append("\n_Multiple matches found — can you provide the Claim Number to narrow it down?_")

        return "\n".join(lines)

    else:
        # Many matches — show top 10 by value with requested fields
        lines = [
            f"**{len(matches):,} claims** match your description:",
            "_" + ", ".join(filters_applied) + "_\n",
            "Here are the **top 10 by value**:\n",
            "| # | Claim | Status | Type | Entity | Injury | Incurred | Expense Paid |",
            "|---|-------|--------|------|--------|--------|----------|-------------|",
        ]

        expense_col = col.get("expense_paid_usd", "Expense Paid USD")
        for i, (_, r) in enumerate(matches.head(10).iterrows(), 1):
            cnum = r.get(col.get("claim_id", ""), "?")
            stat = r.get(col.get("status", ""), "?")
            ctype = str(r.get(col.get("claim_type", ""), "?"))[:18]
            entity = str(r.get(entity_col, "?"))[:18] if entity_col in r.index else "?"
            injury = str(r.get(cid_col, "?"))[:18] if cid_col in r.index else "?"
            inc = r.get(col.get("incurred_usd", ""), 0)
            inc_str = f"${inc:,.2f}" if isinstance(inc, (int, float)) and not pd.isna(inc) else "N/A"
            exp = r.get(expense_col, 0) if expense_col in r.index else 0
            exp_str = f"${exp:,.2f}" if isinstance(exp, (int, float)) and not pd.isna(exp) else "N/A"
            lines.append(f"| {i} | {cnum} | {stat} | {ctype} | {entity} | {injury} | {inc_str} | {exp_str} |")

        # Show requested info summaries
        if wants_status:
            status_col = col.get("status", "Claim Status Derived")
            if status_col in matches.columns:
                status_dist = matches[status_col].value_counts()
                dist_str = ", ".join(f"{s}: {c:,}" for s, c in status_dist.items())
                lines.append(f"\n➜ **Status breakdown**: {dist_str}")

        if requested_fields:
            lines.append("")
            for _, fc, label in requested_fields:
                if fc in matches.columns:
                    numeric = pd.to_numeric(matches[fc], errors='coerce')
                    lines.append(f"➜ **{label}** across {len(matches):,} matches: "
                                 f"${numeric.sum():,.2f} total, "
                                 f"${numeric.mean():,.2f} avg")

        lines.append("\n_Can you narrow it down with a Claim Number, country, date, or more details?_")
        return "\n".join(lines)


def handle_lookup(claim_id: str, df: pd.DataFrame, col: dict,
                  policy_id: str = None) -> str:
    """Look up a specific claim by ID or policy number and return a markdown table.

    Args:
        claim_id:  Claim ID string (e.g. "CLM0000042"), already extracted
                   by QueryAnalyzer.
        df:        Full claims DataFrame.
        col:       Column mapping dict.
        policy_id: Policy number (e.g. "POL-GL-554321"), optional.

    Returns:
        Markdown-formatted claim detail table, or not-found message.
    """
    row = None

    # Try claim_id first
    if claim_id:
        claim_id = claim_id.upper()
        row = df[df[col["claim_id"]] == claim_id]
        if row.empty:
            row = None

    # Try policy_id if no claim found
    if row is None and policy_id:
        policy_id = policy_id.upper()
        pol_col = col.get("policy_number", "Policy Number")
        if pol_col in df.columns:
            row = df[df[pol_col].astype(str).str.upper() == policy_id]
            if row.empty:
                row = None

    if row is None:
        if claim_id:
            return f"Claim **{claim_id}** was not found in the current dataset."
        if policy_id:
            return f"Policy **{policy_id}** was not found in the current dataset."
        return "I couldn't find a Claim ID or Policy Number in your question. Please include one (e.g. CLM0000042 or POL-GL-554321)."

    r = row.iloc[0]

    def s(field):
        val = r.get(col.get(field, ""), "N/A")
        return "N/A" if pd.isna(val) else str(val)

    def c(field):
        try:
            return f"${float(r.get(col.get(field, ''), 0)):,.2f}"
        except Exception:
            return "N/A"

    # Get actual claim_id from row data (in case lookup was by policy)
    display_claim_id = claim_id or str(r.get(col.get("claim_id", ""), "N/A"))

    closed_val = s("closed_date")
    closed_display = closed_val[:10] if closed_val != "N/A" else "Still open"

    lines = [
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Claim ID | {display_claim_id} |",
        f"| Status | {s('status')} |",
        f"| Type | {s('claim_type')} |",
        f"| Claimant | {s('claimant_name')} |",
        f"| Region | {s('region')} |",
        f"| Submitted | {s('submitted_date')[:10]} |",
        f"| Closed | {closed_display} |",
        f"| Claim Amount | {c('claim_amount')} |",
        f"| Paid Amount | {c('paid_amount')} |",
        f"| Reserve | {c('reserve_amount')} |",
        f"| Days Open | {s('days_open')} |",
    ]

    return f"**Claim {display_claim_id}**\n\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# RAG Pipeline
# ---------------------------------------------------------------------------

class RAGPipeline:
    """Orchestrates question-answering: QueryAnalyzer -> route -> answer.

    Flow:
        1. QueryAnalyzer classifies intent + extracts entities
        2. Route: aggregation -> handle_aggregation
                  lookup      -> handle_lookup
                  search      -> pre-filter -> FAISS -> LLM
    """

    def __init__(self, loader, search_engine, llm):
        """
        Args:
            loader:        ClaimsDataLoader instance (already loaded).
            search_engine: ClaimsSearchEngine instance (already built).
            llm:           ClaimsLLM instance.
        """
        self.loader = loader
        self.search_engine = search_engine
        self.llm = llm
        self.analyzer = QueryAnalyzer()

    # ------------------------------------------------------------------
    def ask(self, question: str) -> Dict[str, Any]:
        """Answer a natural language question about claims data.

        Returns:
            Dict with keys: answer, question_type, sources, entities.
        """
        if not question or not question.strip():
            return {
                "answer": "Please ask a question.",
                "question_type": "none",
                "sources": [],
                "entities": {},
            }

        question = question.strip()
        logger.info(f"Question received: '{question}'")

        # Step 1: Analyze intent + entities
        analysis = self.analyzer.analyze(question)
        intent = analysis.get("intent", "search")
        entities = {
            "claim_id": analysis.get("claim_id"),
            "status": analysis.get("status"),
            "region": analysis.get("region"),
            "claim_type": analysis.get("claim_type"),
            "high_value": analysis.get("high_value", False),
            "date_range": analysis.get("date_range"),
        }

        # Validate LLM entities against actual question text to strip hallucinations
        q_lower = question.lower()
        if entities.get("region"):
            region_str = entities["region"].lower()
            # Check if the region (or its short form) actually appears in question
            region_words = [region_str] + {
                "us": ["us", "usa", "united states", "america"],
                "uk": ["uk", "united kingdom", "britain"],
                "usa": ["us", "usa", "united states"],
                "united states": ["us", "usa", "united states"],
                "united kingdom": ["uk", "united kingdom", "britain"],
            }.get(region_str, [])
            if not any(re.search(rf'\b{re.escape(rw)}\b', q_lower) for rw in region_words):
                logger.info(f"Stripped hallucinated region '{entities['region']}' (not in question)")
                entities["region"] = None

        if entities.get("status"):
            if entities["status"].lower() not in q_lower:
                logger.info(f"Stripped hallucinated status '{entities['status']}' (not in question)")
                entities["status"] = None

        if entities.get("date_range") and isinstance(entities["date_range"], dict):
            # Only keep date_range if question has explicit date/year references
            has_year = bool(re.search(r'\b(20\d{2})\b', q_lower))
            has_date_phrase = any(p in q_lower for p in [
                "last quarter", "this year", "last year", "ytd",
                "last month", "this month",
            ])
            if not has_year and not has_date_phrase:
                logger.info(f"Stripped hallucinated date_range (no date in question)")
                entities["date_range"] = None
        logger.info(f"Intent: {intent} | Entities: {entities}")

        # Step 2: Route by intent

        # --- Guard: Out-of-scope ---
        if intent == "unknown":
            return {
                "answer": (
                    "I'm a specialized **Claims Assistant** — I can only answer questions "
                    "about claims data, policies, reserves, financials, and portfolio metrics.\n\n"
                    "Try asking things like:\n"
                    "- *How many open claims are there?*\n"
                    "- *Total incurred by Major LOB*\n"
                    "- *Show me pending claims in Canada*\n"
                    "- *Top 5 adjusters by claim count*"
                ),
                "question_type": "out_of_scope",
                "sources": [],
                "entities": entities,
            }

        if intent == "aggregation":
            # --- Tier 2: Complexity guardrail ---
            # Some aggregation queries can't be answered by heuristic handlers
            # (derived metrics like reporting lag, ratios, 3+ predicates).
            # Escalate those to the Pandas Agent BEFORE running the heuristic
            # path — otherwise the heuristic returns plausible-but-wrong answers.
            from ai.query_analyzer import assess_query_complexity
            should_escalate, reason = assess_query_complexity(question)
            pandas_failed = False
            pandas_error = ""
            if should_escalate:
                logger.info(f"Complexity guardrail: escalating to Pandas Agent ({reason})")
                try:
                    from ai.pandas_agent import pandas_query
                    ai_cfg = self.loader.config.get("ai", {})
                    pandas_answer = pandas_query(
                        question,
                        self.loader.df,
                        self.loader.col,
                        ollama_model=ai_cfg.get("ollama_model", "llama3.2:3b"),
                        ollama_host=ai_cfg.get("ollama_host", "http://localhost:11434"),
                        llm_timeout=ai_cfg.get("llm_timeout", 15),
                        provider=ai_cfg.get("pandas_agent_provider", "ollama"),
                    )
                    if pandas_answer:
                        # Clarification short-circuit — agent asked user a question
                        # instead of writing code. Surface it with a distinct type.
                        if pandas_answer.startswith("__CLARIFY__:"):
                            return {
                                "answer": pandas_answer[len("__CLARIFY__:"):].strip(),
                                "question_type": "clarification",
                                "sources": [],
                                "entities": entities,
                                "escalation_reason": reason,
                            }
                        # Explicit agent failure — treat as fail (do NOT return
                        # it as a pandas_agent success). Fall through to the
                        # QA-mode / heuristic-fallback logic below.
                        if pandas_answer.startswith("ERROR:"):
                            pandas_failed = True
                            pandas_error = pandas_answer
                            logger.warning(f"Pandas Agent returned failure sentinel: {pandas_error}")
                        else:
                            return {
                                "answer": pandas_answer,
                                "question_type": "pandas_agent",
                                "sources": [],
                                "entities": entities,
                                "escalation_reason": reason,
                            }
                    else:
                        pandas_failed = True
                        pandas_error = "returned None (empty / unparseable)"
                        logger.warning(f"Pandas Agent failed on '{reason}'")
                except Exception as e:
                    pandas_failed = True
                    pandas_error = f"{type(e).__name__}: {e}"
                    logger.warning(f"Pandas Agent threw: {pandas_error}")

            # --- QA mode: surface agent failures explicitly ---
            # When disable_heuristic_fallback is true, DO NOT hide agent
            # failures behind a plausible heuristic answer. Return an
            # agent_error so test harness / humans see the real problem.
            disable_fallback = bool(
                self.loader.config.get("ai", {}).get(
                    "disable_heuristic_fallback", False
                )
            )
            if should_escalate and pandas_failed and disable_fallback:
                return {
                    "answer": (
                        f"AGENT_ERROR: Pandas Agent could not answer this "
                        f"query ({reason}). Reason: {pandas_error}"
                    ),
                    "question_type": "agent_error",
                    "sources": [],
                    "entities": entities,
                    "escalation_reason": reason,
                }

            answer = handle_aggregation(
                question, self.loader.summary,
                self.loader.df, self.loader.col, entities,
            )
            # If the guardrail fired but the agent couldn't compute it, add a
            # transparency note so the user doesn't mistake a heuristic
            # best-effort for the exact answer to a complex query.
            if should_escalate and pandas_failed:
                answer = (
                    f"_⚠️ This query needed {reason} — our precise computation "
                    f"path is unavailable right now. Showing the closest "
                    f"heuristic answer below; treat as approximate._\n\n"
                    + answer
                )
            return {
                "answer": answer,
                "question_type": "aggregation",
                "sources": [],
                "entities": entities,
            }

        if intent == "lookup":
            claim_id = entities.get("claim_id")
            policy_id = analysis.get("policy_id")

            # If no claim_id and no policy_id, try fuzzy descriptive lookup
            if not claim_id and not policy_id:
                fuzzy = handle_fuzzy_lookup(question, self.loader.df, self.loader.col)
                if fuzzy:
                    return {
                        "answer": fuzzy,
                        "question_type": "fuzzy_lookup",
                        "sources": [],
                        "entities": entities,
                    }

            lookup_answer = handle_lookup(claim_id, self.loader.df, self.loader.col,
                                          policy_id=policy_id)

            # Hybrid check: does the question ALSO contain aggregation keywords?
            q_lower = question.lower()
            agg_keywords = [
                "how much", "how many", "total", "average", "subro",
                "recoveries", "reserve", "alae", "expense", "incurred",
                "exposure", "indemnity",
            ]
            has_agg = any(kw in q_lower for kw in agg_keywords)

            if has_agg:
                # Run aggregation too and combine answers
                agg_answer = handle_aggregation(
                    question, self.loader.summary,
                    self.loader.df, self.loader.col, entities,
                )
                answer = lookup_answer + "\n\n---\n\n" + agg_answer
                qtype = "lookup+aggregation"
            else:
                answer = lookup_answer
                qtype = "lookup"

            return {
                "answer": answer,
                "question_type": qtype,
                "sources": [],
                "entities": entities,
            }

        # Step 2.5: Try fuzzy descriptive lookup before FAISS
        # Handles "find that claim where..." / descriptive searches
        fuzzy = handle_fuzzy_lookup(question, self.loader.df, self.loader.col)
        if fuzzy:
            return {
                "answer": fuzzy,
                "question_type": "fuzzy_lookup",
                "sources": [],
                "entities": entities,
            }

        # Step 2.75: Pandas Agent — LLM generates code for complex math
        # Catches queries like "standard deviation", "percentile", "correlation"
        try:
            from ai.pandas_agent import pandas_query
            ai_cfg = self.loader.config.get("ai", {})
            pandas_answer = pandas_query(
                question,
                self.loader.df,
                self.loader.col,
                ollama_model=ai_cfg.get("ollama_model", "llama3.2:3b"),
                ollama_host=ai_cfg.get("ollama_host", "http://localhost:11434"),
                llm_timeout=ai_cfg.get("llm_timeout", 15),
                provider=ai_cfg.get("pandas_agent_provider", "ollama"),
            )
            if pandas_answer:
                if pandas_answer.startswith("__CLARIFY__:"):
                    return {
                        "answer": pandas_answer[len("__CLARIFY__:"):].strip(),
                        "question_type": "clarification",
                        "sources": [],
                        "entities": entities,
                    }
                # Explicit agent failure — propagate as agent_error so the
                # test harness / UI sees the real exception.
                if pandas_answer.startswith("ERROR:"):
                    logger.warning(f"Pandas Agent returned failure sentinel: {pandas_answer}")
                    return {
                        "answer": pandas_answer,
                        "question_type": "agent_error",
                        "sources": [],
                        "entities": entities,
                    }
                return {
                    "answer": pandas_answer,
                    "question_type": "pandas_agent",
                    "sources": [],
                    "entities": entities,
                }
        except Exception as e:
            logger.warning(f"Pandas agent failed: {e}")

        # Step 3: Search path — lazy-build FAISS on first search query
        if not self.search_engine.is_ready:
            logger.info("FAISS index not built yet — building lazily on first search…")
            try:
                from data.text_chunker import dataframe_to_chunks
                chunks = dataframe_to_chunks(self.loader.df, self.loader.col)
                self.search_engine.build(chunks)
                logger.info("FAISS index built lazily ✓")
            except Exception as e:
                logger.error(f"Failed to build FAISS index: {e}")
                return {
                    "answer": f"Search index build failed: {e}",
                    "question_type": "search",
                    "sources": [],
                    "entities": entities,
                }

        # 3a. Pre-filter DataFrame indices by entities
        allowed = self._get_allowed_indices(entities)

        # 3b. FAISS search (filtered or unfiltered)
        if allowed is not None:
            matched_chunks = self.search_engine.search_with_filter(question, allowed)
        else:
            matched_chunks = self.search_engine.search(question)

        # 3c. Score threshold filter
        threshold = self.loader.config.get("ai", {}).get("faiss_score_threshold", 0.35)
        matched_chunks = [c for c in matched_chunks if c.get("score", 0) >= threshold]

        if not matched_chunks:
            return {
                "answer": "I couldn't find any relevant claims for that question.",
                "question_type": "search",
                "sources": [],
                "entities": entities,
            }

        # 3d. Retrieve full rows
        from data.text_chunker import retrieve_rows_from_chunks
        context_rows = retrieve_rows_from_chunks(self.loader.df, matched_chunks)

        # 3e. LLM with retry
        answer = self._ask_llm_with_retry(question, context_rows)

        sources = [c["claim_id"] for c in matched_chunks if "claim_id" in c]
        return {
            "answer": answer,
            "question_type": "search",
            "sources": sources,
            "entities": entities,
        }

    # ------------------------------------------------------------------
    def _get_allowed_indices(self, entities: dict) -> Optional[Set[int]]:
        """Build a set of allowed DataFrame indices from entity filters.

        Applies status, region, claim_type, and high_value filters.

        Returns:
            Set of df.index values, or None if no filters apply.
        """
        df = self.loader.df
        col = self.loader.col
        mask = pd.Series(True, index=df.index)
        has_filter = False

        if entities.get("status"):
            mask &= df[col["status"]].str.lower() == entities["status"].lower()
            has_filter = True

        if entities.get("region"):
            mask &= df[col["region"]].str.lower() == entities["region"].lower()
            has_filter = True

        if entities.get("claim_type"):
            mask &= df[col["claim_type"]].str.lower() == entities["claim_type"].lower()
            has_filter = True

        if entities.get("high_value"):
            threshold = self.loader.config.get("notifications", {}).get(
                "high_value_claim_threshold", 100000
            )
            mask &= df[col["claim_amount"]] >= threshold
            has_filter = True

        if not has_filter:
            return None

        return set(df.index[mask])

    # ------------------------------------------------------------------
    def _ask_llm_with_retry(self, question: str, context_rows: pd.DataFrame) -> str:
        """Call the LLM with retry logic.

        Attempts up to llm_retry_count times. On all failures, returns a
        summary-stats fallback answer.
        """
        retry_count = self.loader.config.get("ai", {}).get("llm_retry_count", 2)
        last_error = None

        for attempt in range(1, retry_count + 1):
            try:
                logger.info(f"LLM attempt {attempt}/{retry_count}")
                answer = self.llm.answer(
                    question=question,
                    context_rows=context_rows,
                    col=self.loader.col,
                    summary=self.loader.summary,
                )
                if answer and not answer.startswith("Could not reach"):
                    return answer
                last_error = answer
            except Exception as e:
                logger.warning(f"LLM attempt {attempt} failed: {e}")
                last_error = str(e)

        # Fallback: summary stats answer
        logger.warning("All LLM attempts failed, returning summary fallback")
        s = self.loader.summary
        return (
            f"I was unable to get a detailed answer from the AI model, "
            f"but here is what I know from the data:\n\n"
            f"- Total claims: {s['total_claims']:,}\n"
            f"- Total value: ${s['total_claim_amount']:,.2f}\n"
            f"- Total paid: ${s['total_paid_amount']:,.2f}\n"
            f"- Total reserves: ${s['total_reserve_amount']:,.2f}\n"
            f"- Average claim: ${s['avg_claim_amount']:,.2f}\n"
            f"- Average days open: {s['avg_days_open']} days\n\n"
            f"The search found {len(context_rows)} relevant claims. "
            f"Please try again or rephrase your question."
        )

    # ------------------------------------------------------------------
    def rebuild(self):
        """Reload data and rebuild the search index."""
        logger.info("RAG pipeline rebuild triggered")
        self.loader.reload()

        from data.text_chunker import dataframe_to_chunks
        chunks = dataframe_to_chunks(
            self.loader.df,
            self.loader.col,
            chunk_size=self.loader.config["data"]["chunk_size"],
        )
        self.search_engine.rebuild(chunks)
        logger.info("RAG pipeline rebuild complete")
