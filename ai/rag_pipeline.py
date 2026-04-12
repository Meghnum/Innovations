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
        region_col = col.get("region", "Country")
        if region_col in dframe.columns:
            region_val = ent.get("region")
            if not region_val:
                for kw in ["uk", "us", "usa", "canada", "australia", "germany",
                           "france", "japan", "brazil", "india"]:
                    if _has_word(kw):
                        region_val = "US" if kw in ("us", "usa") else kw.upper() if kw == "uk" else kw.title()
                        break
            if region_val:
                mask &= dframe[region_col].str.lower() == region_val.lower()
                filtered = True

        # --- Minor LOB filter ---
        minor_lob_col = col.get("minor_lob", "Minor LOB")
        if minor_lob_col in dframe.columns:
            minor_lob_keywords = [
                "commercial fire", "marine cargo", "professional indemnity",
                "auto liability", "workers comp", "cyber liability",
                "product liability", "general liability",
            ]
            for kw in minor_lob_keywords:
                if kw in q:
                    mask &= dframe[minor_lob_col].str.lower().str.contains(
                        re.escape(kw), na=False
                    )
                    filtered = True
                    break

        # --- Cause of loss filter ---
        cause_col = col.get("cause_of_loss_descr", "Cause Of Loss Descr")
        if cause_col in dframe.columns:
            cause_keywords = [
                "water damage", "slip and fall", "windstorm", "theft",
                "collision", "workplace injury", "equipment failure",
                "professional error", "cyber breach",
                "fire",  # keep fire last so "commercial fire" (minor_lob) wins first
            ]
            for kw in cause_keywords:
                if kw in q:
                    mask &= dframe[cause_col].str.lower().str.contains(
                        re.escape(kw), na=False
                    )
                    filtered = True
                    break

        # --- Claim type filter (skip keyword detection if Minor LOB already matched) ---
        minor_lob_matched = any(kw in q for kw in minor_lob_keywords) if minor_lob_col in dframe.columns else False
        claim_type_col = col.get("claim_type", "Claim Type Description")
        if claim_type_col in dframe.columns:
            claim_type_val = ent.get("claim_type")
            if not claim_type_val and not minor_lob_matched:
                for kw in ["bodily injury", "property damage", "motor",
                           "liability", "cyber"]:
                    if kw in q:
                        claim_type_val = kw
                        break
            if claim_type_val:
                mask &= dframe[claim_type_col].str.lower().str.contains(
                    re.escape(claim_type_val.lower()), na=False
                )
                filtered = True

        # --- Accident Year filter ---
        accident_year_col = col.get("accident_year", "Accident Year")
        if accident_year_col in dframe.columns:
            ay_match = re.search(r'\baccident\s+year\s+(\d{4})\b', q)
            if ay_match:
                ay_val = int(ay_match.group(1))
                mask &= dframe[accident_year_col] == ay_val
                filtered = True

        # --- Policy UWY filter ---
        policy_uwy_col = col.get("policy_uwy", "Policy UWY")
        if policy_uwy_col in dframe.columns:
            uwy_match = re.search(
                r'\b(?:uwy|underwriting\s+year)\s+(\d{4})\b', q
            )
            if uwy_match:
                uwy_val = int(uwy_match.group(1))
                mask &= dframe[policy_uwy_col] == uwy_val
                filtered = True

        # --- Bulk claim indicator filter ---
        bulk_col = col.get("bulk_claim_indicator", "Bulk Claim Indicator")
        if bulk_col in dframe.columns and _has_word("bulk"):
            mask &= dframe[bulk_col].astype(str).str.lower().isin(
                ["y", "yes", "true", "1"]
            )
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

        # --- Policyholder name filter ---
        # Exclude known entity keywords to avoid "for Canada" triggering policyholder
        _entity_words = {
            "open", "closed", "pending", "rejected", "uk", "us", "usa",
            "canada", "australia", "germany", "france", "japan", "brazil",
            "india", "commercial", "marine", "cyber", "motor", "property",
        }
        ph_col = col.get("policy_holder_name", "Policy Holder Name")
        if ph_col in dframe.columns:
            ph_match = re.search(r'\bfor\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)', question)
            if ph_match:
                ph_name = ph_match.group(1)
                if ph_name.lower() not in _entity_words:
                    mask &= dframe[ph_col].str.lower() == ph_name.lower()
                    filtered = True

        if not filtered:
            return dframe
        return dframe[mask]

    # --- Entity-aware status count (only when no other filters apply) ---
    if ent.get("status") and ("how many" in q or _has_word("count")):
        # Check if there are additional filters beyond just status
        fdf = _apply_filters(df) if df is not None else None
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

    # --- Specific financial column queries ---
    # Maps keyword patterns to (config_key, display_name)
    _fin_columns = {
        # Longer/more-specific keys MUST come before shorter ones
        "outstanding reserve": ("outstanding_reserve_usd", "Outstanding Reserve USD"),
        "nominal reserve": ("nominal_reserve", "Nominal Reserve"),
        "expense reserve": ("expense_reserve_usd", "Expense Reserve USD"),
        "expense paid": ("expense_paid_usd", "Expense Paid USD"),
        "reserve": ("reserve_amount", "Outstanding Reserve USD"),
        "recoveries": ("recoveries_usd", "Recoveries USD"),
        "recovery": ("recoveries_usd", "Recoveries USD"),
        "subrogation": ("recoveries_usd", "Recoveries USD"),
        "salvage": ("recoveries_usd", "Recoveries USD"),
        "alae": ("expense_paid_usd", "Expense Paid USD"),
        "legal": ("expense_paid_usd", "Expense Paid USD"),
        "indemnity": ("indemnity_paid_usd", "Indemnity Paid USD"),
        "incurred": ("incurred_usd", "Incurred USD"),
    }

    if df is not None and col is not None:
        for fin_kw, (cfg_key, display) in _fin_columns.items():
            if fin_kw in q:
                actual_col = col.get(cfg_key, display)
                if actual_col not in df.columns:
                    continue
                fdf = _apply_filters(df)
                filter_desc = f" ({len(fdf):,} matching claims)" if len(fdf) < len(df) else ""

                if "average" in q or "avg" in q or "mean" in q:
                    val = fdf[actual_col].mean()
                    return f"Average {display}{filter_desc}: **${val:,.2f}**"

                if "total" in q or "sum" in q or "how much" in q or "recovered" in q:
                    val = fdf[actual_col].sum()
                    return f"Total {display}{filter_desc}: **${val:,.2f}**"

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

                # Default: show total
                val = fdf[actual_col].sum()
                return f"Total {display}{filter_desc}: **${val:,.2f}**"

    # --- Status count (generic) ---
    if "how many" in q or _has_word("count"):
        # Detect status keyword for labeling
        detected_status = None
        for status in ["open", "closed", "pending", "rejected", "under review"]:
            if status in q:
                detected_status = status.title()
                break

        # Try _apply_filters to handle combined filters (status+region etc.)
        fdf = _apply_filters(df) if df is not None else None
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

    # --- Country breakdown ---
    if df is not None and col is not None and (
        _has_word("country") or _has_word("countries")
    ):
        fdf = _apply_filters(df)
        filter_desc = f" ({len(fdf):,} matching)" if len(fdf) < len(df) else ""
        result = fdf.groupby(col["region"])[col["claim_id"]].count().sort_values(ascending=False)
        lines = [f"- {r}: {c:,}" for r, c in result.items()]
        return f"**Claims by Country{filter_desc}:**\n" + "\n".join(lines)

    # --- Smart "biggest / top / most / contributing factor" detector ---
    # Must be ABOVE generic breakdown handlers to catch "breakdown by contributing factor"
    if df is not None and col is not None and any(
        w in q for w in ["biggest", "largest", "top", "most", "highest",
                         "contributing", "driver", "factor", "volume",
                         "dominant", "major", "leading"]
    ):
        # Show top contributors across multiple dimensions
        fdf = _apply_filters(df)
        filter_desc = f" (filtered to {len(fdf):,} claims)" if len(fdf) < len(df) else ""
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
        logger.info(f"Intent: {intent} | Entities: {entities}")

        # Step 2: Route by intent
        if intent == "aggregation":
            answer = handle_aggregation(
                question, self.loader.summary,
                self.loader.df, self.loader.col, entities,
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
            answer = handle_lookup(claim_id, self.loader.df, self.loader.col,
                                   policy_id=policy_id)
            return {
                "answer": answer,
                "question_type": "lookup",
                "sources": [],
                "entities": entities,
            }

        # Step 3: Search path
        if not self.search_engine.is_ready:
            return {
                "answer": "Search engine is not ready. Please wait for the index to build.",
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
