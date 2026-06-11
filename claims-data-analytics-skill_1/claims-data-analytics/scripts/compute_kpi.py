"""
Step 3 of the upload workflow: compute a metric and return the value PLUS a full
audit trail so every answer can be cited and explained.

Two layers:
  1. A generic engine (count / distinct-count / sum / average / median / ratio)
     driven by the metric's `computation` hint in the catalogue. Good for the
     ~standard metrics once the relevant column(s) are confirmed.
  2. A registry of exact formulas for metrics whose definition is a specific
     calculation (incurred, the ratios, nominal-reserve logic). These override
     the generic engine.

Every result is returned as:
    {
      "value": <number>,
      "audit": {
        "metric", "app", "definition", "provenance",
        "method", "columns_used", "rows_used", "filters", "caveats"
      }
    }
The agent MUST surface the audit block to the user as the "how this was
generated" + citations section. Do not report a value without it.
"""
from __future__ import annotations
import pandas as pd


# ---------------------------------------------------------------- helpers ---
def _col(df, cols, canonical):
    name = cols.get(canonical, canonical)
    if name not in df.columns:
        raise KeyError(f"Field '{canonical}' (column '{name}') not in the uploaded data.")
    return name


def _audit(metric, app, defn, prov, method, columns, rows, filters, caveats):
    return {"metric": metric, "app": app, "definition": defn, "provenance": prov,
            "method": method, "columns_used": columns, "rows_used": int(rows),
            "filters": filters or "none", "caveats": caveats}


# -------------------------------------------------- generic engine ----------
def generic(df, meta, cols, value_col=None, id_col=None,
            numerator_col=None, denominator_col=None, filters=None):
    """meta = catalogue entry dict (name/app/definition/provenance/computation)."""
    comp = meta.get("computation", "unspecified")
    name, app = meta["name"], meta["app"]
    defn, prov = meta["definition"], meta["provenance"]
    caveats = []
    if prov in ("IND", "PROP"):
        caveats.append(f"Definition is {prov}: confirm against your team's official definition.")

    if comp == "ratio":
        if not (numerator_col and denominator_col):
            raise ValueError(f"'{name}' is a ratio: specify numerator_col and denominator_col.")
        n = df[_col(df, cols, numerator_col)].fillna(0).sum()
        d = df[_col(df, cols, denominator_col)].fillna(0).sum()
        val = (float(n) / float(d) * 100) if d else None
        return {"value": val, "audit": _audit(name, app, defn, prov,
                f"100 * sum({numerator_col}) / sum({denominator_col})",
                [numerator_col, denominator_col], len(df), filters, caveats)}

    if comp in ("sum", "sum_or_count") and value_col:
        c = _col(df, cols, value_col)
        val = float(df[c].fillna(0).sum())
        return {"value": val, "audit": _audit(name, app, defn, prov,
                f"sum({value_col})", [value_col], len(df), filters, caveats)}

    if comp in ("sum_or_count",) or (comp == "unspecified" and id_col):
        if id_col:
            c = _col(df, cols, id_col)
            val = int(df[c].nunique())
            caveats.append("Counted DISTINCT ids to avoid double-counting claims that span rows.")
            return {"value": val, "audit": _audit(name, app, defn, prov,
                    f"count_distinct({id_col})", [id_col], len(df), filters, caveats)}
        val = int(len(df))
        caveats.append("Counted rows; if a claim can span multiple rows, pass id_col for a distinct count.")
        return {"value": val, "audit": _audit(name, app, defn, prov,
                "row_count", ["(all rows)"], len(df), filters, caveats)}

    if comp == "average" and value_col:
        c = _col(df, cols, value_col)
        val = float(df[c].dropna().mean())
        return {"value": val, "audit": _audit(name, app, defn, prov,
                f"mean({value_col})", [value_col], df[c].notna().sum(), filters, caveats)}

    if comp == "median" and value_col:
        c = _col(df, cols, value_col)
        val = float(df[c].dropna().median())
        return {"value": val, "audit": _audit(name, app, defn, prov,
                f"median({value_col})", [value_col], df[c].notna().sum(), filters, caveats)}

    raise ValueError(
        f"Cannot compute '{name}' generically (computation='{comp}'). "
        f"Provide the right column argument(s) or add an exact formula to the registry."
    )


# ------------------------------------------------ exact formulas ------------
def usd_incurred(df, cols):
    ind = df[_col(df, cols, "USD Indemnity Paid")].fillna(0)
    exp = df[_col(df, cols, "USD Expense Paid")].fillna(0)
    res = df[_col(df, cols, "USD Indemnity Reserve")].fillna(0)
    rec = df[_col(df, cols, "USD Recovery")].fillna(0)
    return float((ind + exp + res - rec).sum())  # recoveries SUBTRACTED


def _flagsum(df, cols, canonical):
    return float(df[_col(df, cols, canonical)].fillna(0).sum())


def _flag_ratio(df, cols, num, den_canons):
    """num / sum(dens) over flag sums, None on a zero denominator.
    Each flag column is summed once (the denominator first, as before)."""
    den = sum(_flagsum(df, cols, c) for c in den_canons)
    return (_flagsum(df, cols, num) / den) if den else None


REGISTRY = {
    ("MAR-Operational", "USD Incurred"):
        lambda df, cols: usd_incurred(df, cols),
    ("MAR-Operational", "Closing Ratio"):
        lambda df, cols: _flag_ratio(df, cols, "Closed Flag", ["Opened Flag"]),
    ("MAR-Operational", "Net Closing Ratio"):
        lambda df, cols: _flag_ratio(df, cols, "Closed Flag", ["Opened Flag", "Reopened Flag"]),
    ("MAR-Operational", "Reopened Ratio"):
        lambda df, cols: _flag_ratio(df, cols, "Reopened Flag", ["Closed Flag"]),
}


def compute(meta, df, cols=None, **kwargs):
    """meta: catalogue entry dict. Returns {'value', 'audit'}."""
    cols = cols or {}

    # App-specific modules (exact Qlik translations) take priority.
    if meta["app"] in ("MAR-Operational", "MAR Operational"):
        import mar_operational as mar
        if meta["name"] in mar.REGISTRY:
            return mar.compute(meta["name"], df, cols, grain=kwargs.get("grain", "claim"))

    key = (meta["app"], meta["name"])
    if key in REGISTRY:
        val = REGISTRY[key](df, cols)
        caveats = []
        if meta["provenance"] in ("IND", "PROP"):
            caveats.append(f"Definition is {meta['provenance']}: confirm with the owning team.")
        return {"value": val, "audit": _audit(meta["name"], meta["app"], meta["definition"],
                meta["provenance"], "exact formula (see business_rules.md)",
                ["per formula"], len(df), kwargs.get("filters"), caveats)}
    return generic(df, meta, cols, **kwargs)
