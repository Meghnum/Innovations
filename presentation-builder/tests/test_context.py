from scripts.profile import detect_context

def _profile(schema: dict, date_range=None) -> dict:
    return {
        "schema": schema,
        "null_pct": {c: 0.0 for c in schema},
        "outliers": [],
        "date_range": date_range,
        "pii_columns": [],
        "distributions": {},
    }

def test_time_series_story_when_date_present():
    p = _profile({"Date": "Date", "Revenue": "Float64"}, date_range={"column": "Date", "min": "2026-01", "max": "2026-12"})
    ctx = detect_context(p)
    assert ctx["story_type"] == "time-series"
    assert "monthly_revenue" in ctx["required_computations"]

def test_margin_story_when_revenue_and_cost():
    p = _profile({"Revenue": "Float64", "Cost": "Float64"})
    ctx = detect_context(p)
    assert "margin" in ctx["story_type"]
    assert "gross_margin" in ctx["required_computations"]

def test_regional_story_when_region_and_numeric():
    p = _profile({"Region": "String", "Sales": "Float64"})
    ctx = detect_context(p)
    assert "regional" in ctx["story_type"] or "comparative" in ctx["story_type"]
    assert "top_n_by_region" in ctx["required_computations"]

def test_combined_story_time_region_financials():
    p = _profile(
        {"Date": "Date", "Region": "String", "Revenue": "Float64", "Cost": "Float64"},
        date_range={"column": "Date", "min": "2026-Q3", "max": "2026-Q3"},
    )
    ctx = detect_context(p)
    sections = ctx["suggested_sections"]
    assert any("Trend" in s for s in sections)
    assert any("Margin" in s for s in sections)
    assert any("Region" in s for s in sections)
