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
