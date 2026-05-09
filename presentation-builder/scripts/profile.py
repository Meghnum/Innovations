import re

import polars as pl

PII_NAME_RX = re.compile(
    r"(?i)(ssn|social.?security|credit.?card|cc.?num|passport|home.?address|tax.?id|dob|date.?of.?birth|email|phone|account.?number|acct.?num)"
)
SSN_RX = re.compile(r"^\d{3}-\d{2}-\d{4}$")
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _luhn_valid(num: int) -> bool:
    digits = [int(d) for d in str(num)]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _detect_pii(df: pl.DataFrame) -> list:
    pii = set()
    for col in df.columns:
        if PII_NAME_RX.search(col):
            pii.add(col)
            continue
        series = df[col].drop_nulls()
        if series.len() == 0:
            continue
        sample = series.head(min(20, series.len())).to_list()
        if df[col].dtype == pl.String:
            if any(SSN_RX.match(str(v)) for v in sample):
                pii.add(col)
                continue
            if any(EMAIL_RX.match(str(v)) for v in sample):
                pii.add(col)
                continue
        if df[col].dtype.is_numeric():
            try:
                if all(_luhn_valid(int(v)) for v in sample):
                    pii.add(col)
            except (ValueError, TypeError):
                pass
    return sorted(pii)


def _date_range(df: pl.DataFrame) -> dict | None:
    for col in df.columns:
        if df[col].dtype in (pl.Date, pl.Datetime):
            series = df[col].drop_nulls()
            if series.len() == 0:
                continue
            return {
                "column": col,
                "min": str(series.min()),
                "max": str(series.max()),
            }
    return None


def _distributions(df: pl.DataFrame) -> dict:
    out = {}
    for col in df.columns:
        if df[col].dtype.is_numeric():
            series = df[col].drop_nulls()
            if series.len() == 0:
                continue
            out[col] = {
                "mean": float(series.mean()),
                "min": series.min(),
                "max": series.max(),
                "std": float(series.std()) if series.len() > 1 else 0.0,
            }
    return out


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
        "distributions": _distributions(df),
        "outliers": _detect_outliers(df),
        "date_range": _date_range(df),
        "pii_columns": _detect_pii(df),
    }
