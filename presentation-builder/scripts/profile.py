import re

import polars as pl

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
    pii = set()
    for col in df.columns:
        if PII_NAME_RX.search(col):
            pii.add(col)
            continue
        series = df[col].drop_nulls()
        if series.len() == 0:
            continue
        sample_size = min(200, series.len())
        sample = series.sample(n=sample_size, seed=42).to_list() if series.len() > sample_size else series.to_list()
        if df[col].dtype == pl.String:
            if any(SSN_RX.match(str(v)) for v in sample):
                pii.add(col)
                continue
            if any(EMAIL_RX.match(str(v)) for v in sample):
                pii.add(col)
                continue
        if df[col].dtype.is_numeric():
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
    out = {}
    for col in df.columns:
        if df[col].dtype.is_numeric():
            series = df[col].drop_nulls()
            if series.len() == 0:
                continue
            out[col] = {
                "mean": float(series.mean()),
                "min": series.min(),
                "max": series.max(),
                "std": float(series.std()) if series.len() > 1 else 0.0,
            }
    return out


def _detect_outliers(df: pl.DataFrame, max_per_col: int = 5) -> list:
    """IQR-based outlier detection. Returns top-N most extreme outliers per column."""
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
        # Find values outside IQR fences
        candidates = []
        for v in series.unique().to_list():
            if v < lower or v > upper:
                dev_pct = 100.0 * (v - mean) / abs(mean)
                candidates.append({
                    "col": col,
                    "value": v,
                    "deviation_pct": round(dev_pct, 2),
                })
        # Keep top-N by absolute deviation
        candidates.sort(key=lambda x: abs(x["deviation_pct"]), reverse=True)
        out.extend(candidates[:max_per_col])
    return out


def profile(df: pl.DataFrame) -> dict:
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
    null_pct = {
        col: round(100.0 * df[col].null_count() / df.height, 2)
        for col in df.columns
    }
    return {
        "schema": schema,
        "dtypes": schema,  # alias
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

    return {"slides": slides}
