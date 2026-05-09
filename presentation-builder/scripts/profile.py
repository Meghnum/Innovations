import polars as pl


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
        "distributions": {},
        "outliers": [],
        "date_range": None,
        "pii_columns": [],
    }
