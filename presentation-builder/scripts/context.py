import re

REVENUE_RX = re.compile(r"(?i)(revenue|sales|income|amount)")
COST_RX = re.compile(r"(?i)(cost|expense|spend|cogs)")
REGION_RX = re.compile(r"(?i)(region|country|state|city|territory|segment|department)")
DATE_RX = re.compile(r"(?i)(date|time|month|quarter|year|period)")

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
