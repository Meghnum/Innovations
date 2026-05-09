import polars as pl


def _detect_outliers(df: pl.DataFrame, threshold_pct: float = 20.0) -> list:
    out = []
    for col in df.columns:
        if not df[col].dtype.is_numeric():
            continue
        series = df[col].drop_nulls()
        if series.len() < 2:
            continue
        mean = series.mean()
        if mean is None or mean == 0:
            continue
        for v in series.unique().to_list():
            dev_pct = 100.0 * (v - mean) / abs(mean)
            if abs(dev_pct) > threshold_pct:
                out.append({
                    "col": col,
                    "value": v,
                    "deviation_pct": round(dev_pct, 2),
                })
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
        "distributions": {},
        "outliers": _detect_outliers(df),
        "date_range": None,
        "pii_columns": [],
    }
