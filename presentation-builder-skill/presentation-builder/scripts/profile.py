from __future__ import annotations

import re

try:
    import polars as pl
except ImportError as _e:  # pragma: no cover
    raise ImportError(
        "presentation-builder requires 'polars' — pip install polars "
        "(use polars-lts-cpu on emulated/older CPUs)") from _e

# ── PII regexes ──────────────────────────────────────────────────────────────
PII_NAME_RX = re.compile(
    r"(?i)(ssn|social.?security|credit.?card|cc.?num|passport|home.?address|tax.?id|dob|date.?of.?birth|email|phone|account.?number|acct.?num)"
)
SSN_RX = re.compile(r"^\d{3}-\d{2}-\d{4}$")
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ── Context detection regexes ─────────────────────────────────────────────────
REVENUE_RX = re.compile(r"(?i)(revenue|sales|income|amount)")
COST_RX = re.compile(r"(?i)(cost|expense|spend|cogs)")
REGION_RX = re.compile(r"(?i)(region|country|state|city|territory|segment|department)")
DATE_RX = re.compile(r"(?i)(date|time|month|quarter|year|period)")

# ── Outline constants ─────────────────────────────────────────────────────────
# Map computation_id → required columns (regex match against profile schema).
COMPUTATION_REQUIREMENTS = {
    "monthly_revenue": [r"(?i)(revenue|sales|income|amount)"],
    "gross_margin": [r"(?i)(revenue|sales|income)", r"(?i)(cost|expense|cogs)"],
    "top_n_by_region": [r"(?i)(region|country|segment|territory)"],
    "outlier_drill": [],
    "descriptive_summary": [],
}

NULL_THRESHOLD_PCT = 15.0


# ── profile helpers ───────────────────────────────────────────────────────────

def _luhn_valid(num: int) -> bool:
    digits = [int(d) for d in str(num)]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _detect_pii(df: pl.DataFrame) -> list:
    """Columns that look like PII: name match, or ANY value in the column that
    is an SSN/email (full vectorised scan — a single leaked value is a leak),
    or an all-Luhn-valid numeric sample (first 20, as before)."""
    pii = set()
    for col in df.columns:
        if PII_NAME_RX.search(col):
            pii.add(col)
            continue
        series = df[col].drop_nulls()
        if series.len() == 0:
            continue
        if df[col].dtype == pl.String:
            # scan EVERY value (the old 20-row sample missed PII that first
            # appears later in the file); same anchored patterns, Rust-side
            if bool(series.str.contains(SSN_RX.pattern).any()) or \
               bool(series.str.contains(EMAIL_RX.pattern).any()):
                pii.add(col)
                continue
        if df[col].dtype.is_numeric():
            sample = series.head(min(20, series.len())).to_list()
            try:
                if all(_luhn_valid(int(v)) for v in sample):
                    pii.add(col)
            except (ValueError, TypeError):
                pass
    return sorted(pii)


def _date_range(df: pl.DataFrame) -> dict | None:
    for col in df.columns:
        if df[col].dtype in (pl.Date, pl.Datetime):
            series = df[col].drop_nulls()
            if series.len() == 0:
                continue
            return {
                "column": col,
                "min": str(series.min()),
                "max": str(series.max()),
            }
    return None


def _distributions(df: pl.DataFrame) -> dict:
    """mean/min/max/std per numeric column, computed in ONE select pass
    (polars aggregates skip nulls, matching the old per-column drop_nulls)."""
    num_cols = [c for c in df.columns if df.schema[c].is_numeric()]
    if not num_cols:
        return {}
    aggs = []
    for i, c in enumerate(num_cols):
        # drop_nulls first: bit-identical to the old per-Series math (the
        # null-aware std kernel reduces in a different order)
        e = pl.col(c).drop_nulls()
        aggs += [e.mean().alias(f"{i}m"), e.min().alias(f"{i}lo"),
                 e.max().alias(f"{i}hi"), e.std().alias(f"{i}s"),
                 e.count().alias(f"{i}n")]
    vals = df.select(aggs).row(0)
    out = {}
    for i, c in enumerate(num_cols):
        mean, mn, mx, std, n = vals[5 * i:5 * i + 5]
        if n == 0:          # all-null column: nothing to describe
            continue
        out[c] = {
            "mean": float(mean),
            "min": mn,
            "max": mx,
            "std": float(std) if n > 1 else 0.0,
        }
    return out


def _detect_outliers(df: pl.DataFrame, max_per_col: int = 5) -> list:
    """IQR-based outlier detection. Returns top-N most extreme outliers per column.
    The fence comparison runs vectorised over the column's DISTINCT values;
    only the (few) actual outliers reach Python."""
    out = []
    for col in df.columns:
        if not df[col].dtype.is_numeric():
            continue
        series = df[col].drop_nulls()
        if series.len() < 4:  # Need enough data for quartiles
            continue
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        if q1 is None or q3 is None:
            continue
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        mean = series.mean()
        if mean is None or mean == 0:
            continue
        # Find unique values outside the IQR fences (vectorised, not per-value Python)
        uniq = series.unique()
        extreme = uniq.filter((uniq < lower) | (uniq > upper)).to_list()
        candidates = [
            {"col": col, "value": v, "deviation_pct": round(100.0 * (v - mean) / abs(mean), 2)}
            for v in extreme
        ]
        # Keep top-N by absolute deviation
        candidates.sort(key=lambda x: abs(x["deviation_pct"]), reverse=True)
        out.extend(candidates[:max_per_col])
    return out


def profile(df: pl.DataFrame) -> dict:
    """Profile a frame: {schema, dtypes, null_pct, distributions, outliers,
    date_range, pii_columns}. Empty/None input returns the same shape with
    empty values. Column passes are batched — one scan each for nulls and
    numeric distributions."""
    if df is None or df.is_empty():
        return {
            "schema": {},
            "dtypes": {},
            "null_pct": {},
            "distributions": {},
            "outliers": [],
            "date_range": None,
            "pii_columns": [],
        }
    schema = {col: str(df.schema[col]) for col in df.columns}
    nulls = df.null_count().row(0)          # one pass over all columns
    null_pct = {
        col: round(100.0 * n / df.height, 2)
        for col, n in zip(df.columns, nulls)
    }
    return {
        "schema": schema,
        "dtypes": dict(schema),  # alias (own copy: callers may mutate one view)
        "null_pct": null_pct,
        "distributions": _distributions(df),
        "outliers": _detect_outliers(df),
        "date_range": _date_range(df),
        "pii_columns": _detect_pii(df),
    }


# ── context detection ─────────────────────────────────────────────────────────

def _has_match(cols, rx):
    return any(rx.search(c) for c in cols)

def _find_first(cols, rx):
    for c in cols:
        if rx.search(c):
            return c
    return None

def detect_context(profile: dict) -> dict:
    """Infer the story the data supports. Returns {story_type,
    suggested_sections, required_computations} (always at least the
    descriptive fallback)."""
    cols = list(profile.get("schema", {}).keys())
    sections = []
    computations = []
    story_parts = []

    has_date = profile.get("date_range") is not None or _has_match(cols, DATE_RX)
    has_revenue = _has_match(cols, REVENUE_RX)
    has_cost = _has_match(cols, COST_RX)
    has_region = _has_match(cols, REGION_RX)

    if has_date and has_revenue:
        sections.append("Revenue Trend")
        computations.append("monthly_revenue")
        story_parts.append("time-series")
    if has_revenue and has_cost:
        sections.append("Margin Analysis")
        computations.append("gross_margin")
        story_parts.append("margin")
    if has_region:
        numeric_cols = [c for c, t in profile.get("schema", {}).items() if "Int" in t or "Float" in t]
        if numeric_cols:
            sections.append("Regional Breakdown")
            computations.append("top_n_by_region")
            story_parts.append("regional")
    if profile.get("outliers"):
        sections.append("Outlier Deep Dive")
        computations.append("outlier_drill")

    if not sections:
        sections.append("Data Summary")
        computations.append("descriptive_summary")
        story_parts.append("descriptive")

    return {
        "story_type": " + ".join(story_parts),
        "suggested_sections": sections,
        "required_computations": computations,
    }


# ── outline building ──────────────────────────────────────────────────────────

def _columns_matching(schema_cols, pattern):
    rx = re.compile(pattern)
    return [c for c in schema_cols if rx.search(c)]


def _check_viability(profile: dict, computation_id: str) -> tuple:
    schema_cols = list(profile.get("schema", {}).keys())
    null_pct = profile.get("null_pct", {})
    pii = set(profile.get("pii_columns", []))
    requirements = COMPUTATION_REQUIREMENTS.get(computation_id, [])
    for pattern in requirements:
        matches = _columns_matching(schema_cols, pattern)
        if not matches:
            return False, f"No column matching {pattern} found"
        # Check viability of best match
        viable = [c for c in matches if c not in pii and null_pct.get(c, 0) <= NULL_THRESHOLD_PCT]
        if not viable:
            offending = matches[0]
            if offending in pii:
                return False, f"Column '{offending}' excluded for PII privacy compliance"
            return False, f"Column '{offending}' has {null_pct.get(offending, 0)}% nulls (>{NULL_THRESHOLD_PCT}%)"
    return True, ""


def build_outline(profile: dict, context: dict) -> dict:
    """Slide plan from a profile+context: exec summary, viable sections
    (PII/null-threshold checked), outlier deep-dives — budget-enforced.
    Returns {slides, deferred, excluded} from enforce_slide_budget."""
    slides = []
    n = 1
    # Slide 1: Exec Summary placeholder (filled in Stage 2 from synthesized takeaways)
    slides.append({
        "n": n,
        "layout": "Title and Content",
        "title": "Executive Summary",
        "content_type": "exec_summary",
        "computation_id": None,
        "chart_spec": None,
        "status": "active",
    })
    n += 1

    # Section slides
    sections = context.get("suggested_sections", [])
    computations = context.get("required_computations", [])
    for section, comp_id in zip(sections, computations):
        viable, reason = _check_viability(profile, comp_id)
        slide = {
            "n": n,
            "layout": "Image + Text",
            "title": section,
            "content_type": "section",
            "computation_id": comp_id,
            "chart_spec": {"type": "auto"},
            "status": "active" if viable else "excluded",
            "reason": "" if viable else reason,
        }
        slides.append(slide)
        n += 1

    # Deep-dive slides per outlier
    for outlier in profile.get("outliers", []):
        slides.append({
            "n": n,
            "layout": "Big Number",
            "title": f"Deep Dive: {outlier['col']} = {outlier['value']}",
            "content_type": "deep_dive",
            "computation_id": "outlier_drill",
            "chart_spec": {"type": "annotation", "outlier": outlier},
            "status": "active",
            "outlier": outlier,
        })
        n += 1

    return enforce_slide_budget(slides, MAX_SLIDES)


# ── slide budget, prioritization & analytics bridge ───────────────────────────
# "Brevity is Law": a deck never exceeds MAX_SLIDES active content slides, and
# deep-dives are capped so outliers can't explode the deck. Pure-stdlib.
MAX_SLIDES = 10
MAX_DEEP_DIVES = 2
_BASE_PRIORITY = {
    "monthly_revenue": 80, "gross_margin": 75, "top_n_by_region": 60,
    "descriptive_summary": 30, "outlier_drill": 0,
}
_RAG_WEIGHT = {"red": 100, "amber": 60, "green": 20, None: 40}


def score_slide(slide: dict) -> float:
    ct = slide.get("content_type")
    if ct == "exec_summary":
        return 1e9
    if ct == "deep_dive":
        o = slide.get("outlier") or {}
        return 50 + abs(float(o.get("deviation_pct") or 0))
    if ct == "insight":
        rag = _RAG_WEIGHT.get(slide.get("rag"), 40)
        delta = abs(float((slide.get("comparison") or {}).get("delta_pct") or 0))
        return rag + min(delta, 40)
    return _BASE_PRIORITY.get(slide.get("computation_id"), 40)


def enforce_slide_budget(slides: list, max_slides: int = MAX_SLIDES) -> dict:
    """Keep exec summary, cap deep-dives, prioritize by impact, trim to <=max_slides
    ACTIVE content slides. Data-integrity 'excluded' slides are set aside (they still
    feed the Exclusions slide via build_deck). Brevity-trimmed slides go to 'deferred'."""
    excluded = [s for s in slides if s.get("status") == "excluded"]
    active = [s for s in slides if s.get("status") != "excluded"]
    exec_s = [s for s in active if s.get("content_type") == "exec_summary"]
    deep = [s for s in active if s.get("content_type") == "deep_dive"]
    others = [s for s in active if s.get("content_type") not in ("exec_summary", "deep_dive")]
    deep.sort(key=score_slide, reverse=True)
    deep_kept, deep_cut = deep[:MAX_DEEP_DIVES], deep[MAX_DEEP_DIVES:]
    pool = others + deep_kept
    pool.sort(key=score_slide, reverse=True)
    budget = max(0, max_slides - len(exec_s))
    kept_body, deferred = pool[:budget], pool[budget:] + deep_cut
    kept = exec_s + kept_body
    for i, s in enumerate(kept, start=1):
        s["n"] = i
    for s in deferred:
        s["status"] = "deferred_for_brevity"
    # excluded slides appended so build_deck's Exclusions logic still finds them
    return {"slides": kept + excluded, "deferred": deferred, "excluded": excluded}


def outline_from_analytics(insights: list, max_slides: int = MAX_SLIDES) -> dict:
    """Bridge: turn claims-analytics output into a slide plan. Each insight:
      {metric, value, display, period, comparison:{prior,delta_pct}, definition,
       provenance, app, app_url, rag, breakdown:{labels,values}?}. Preserves
      provenance/app for citation; respects the slide budget."""
    slides = [{"n": 1, "content_type": "exec_summary", "title": "Executive Summary",
               "layout": "Title and Content", "status": "active"}]
    for ins in insights:
        if (ins.get("breakdown") or {}).get("labels"):
            vk, layout = "comparative_bar", "Image + Text"
        else:
            vk, layout = "kpi_card", "Big Number"
        slides.append({
            "content_type": "insight", "visual_kind": vk, "layout": layout,
            "metric": ins.get("metric"), "display": ins.get("display"),
            "value": ins.get("value"), "period": ins.get("period"),
            "comparison": ins.get("comparison"), "definition": ins.get("definition"),
            "provenance": ins.get("provenance"), "app": ins.get("app"),
            "app_url": ins.get("app_url"), "rag": ins.get("rag"),
            "breakdown": ins.get("breakdown"), "status": "active",
        })
    return enforce_slide_budget(slides, max_slides)