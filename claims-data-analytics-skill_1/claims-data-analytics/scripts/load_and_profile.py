"""
Step 1 of the upload workflow: profile an uploaded Excel/CSV.

Returns the sheets, their columns, dtypes, row counts and a small sample, so the
agent knows the shape of the data BEFORE trying to answer anything. Never assume
the layout — always profile first.

Usage:
    from load_and_profile import profile
    info = profile("/mnt/user-data/uploads/whatever.xlsx")
"""
from __future__ import annotations
import pandas as pd

try:
    import numpy as np
except Exception:                       # pandas ships numpy; belt-and-braces only
    np = None


def profile(path: str, sample_rows: int = 3) -> dict:
    out = {"path": path, "sheets": []}
    if path.lower().endswith((".csv", ".tsv")):
        sep = "\t" if path.lower().endswith(".tsv") else ","
        df = pd.read_csv(path, sep=sep)
        out["sheets"].append(_sheet_info("(csv)", df, sample_rows))
        return out
    with pd.ExcelFile(path) as xl:
        for name in xl.sheet_names:
            df = xl.parse(name)
            out["sheets"].append(_sheet_info(name, df, sample_rows))
    return out


def _sheet_info(name, df, sample_rows):
    return {
        "sheet": name,
        "rows": int(len(df)),
        "columns": [
            {"name": str(c), "dtype": str(df[c].dtype),
             "non_null": int(df[c].notna().sum()),
             "sample": [None if pd.isna(v) else _coerce(v)
                        for v in df[c].dropna().head(sample_rows).tolist()]}
            for c in df.columns
        ],
    }


def _coerce(v):
    if np is not None:
        if isinstance(v, np.integer): return int(v)
        if isinstance(v, np.floating): return float(v)
    return str(v)
