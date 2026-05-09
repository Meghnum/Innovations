import re

# Map computation_id → required columns (regex match against profile schema).
COMPUTATION_REQUIREMENTS = {
    "monthly_revenue": [r"(?i)(revenue|sales|income|amount)"],
    "gross_margin": [r"(?i)(revenue|sales|income)", r"(?i)(cost|expense|cogs)"],
    "top_n_by_region": [r"(?i)(region|country|segment|territory)"],
    "outlier_drill": [],
    "descriptive_summary": [],
}

NULL_THRESHOLD_PCT = 15.0


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
