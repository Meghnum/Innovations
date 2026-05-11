import polars as pl
import datetime as dt
from scripts.analyze import analyze

def test_monthly_revenue_returns_flat_kv():
    df = pl.DataFrame({
        "Date": [dt.date(2026, 7, 1), dt.date(2026, 8, 1), dt.date(2026, 9, 1)],
        "Revenue": [4_500_000, 4_200_000, 3_900_000],
    })
    result = analyze(df, "monthly_revenue")
    assert isinstance(result, dict)
    assert all(isinstance(v, (int, float, str)) for v in result.values())
    assert "sep_revenue" in result or any("sep" in k.lower() for k in result)

def test_gross_margin_computation():
    df = pl.DataFrame({
        "Revenue": [1000, 2000, 3000],
        "Cost": [400, 1000, 1500],
    })
    result = analyze(df, "gross_margin")
    # Gross margin = (Revenue - Cost) / Revenue
    # Total: (6000-2900)/6000 = 51.67%
    assert "total_gross_margin_pct" in result
    assert abs(result["total_gross_margin_pct"] - 51.67) < 0.5

def test_top_n_by_region():
    df = pl.DataFrame({
        "Region": ["North", "South", "East", "West"],
        "Revenue": [1000, 500, 2000, 1500],
    })
    result = analyze(df, "top_n_by_region")
    assert "top_region" in result
    assert result["top_region"] == "East"
    assert "top_region_value" in result
    assert result["top_region_value"] == 2000

def test_unknown_computation_returns_empty():
    df = pl.DataFrame({"x": [1, 2, 3]})
    result = analyze(df, "nonexistent")
    assert result == {}
