from scripts.outline import build_outline

def _ctx(sections, computations):
    return {
        "story_type": "test",
        "suggested_sections": sections,
        "required_computations": computations,
    }

def _prof(null_pct=None, outliers=None, pii=None):
    return {
        "schema": {"Date": "Date", "Revenue": "Float64", "Cost": "Float64", "Region": "String"},
        "null_pct": null_pct or {"Date": 0, "Revenue": 0, "Cost": 0, "Region": 0},
        "outliers": outliers or [],
        "pii_columns": pii or [],
        "distributions": {},
        "date_range": None,
    }

def test_outline_has_exec_summary_first():
    profile = _prof()
    ctx = _ctx(["Revenue Trend"], ["monthly_revenue"])
    outline = build_outline(profile, ctx)
    assert outline["slides"][0]["content_type"] == "exec_summary"
    assert outline["slides"][0]["n"] == 1

def test_outline_excludes_slide_when_required_col_too_null():
    profile = _prof(null_pct={"Date": 0, "Revenue": 0, "Cost": 40.0, "Region": 0})
    ctx = _ctx(["Margin Analysis"], ["gross_margin"])
    outline = build_outline(profile, ctx)
    margin_slide = [s for s in outline["slides"] if s["computation_id"] == "gross_margin"][0]
    assert margin_slide["status"] == "excluded"
    assert "Cost" in margin_slide["reason"]
    assert "40" in margin_slide["reason"]

def test_outline_includes_deep_dive_per_outlier():
    profile = _prof(outliers=[{"col": "Revenue", "value": 1.2e6, "deviation_pct": 340}])
    ctx = _ctx(["Revenue Trend"], ["monthly_revenue"])
    outline = build_outline(profile, ctx)
    deep_dives = [s for s in outline["slides"] if s["content_type"] == "deep_dive"]
    assert len(deep_dives) == 1

def test_outline_skips_pii_computations():
    profile = _prof(pii=["Revenue"])
    ctx = _ctx(["Revenue Trend"], ["monthly_revenue"])  # uses Revenue
    outline = build_outline(profile, ctx)
    rev_slide = [s for s in outline["slides"] if s["computation_id"] == "monthly_revenue"][0]
    assert rev_slide["status"] == "excluded"
    assert "PII" in rev_slide["reason"] or "privacy" in rev_slide["reason"].lower()
