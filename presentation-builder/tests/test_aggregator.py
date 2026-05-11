import polars as pl
import datetime as dt
from scripts.analyze import aggregate

def test_aggregate_time_series_reduces_to_monthly_points():
    df = pl.DataFrame({
        "Date": [dt.date(2026, 7, i) for i in range(1, 31)],
        "Revenue": [100] * 30,
    })
    result = aggregate(df, {"type": "line", "x": "Date", "y": "Revenue"})
    assert "labels" in result and "values" in result
    assert len(result["labels"]) == len(result["values"])
    assert len(result["labels"]) <= 100

def test_aggregate_categorical_groups_by_x():
    df = pl.DataFrame({
        "Region": ["N", "S", "N", "S", "E"],
        "Revenue": [1, 2, 3, 4, 5],
    })
    result = aggregate(df, {"type": "bar", "x": "Region", "y": "Revenue"})
    assert sorted(result["labels"]) == ["E", "N", "S"]
    by_label = dict(zip(result["labels"], result["values"]))
    assert by_label["N"] == 4
    assert by_label["S"] == 6
    assert by_label["E"] == 5

def test_aggregate_caps_at_100_points():
    df = pl.DataFrame({"x": list(range(500)), "y": list(range(500))})
    result = aggregate(df, {"type": "bar", "x": "x", "y": "y"})
    assert len(result["values"]) <= 100

def test_aggregate_empty_dataframe_returns_empty():
    df = pl.DataFrame({"x": [], "y": []})
    result = aggregate(df, {"type": "bar", "x": "x", "y": "y"})
    assert result["labels"] == []
    assert result["values"] == []
