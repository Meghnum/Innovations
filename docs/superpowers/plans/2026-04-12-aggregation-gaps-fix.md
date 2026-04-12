# Aggregation Gaps Fix - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 8 gaps in handle_aggregation so complex insurance queries (filtered financials, date ranges, flag columns, policy lookups) return correct answers instead of falling through to generic summary.

**Architecture:** Replace brittle if/else chain with a two-layer approach: (1) add `_apply_entity_filters(df, col, entities, q)` helper that pre-filters DataFrame before ANY aggregation branch, (2) add new handlers for missing financial columns, date filters, flag filters, and policy lookup. Keep existing handlers intact.

**Tech Stack:** pandas, regex, existing config column mappings

---

### Task 1: Add universal entity filter helper

**Files:**
- Modify: `ai/rag_pipeline.py:28-58`
- Test: `tests/test_scenarios.py`

- [ ] **Step 1: Add `_apply_filters` helper after `_has_word` inside `handle_aggregation`**

```python
    # --- Universal pre-filter: apply entity + keyword filters to df ---
    def _apply_filters(base_df: pd.DataFrame) -> pd.DataFrame:
        """Pre-filter DataFrame using entities AND keyword-detected filters."""
        filtered = base_df.copy()

        # Entity filters (from QueryAnalyzer)
        if ent.get("status"):
            filtered = filtered[filtered[col["status"]].str.lower() == ent["status"].lower()]
        if ent.get("region"):
            filtered = filtered[filtered[col["region"]].str.lower() == ent["region"].lower()]
        if ent.get("claim_type"):
            filtered = filtered[filtered[col["claim_type"]].str.lower() == ent["claim_type"].lower()]

        # Keyword-detected filters from question text
        # Status keywords
        for status_kw in ["open", "closed", "pending", "rejected", "under review"]:
            if status_kw in q and not ent.get("status"):
                filtered = filtered[filtered[col["status"]].str.lower() == status_kw]
                break

        # Country keywords
        country_map = {"uk": "UK", "us": "US", "usa": "US", "canada": "Canada",
                       "australia": "Australia", "germany": "Germany", "france": "France",
                       "japan": "Japan", "brazil": "Brazil", "india": "India"}
        for kw, val in country_map.items():
            if _has_word(kw) and not ent.get("region"):
                filtered = filtered[filtered[col["region"]] == val]
                break

        # Minor LOB keywords
        minor_lob_col = col.get("minor_lob", "Minor LOB")
        if minor_lob_col in base_df.columns:
            for lob_kw in ["commercial fire", "marine cargo", "professional indemnity",
                           "auto liability", "workers comp", "cyber liability",
                           "product liability", "general liability"]:
                if lob_kw in q:
                    filtered = filtered[filtered[minor_lob_col].str.lower() == lob_kw]
                    break

        # Cause of loss keywords
        cause_col = col.get("cause_of_loss_descr", "Cause Of Loss Descr")
        if cause_col in base_df.columns:
            for cause_kw in ["water damage", "fire", "slip and fall", "windstorm",
                             "theft", "collision", "workplace injury", "equipment failure",
                             "professional error", "cyber breach"]:
                if cause_kw in q:
                    filtered = filtered[filtered[cause_col].str.lower() == cause_kw]
                    break

        # Claim type keywords
        for ct_kw in ["bodily injury", "property damage", "motor", "liability", "cyber"]:
            if ct_kw in q and not ent.get("claim_type"):
                filtered = filtered[filtered[col["claim_type"]].str.lower() == ct_kw]
                break

        # Accident Year
        import re as _re
        ay_match = _re.search(r'accident year\s*(\d{4})', q)
        if ay_match:
            ay_col = col.get("accident_year", "Accident Year")
            if ay_col in base_df.columns:
                filtered = filtered[filtered[ay_col] == int(ay_match.group(1))]

        # Policy UWY
        uwy_match = _re.search(r'uwy\s*(\d{4})|underwriting year\s*(\d{4})', q)
        if uwy_match:
            uwy_val = int(uwy_match.group(1) or uwy_match.group(2))
            uwy_col = col.get("policy_uwy", "Policy UWY")
            if uwy_col in base_df.columns:
                filtered = filtered[filtered[uwy_col] == uwy_val]

        # Bulk claim indicator
        if "bulk" in q:
            bulk_col = col.get("bulk_claim_indicator", "Bulk Claim Indicator")
            if bulk_col in base_df.columns:
                filtered = filtered[filtered[bulk_col] == True]

        # MAR fast track
        if "fast track" in q or "mar" in q:
            mar_col = col.get("mar_fast_track_flag", "MAR Fast Track Flag")
            if mar_col in base_df.columns:
                filtered = filtered[filtered[mar_col] == True]

        # Policyholder name
        holder_col = col.get("policy_holder_name", "Policy Holder Name")
        if holder_col in base_df.columns:
            # Check for quoted names or "for <name>"
            name_match = _re.search(r'(?:for|from|of)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', question)
            if name_match:
                name = name_match.group(1)
                filtered = filtered[filtered[holder_col].str.contains(name, case=False, na=False)]

        return filtered
```

- [ ] **Step 2: Run existing tests to verify nothing breaks**

Run: `python -m pytest tests/test_aggregation.py -v --tb=short`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add ai/rag_pipeline.py
git commit -m "feat: add universal _apply_filters helper to handle_aggregation"
```

---

### Task 2: Add financial column handlers (Recoveries, Outstanding Reserve, Expense, Nominal Reserve)

**Files:**
- Modify: `ai/rag_pipeline.py` (add new handlers before the Average section ~line 145)

- [ ] **Step 1: Add financial column detection and handlers after Total value BY status block**

Insert after the `Total value BY status` handler (around line 125):

```python
    # --- Specific financial column queries ---
    # Maps keyword patterns to (config_key, display_name)
    _fin_columns = {
        "outstanding reserve": ("outstanding_reserve_usd", "Outstanding Reserve USD"),
        "reserve": ("reserve_amount", "Outstanding Reserve USD"),
        "recoveries": ("recoveries_usd", "Recoveries USD"),
        "recovery": ("recoveries_usd", "Recoveries USD"),
        "subrogation": ("recoveries_usd", "Recoveries USD"),
        "salvage": ("recoveries_usd", "Recoveries USD"),
        "expense paid": ("expense_paid_usd", "Expense Paid USD"),
        "expense reserve": ("expense_reserve_usd", "Expense Reserve USD"),
        "alae": ("expense_paid_usd", "Expense Paid USD"),
        "legal": ("expense_paid_usd", "Expense Paid USD"),
        "indemnity": ("indemnity_paid_usd", "Indemnity Paid USD"),
        "nominal reserve": ("nominal_reserve", "Nominal Reserve"),
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
                break
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_aggregation.py tests/test_scenarios.py -v --tb=short`

- [ ] **Step 3: Commit**

```bash
git add ai/rag_pipeline.py
git commit -m "feat: add financial column handlers for recoveries, expense, nominal reserve"
```

---

### Task 3: Apply _apply_filters to existing aggregation handlers

**Files:**
- Modify: `ai/rag_pipeline.py` (update existing count/total/average handlers to use filtered df)

- [ ] **Step 1: Update "how many" / count handler to use _apply_filters**

Replace the generic status count block (line ~127-134):

```python
    # --- Status count (generic) ---
    if "how many" in q or _has_word("count"):
        for status in ["open", "closed", "pending", "rejected", "under review"]:
            if status in q:
                count = summary["status_counts"].get(status.title(), 0)
                return f"There are **{count:,}** {status.title()} claims in the current dataset."
        # Apply filters for generic "how many claims" with context
        fdf = _apply_filters(df) if df is not None else None
        if fdf is not None and len(fdf) < len(df):
            return f"There are **{len(fdf):,}** matching claims (out of {summary['total_claims']:,} total)."
        if "claim" in q:
            return f"There are **{summary['total_claims']:,}** claims in the current dataset."
```

- [ ] **Step 2: Update Average handler to support filtered averages**

Replace the average block (line ~145-149):

```python
    # --- Average ---
    if "average" in q or "avg" in q:
        fdf = _apply_filters(df) if df is not None else None
        filter_desc = f" ({len(fdf):,} matching claims)" if fdf is not None and len(fdf) < len(df) else ""

        if "day" in q or "open" in q or "life" in q or "claim life" in q:
            if fdf is not None and len(fdf) < len(df):
                days_col = col.get("days_open", col.get("claim_life_days", "Claim Life Days"))
                avg_val = round(fdf[days_col].mean(), 1)
                return f"Average claim life days{filter_desc}: **{avg_val}** days."
            return f"The average number of days a claim is open is **{summary['avg_days_open']}** days."

        if fdf is not None and len(fdf) < len(df):
            avg_val = round(fdf[col["claim_amount"]].mean(), 2)
            return f"Average claim value{filter_desc}: **${avg_val:,.2f}**."
        return f"The average claim value is **${summary['avg_claim_amount']:,.2f}**."
```

- [ ] **Step 3: Update Total value handler similarly**

Replace the total value block (line ~136-143):

```python
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
```

- [ ] **Step 4: Update smart detector to apply filters before grouping**

In the smart "biggest/top/contributing" section, add filtering:

```python
        fdf = _apply_filters(df)
        filter_desc = f" (filtered to {len(fdf):,} claims)" if len(fdf) < len(df) else ""
        # Then use fdf instead of df for all groupby operations in this block
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_aggregation.py tests/test_scenarios.py -v --tb=short`

- [ ] **Step 6: Commit**

```bash
git add ai/rag_pipeline.py
git commit -m "feat: apply entity+keyword filters across all aggregation handlers"
```

---

### Task 4: Add policy number lookup support

**Files:**
- Modify: `ai/rag_pipeline.py` (handle_lookup and RAGPipeline.ask)
- Modify: `ai/query_analyzer.py` (detect POL pattern)

- [ ] **Step 1: Update QueryAnalyzer to extract policy_id**

In `ai/query_analyzer.py`, add policy_id extraction to `_keyword_fallback`:

```python
    # Check for policy number pattern (POL followed by digits)
    pol_match = re.search(r'\b(POL[\-]?\d+[A-Za-z]*)\b', question, re.IGNORECASE)
    if pol_match:
        result["intent"] = "lookup"
        result["policy_id"] = pol_match.group(1).upper()
```

Also add `"policy_id": None` to the default result dict.

- [ ] **Step 2: Update handle_lookup to support policy number**

```python
def handle_lookup(claim_id: str, df: pd.DataFrame, col: dict,
                  policy_id: str = None) -> str:
    # Try claim_id first
    if claim_id:
        claim_id = claim_id.upper()
        row = df[df[col["claim_id"]] == claim_id]
        if not row.empty:
            # ... existing logic ...

    # Try policy_id
    if policy_id:
        policy_id = policy_id.upper()
        pol_col = col.get("policy_number", "Policy Number")
        if pol_col in df.columns:
            rows = df[df[pol_col] == policy_id]
            if not rows.empty:
                r = rows.iloc[0]
                # Build same table format but with policy context
                # ... (same table logic as claim lookup)
```

- [ ] **Step 3: Update RAGPipeline.ask to pass policy_id**

```python
        if intent == "lookup":
            claim_id = entities.get("claim_id")
            policy_id = analysis.get("policy_id")
            answer = handle_lookup(claim_id, self.loader.df, self.loader.col,
                                   policy_id=policy_id)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/ -v --tb=short`

- [ ] **Step 5: Commit**

```bash
git add ai/rag_pipeline.py ai/query_analyzer.py
git commit -m "feat: add policy number lookup support"
```

---

### Task 5: Update summary dict with additional metrics

**Files:**
- Modify: `data/qvd_loader.py:783-819` (build_aggregated_summary)

- [ ] **Step 1: Add recoveries, expense, nominal reserve totals to summary**

```python
    # Add to summary dict:
    "total_recoveries":      round(df[c.get("recoveries_usd", "Recoveries USD")].sum(), 2)
                             if c.get("recoveries_usd", "Recoveries USD") in df.columns else 0,
    "total_expense_paid":    round(df[c.get("expense_paid_usd", "Expense Paid USD")].sum(), 2)
                             if c.get("expense_paid_usd", "Expense Paid USD") in df.columns else 0,
    "avg_nominal_reserve":   round(df[c.get("nominal_reserve", "Nominal Reserve")].mean(), 2)
                             if c.get("nominal_reserve", "Nominal Reserve") in df.columns else 0,
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/ -v --tb=short`

- [ ] **Step 3: Commit**

```bash
git add data/qvd_loader.py
git commit -m "feat: add recoveries, expense, nominal reserve to summary stats"
```

---

### Task 6: Write comprehensive test coverage for all 8 gaps

**Files:**
- Create: `tests/test_gap_fixes.py`

- [ ] **Step 1: Write tests that verify each gap is fixed**

```python
"""Tests verifying all 8 aggregation gaps are fixed."""
import pytest
import pandas as pd
import numpy as np
from ai.rag_pipeline import handle_aggregation, handle_lookup, RAGPipeline

# ... fixture with small DataFrame containing all 74 columns ...

class TestGap1_PolicyLookup:
    def test_lookup_by_policy_number(self, ...):
        """POL-based query should find and return claim details."""

class TestGap2_MinorLOBFilter:
    def test_total_for_commercial_fire(self, ...):
        """'Total incurred for Commercial Fire' should filter by Minor LOB."""

class TestGap3_RecoveriesHandler:
    def test_recoveries_closed_uk(self, ...):
        """'Recoveries on closed UK claims' should filter and sum Recoveries USD."""

class TestGap4_CauseOfLossAverage:
    def test_avg_days_water_damage(self, ...):
        """'Average claim life days for water damage' should filter by cause."""

class TestGap5_AccidentYearFilter:
    def test_incurred_by_accident_year(self, ...):
        """'Total incurred for AY 2023' should filter by Accident Year."""

class TestGap6_SmartDetectorWithFilter:
    def test_top_factors_slip_and_fall(self, ...):
        """'Top contributing factors for slip and fall' should filter first."""

class TestGap7_BulkClaimFilter:
    def test_bulk_claims_count(self, ...):
        """'How many bulk claims' should filter by Bulk Claim Indicator."""

class TestGap8_NominalReserveAvg:
    def test_avg_nominal_reserve(self, ...):
        """'Average nominal reserve' should return Nominal Reserve average, not Incurred."""
```

- [ ] **Step 2: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`

- [ ] **Step 3: Commit**

```bash
git add tests/test_gap_fixes.py
git commit -m "test: add coverage for all 8 aggregation gap fixes"
```
