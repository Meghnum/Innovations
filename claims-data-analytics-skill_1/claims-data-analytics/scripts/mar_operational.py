"""
MAR-Operational KPIs — faithful Python translations of the live Qlik expressions
(KPI_List Sheet2). Each returns {'value', 'audit'} for citation.

Key fidelity points reproduced from the Qlik:
- grain switch (vClaimsSources): grain='claim' uses CLAIM_NUMBER + *_CLAIM_*
  indicators; grain='claimant' uses CLAIM_CLAIMANT_NUMBER + *_CLAIMANT_*.
- aggr(count(DISTINCT id), <dims>) => distinct-per-period: group by the dims,
  count distinct ids, then sum. NOT a global distinct count.
- set filters {<IND={'1'}>} => row filter IND == '1' (string-safe).
Indicators are compared as strings because '1'/'2' may load as int or text.
"""
from __future__ import annotations
import pandas as pd

GRAINS = {
    "claim":    {"id": "CLAIM_NUMBER",          "sfx": "CLAIM"},
    "claimant": {"id": "CLAIM_CLAIMANT_NUMBER", "sfx": "CLAIMANT"},
}


def _col(df, cols, canon):
    name = cols.get(canon, canon)
    if name not in df.columns:
        raise KeyError(f"MAR-Operational needs field '{canon}' (column '{name}') — not in upload.")
    return name


def _eq(df, cols, canon, val):
    # string-compare per DISTINCT value, then a C-path isin — equivalent to
    # astype(str).str.strip() == str(val) without casting the whole column
    s = df[_col(df, cols, canon)]
    u = s.dropna().unique()
    match = (pd.Series(u).astype(str).str.strip() == str(val)).to_numpy()
    return s.isin(u[match])


def _mask(df, cols, conds):
    m = pd.Series(True, index=df.index)
    for canon, val in conds.items():
        m &= _eq(df, cols, canon, val)
    return m


def _filter(df, cols, conds):
    return df[_mask(df, cols, conds)]


def _distinct_per_period(df, cols, id_canon, dim_canons, conds):
    m = _mask(df, cols, conds)
    idc = _col(df, cols, id_canon)
    if not dim_canons:
        return int(df.loc[m, idc].nunique())
    dims = [_col(df, cols, d) for d in dim_canons]
    # slice only the columns the count needs — these exports are wide
    sub = df.loc[m, dims + [idc]]
    if sub.empty:
        return 0
    return int(sub.groupby(dims)[idc].nunique().sum())


def _ind(sfx, kind):  # kind in NEW/CLOSED/REOPENED/PENDING
    return f"{kind}_{sfx}_INDICATOR"


def _aud(name, method, cols_used, conds, caveats=None):
    return {"metric": name, "app": "MAR-Operational", "provenance": "OWNER",
            "method": method, "columns_used": cols_used,
            "filters": conds or "none", "caveats": caveats or []}


# ---- KPIs ------------------------------------------------------------------
def closing_ratio(df, cols, grain="claim"):
    g = GRAINS[grain]; idc, s = g["id"], g["sfx"]
    num = _distinct_per_period(df, cols, idc, ["MonthYear"], {_ind(s,"CLOSED"):1})
    den = _distinct_per_period(df, cols, idc, ["MonthYear"], {_ind(s,"NEW"):1})
    val = num/den if den else None
    return {"value": val, "audit": _aud("Closing Ratio",
        f"sum_over_MonthYear(distinct {idc} where {_ind(s,'CLOSED')}=1) / "
        f"sum_over_MonthYear(distinct {idc} where {_ind(s,'NEW')}=1)",
        [idc, _ind(s,"CLOSED"), _ind(s,"NEW"), "MonthYear"], {"grain": grain})}


def total_new_claims(df, cols, grain="claim"):
    g = GRAINS[grain]; idc, s = g["id"], g["sfx"]
    val = _distinct_per_period(df, cols, idc, ["MonthYear"], {_ind(s,"NEW"):1})
    return {"value": val, "audit": _aud("Total New Claims",
        f"sum_over_MonthYear(distinct {idc} where {_ind(s,'NEW')}=1)",
        [idc, _ind(s,"NEW"), "MonthYear"], {"grain": grain})}


def total_closed_claims(df, cols, grain="claim"):
    g = GRAINS[grain]; idc, s = g["id"], g["sfx"]
    val = _distinct_per_period(df, cols, idc, ["MonthYear"], {_ind(s,"CLOSED"):1})
    return {"value": val, "audit": _aud("Total Closed Claims",
        f"sum_over_MonthYear(distinct {idc} where {_ind(s,'CLOSED')}=1)",
        [idc, _ind(s,"CLOSED"), "MonthYear"], {"grain": grain})}


def net_closing_ratio(df, cols, grain="claim"):
    g = GRAINS[grain]; idc, s = g["id"], g["sfx"]
    num = _distinct_per_period(df, cols, idc, ["MonthYear"], {_ind(s,"CLOSED"):1})
    new = _distinct_per_period(df, cols, idc, ["MonthYear"], {_ind(s,"NEW"):1})
    reo = _distinct_per_period(df, cols, idc, ["MonthYear"], {_ind(s,"REOPENED"):1})
    den = new + reo
    val = num/den if den else None
    return {"value": val, "audit": _aud("Net Closing Ratio",
        f"closed / (new + reopened), each sum_over_MonthYear(distinct {idc})",
        [idc, _ind(s,"CLOSED"), _ind(s,"NEW"), _ind(s,"REOPENED"), "MonthYear"], {"grain": grain})}


def pending_claims_count(df, cols, grain="claim"):
    g = GRAINS[grain]; idc, s = g["id"], g["sfx"]
    val = _distinct_per_period(df, cols, idc, ["MonthYear","COG_COUNTRY"], {_ind(s,"PENDING"):1})
    return {"value": val, "audit": _aud("Pending Claims Count",
        f"sum_over_(MonthYear,COG_COUNTRY)(distinct {idc} where {_ind(s,'PENDING')}=1)",
        [idc, _ind(s,"PENDING"), "MonthYear", "COG_COUNTRY"], {"grain": grain})}


def reopened_ratio(df, cols, grain="claim"):
    g = GRAINS[grain]; idc, s = g["id"], g["sfx"]
    num = _distinct_per_period(df, cols, idc, ["MonthYear","COG_COUNTRY"], {_ind(s,"REOPENED"):1})
    den = _distinct_per_period(df, cols, idc, ["MonthYear","COG_COUNTRY"], {_ind(s,"CLOSED"):1})
    val = num/den if den else None
    return {"value": val, "audit": _aud("Reopened Ratio",
        f"reopened / closed, each sum_over_(MonthYear,COG_COUNTRY)(distinct {idc})",
        [idc, _ind(s,"REOPENED"), _ind(s,"CLOSED"), "MonthYear", "COG_COUNTRY"], {"grain": grain})}


# ---- claim-grain-only KPIs (no claimant variant in source) -----------------
def volume_1yr_static(df, cols, grain="claim"):
    val = _distinct_per_period(df, cols, "CLAIM_NUMBER", [],
                               {"PENDING_CLAIM_INDICATOR":1, "STATIC_CLAIM_INDICATOR":2})
    return {"value": val, "audit": _aud("Volume - 1 Year Static Claims",
        "distinct CLAIM_NUMBER where PENDING=1 and STATIC_CLAIM_INDICATOR=2",
        ["CLAIM_NUMBER","PENDING_CLAIM_INDICATOR","STATIC_CLAIM_INDICATOR"], None)}


def average_time_to_settle(df, cols, grain="claim"):
    m = _mask(df, cols, {"CLOSED_CLAIM_INDICATOR":1})
    my, cn, ld = _col(df,cols,"MonthYear"), _col(df,cols,"CLAIM_NUMBER"), _col(df,cols,"CLAIM_LIFE_DAYS_NUMBER")
    inner = df.loc[m, [my, cn, ld]].groupby([my, cn])[ld].mean()
    val = float(inner.mean()) if len(inner) else None
    return {"value": val, "audit": _aud("Average Time to Settle",
        "avg over (MonthYear,CLAIM_NUMBER) of avg(CLAIM_LIFE_DAYS_NUMBER) where CLOSED=1",
        ["CLAIM_LIFE_DAYS_NUMBER","CLOSED_CLAIM_INDICATOR","MonthYear","CLAIM_NUMBER"], None,
        ["Same formula as 'Time to Settle' in source."])}


def acpsc(df, cols, grain="claim"):
    m = _mask(df, cols, {"CLOSED_CLAIM_INDICATOR":1})
    c = _col(df,cols,"INCURRED_TOTAL_GROSS_USD_AMT")
    s = df.loc[m, c]
    val = float(s.mean()) if len(s) else None
    return {"value": val, "audit": _aud("ACPSC",
        "mean(INCURRED_TOTAL_GROSS_USD_AMT) over rows where CLOSED=1",
        ["INCURRED_TOTAL_GROSS_USD_AMT","CLOSED_CLAIM_INDICATOR"], None,
        ["Row-level average per source definition (incurred of closed / count)."])}


def acpoc(df, cols, grain="claim"):
    m = _mask(df, cols, {"PENDING_CLAIM_INDICATOR":1})
    c = _col(df,cols,"INCURRED_TOTAL_GROSS_USD_AMT")
    s = df.loc[m, c]
    val = float(s.mean()) if len(s) else None
    return {"value": val, "audit": _aud("ACPOC",
        "mean(INCURRED_TOTAL_GROSS_USD_AMT) over rows where PENDING=1",
        ["INCURRED_TOTAL_GROSS_USD_AMT","PENDING_CLAIM_INDICATOR"], None)}


def age_under_6m(df, cols, grain="claim"):
    a = _distinct_per_period(df, cols, "CLAIM_NUMBER", [], {"PENDING_CLAIM_INDICATOR":1, "CLAIM_LIFE_BANDING":"1) 0-3 Months"})
    b = _distinct_per_period(df, cols, "CLAIM_NUMBER", [], {"PENDING_CLAIM_INDICATOR":1, "CLAIM_LIFE_BANDING":"2) 3-6 Months"})
    return {"value": a+b, "audit": _aud("Age Profile - Under 6 Months",
        "distinct CLAIM_NUMBER (PENDING=1) in bandings '1) 0-3 Months' + '2) 3-6 Months'",
        ["CLAIM_NUMBER","PENDING_CLAIM_INDICATOR","CLAIM_LIFE_BANDING"], None)}


def age_6_12m(df, cols, grain="claim"):
    a = _distinct_per_period(df, cols, "CLAIM_NUMBER", [], {"PENDING_CLAIM_INDICATOR":1, "CLAIM_LIFE_BANDING":"3) 6-9 Months"})
    b = _distinct_per_period(df, cols, "CLAIM_NUMBER", [], {"PENDING_CLAIM_INDICATOR":1, "CLAIM_LIFE_BANDING":"4) 9-12 Months"})
    return {"value": a+b, "audit": _aud("Age Profile - 6-12 Months",
        "distinct CLAIM_NUMBER (PENDING=1) in bandings '3) 6-9 Months' + '4) 9-12 Months'",
        ["CLAIM_NUMBER","PENDING_CLAIM_INDICATOR","CLAIM_LIFE_BANDING"], None)}


def nominal_reserves(df, cols, grain="claim"):
    val = _distinct_per_period(df, cols, "CLAIM_NUMBER", [], {"NOMINAL_INDICATOR":1})
    return {"value": val, "audit": _aud("Nominal Reserves",
        "distinct CLAIM_NUMBER where NOMINAL_INDICATOR=1",
        ["CLAIM_NUMBER","NOMINAL_INDICATOR"], None)}


def nominal_age(df, cols, grain="claim"):
    m = _mask(df, cols, {"NOMINAL_INDICATOR":1})
    my, ld = _col(df,cols,"MonthYear"), _col(df,cols,"CLAIM_LIFE_DAYS_NUMBER")
    inner = df.loc[m, [my, ld]].groupby(my)[ld].mean()
    val = float(inner.mean()) if len(inner) else None
    return {"value": val, "audit": _aud("Nominal Age",
        "avg over MonthYear of avg(CLAIM_LIFE_DAYS_NUMBER) where NOMINAL=1",
        ["CLAIM_LIFE_DAYS_NUMBER","NOMINAL_INDICATOR","MonthYear"], None)}


def reserve_completion_0_30(df, cols, grain="claim"):
    a = _distinct_per_period(df, cols, "CLAIM_NUMBER", [], {"REGISTRATION_INDICATOR":1, "NEW_CLAIM_INDICATOR":1})
    b = _distinct_per_period(df, cols, "CLAIM_NUMBER", [], {"REGISTRATION_INDICATOR":0, "NEW_CLAIM_INDICATOR":1})
    val = a/(a+b) if (a+b) else None
    return {"value": val, "audit": _aud("Reserve Completion (0-30 Calendar Days)",
        "registered new / (registered new + unregistered new), distinct CLAIM_NUMBER",
        ["CLAIM_NUMBER","REGISTRATION_INDICATOR","NEW_CLAIM_INDICATOR"], None)}


def inactive_claims_270(df, cols, grain="claim"):
    val = _distinct_per_period(df, cols, "CLAIM_NUMBER", [], {"PENDING_CLAIM_INDICATOR":1, "INACTIVE_INDICATOR":1})
    return {"value": val, "audit": _aud("Inactive Claims (>270 Days)",
        "distinct CLAIM_NUMBER where PENDING=1 and INACTIVE=1",
        ["CLAIM_NUMBER","PENDING_CLAIM_INDICATOR","INACTIVE_INDICATOR"], None)}


REGISTRY = {
    "Closing Ratio": closing_ratio,
    "Total New Claims": total_new_claims,
    "Total Closed Claims": total_closed_claims,
    "Net Closing Ratio": net_closing_ratio,
    "Pending Claims Count": pending_claims_count,
    "Reopened Ratio": reopened_ratio,
    "Volume - 1 Year Static Claims": volume_1yr_static,
    "Time to Settle": average_time_to_settle,
    "Average Time to Settle": average_time_to_settle,
    "ACPSC": acpsc,
    "ACPOC": acpoc,
    "Age Profile - Under 6 Months Old": age_under_6m,
    "Age Profile - 6 - 12 Months": age_6_12m,
    "Nominal Reserves": nominal_reserves,
    "Nominal Age": nominal_age,
    "Reserve Completion (0-30 Calendar Days)": reserve_completion_0_30,
    "Inactive Claims (>270 Days)": inactive_claims_270,
}

# canonical columns this app expects (for resolve_columns / validation)
CANONICAL_COLUMNS = [
    "CLAIM_NUMBER","CLAIM_CLAIMANT_NUMBER","MonthYear","COG_COUNTRY","CLAIM_LIFE_BANDING",
    "CLAIM_LIFE_DAYS_NUMBER","INCURRED_TOTAL_GROSS_USD_AMT",
    "NEW_CLAIM_INDICATOR","CLOSED_CLAIM_INDICATOR","REOPENED_CLAIM_INDICATOR","PENDING_CLAIM_INDICATOR",
    "NEW_CLAIMANT_INDICATOR","CLOSED_CLAIMANT_INDICATOR","REOPENED_CLAIMANT_INDICATOR","PENDING_CLAIMANT_INDICATOR",
    "STATIC_CLAIM_INDICATOR","NOMINAL_INDICATOR","REGISTRATION_INDICATOR","INACTIVE_INDICATOR",
]


def compute(kpi: str, df: pd.DataFrame, cols=None, grain: str = "claim") -> dict:
    """Run one MAR-Operational KPI. Returns {'value', 'audit'};
    raises KeyError for unknown KPIs or missing required columns."""
    cols = cols or {}
    if kpi not in REGISTRY:
        raise KeyError(f"No MAR-Operational implementation for '{kpi}'. Available: {sorted(REGISTRY)}")
    return REGISTRY[kpi](df, cols, grain)
