"""
Step 1 of the upload workflow: profile an uploaded Excel/CSV.

Returns the sheets, their columns, dtypes, row counts and a small sample, so the
agent knows the shape of the data BEFORE trying to answer anything. Never assume
the layout — always profile first.

Trust model: reads exactly the file it is given (the caller's own upload),
resolved to a real absolute path. Set the CLAIMS_DATA_ROOT environment variable
to confine reads to one directory (e.g. the upload area) — paths outside it are
refused. Failures return {"path", "error"} instead of raising. Sample values
that look like personal data (emails, SSN-format ids, long digit runs) are
masked, and columns whose NAME suggests PII are fully redacted — the profile
dict travels into logs/LLM context, so raw identifiers must not ride along.

Usage:
    from load_and_profile import profile
    info = profile("/mnt/user-data/uploads/whatever.xlsx")
"""
from __future__ import annotations
import os
import re

import pandas as pd

try:
    import numpy as np
except Exception:                       # pandas ships numpy; belt-and-braces only
    np = None

_ALLOWED_EXTS = (".csv", ".tsv", ".xlsx", ".xlsm", ".xls")

# sample-redaction patterns (full-value matches / name hints)
_EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SSN_RX = re.compile(r"^\d{3}-\d{2}-\d{4}$")
_PII_NAME_RX = re.compile(
    r"(?i)(ssn|social.?security|e-?mail|phone|mobile|home.?address|street|postcode|"
    r"zip.?code|dob|date.?of.?birth|passport|national.?id|tax.?id|credit.?card|"
    r"card.?n|\bcard\b|iban|account.?n|claimant.?name|first.?name|last.?name|surname)"
)
_MIN_ID_DIGITS = 9   # int-like values this long look like phone/account/card numbers


def _mask(value_str: str):
    """Masked form of a PII-looking value, or None when it looks clean."""
    if _EMAIL_RX.match(value_str):
        dot = value_str.rfind(".")
        return value_str[0] + "***@***" + value_str[dot:]
    if _SSN_RX.match(value_str):
        return "***-**-" + value_str[-4:]
    digits = re.sub(r"\D", "", value_str)
    # long pure-digit identifiers (cards, phones, accounts) — keep the shape
    if len(digits) >= _MIN_ID_DIGITS and re.fullmatch(r"[\d\s\-+()]+", value_str):
        return "*" * (len(digits) - 4) + digits[-4:]
    return None


def _sample_value(v, name_is_pii: bool):
    if name_is_pii:
        return "[redacted]"
    coerced = _coerce(v)
    masked = _mask(str(coerced))
    return masked if masked is not None else coerced


def profile(path: str, sample_rows: int = 3) -> dict:
    """Profile a CSV/TSV/XLSX upload. Returns {"path", "sheets": [...]} or
    {"path", "error": <plain reason>} — never an exception for bad input."""
    p = os.path.realpath(path)
    root = os.environ.get("CLAIMS_DATA_ROOT")
    if root and not p.startswith(os.path.realpath(root) + os.sep):
        return {"path": path, "error": "path is outside the allowed data directory "
                                       "(CLAIMS_DATA_ROOT)"}
    if not os.path.isfile(p):
        return {"path": path, "error": f"file not found: {path}"}
    ext = os.path.splitext(p)[1].lower()
    if ext not in _ALLOWED_EXTS:
        return {"path": path, "error": f"unsupported file type '{ext}' "
                                       f"(expected one of: {', '.join(_ALLOWED_EXTS)})"}
    out = {"path": path, "sheets": []}
    try:
        if ext in (".csv", ".tsv"):
            sep = "\t" if ext == ".tsv" else ","
            df = pd.read_csv(p, sep=sep)
            out["sheets"].append(_sheet_info("(csv)", df, sample_rows))
            return out
        with pd.ExcelFile(p) as xl:
            for name in xl.sheet_names:
                df = xl.parse(name)
                out["sheets"].append(_sheet_info(name, df, sample_rows))
        return out
    except Exception as e:
        return {"path": path, "error": f"parse failed: {e}"}


def _sheet_info(name, df, sample_rows):
    return {
        "sheet": name,
        "rows": int(len(df)),
        "columns": [
            {"name": str(c), "dtype": str(df[c].dtype),
             "non_null": int(df[c].notna().sum()),
             "sample": [_sample_value(v, bool(_PII_NAME_RX.search(str(c))))
                        for v in df[c].dropna().head(sample_rows).tolist()]}
            for c in df.columns
        ],
    }


def _coerce(v):
    if np is not None:
        if isinstance(v, np.integer): return int(v)
        if isinstance(v, np.floating): return float(v)
    return str(v)
