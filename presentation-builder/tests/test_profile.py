import polars as pl
from scripts.profile import profile


def test_profile_basic_schema():
    df = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    result = profile(df)
    assert "schema" in result
    assert result["schema"]["a"] == "Int64"
    assert result["schema"]["b"] == "String"
    assert "null_pct" in result
    assert result["null_pct"]["a"] == 0.0
    assert result["null_pct"]["b"] == 0.0


def test_profile_null_pct_correct():
    df = pl.DataFrame({"a": [1, None, 3, None]})
    result = profile(df)
    assert result["null_pct"]["a"] == 50.0


def test_outlier_detected_when_value_exceeds_20pct_deviation():
    df = pl.DataFrame({"x": [10, 11, 9, 10, 100]})  # 100 is far above mean
    result = profile(df)
    outs = [o for o in result["outliers"] if o["col"] == "x"]
    assert len(outs) >= 1
    assert any(o["value"] == 100 for o in outs)
    assert all(abs(o["deviation_pct"]) > 20 for o in outs)


def test_no_outliers_in_uniform_data():
    df = pl.DataFrame({"x": [10, 10, 10, 10, 10]})
    result = profile(df)
    assert result["outliers"] == []
