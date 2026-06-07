"""
Filter-agnostic claims engine (glossary-driven, no indicator assumptions).

  resolve_schema(columns)  -> map real headers to canonical concepts
  derive_state(df, schema) -> closed/open/pending/reopened/declined from real cols
  compute(metric, ...)     -> apply KPI logic; {value,audit} or {needs,reason}

Status derivation is pinned to real values:
  - Claim Status Derived / Claim Status Original take 'closed' | 'open' (exact).
  - Reopened comes from the reopened-date column (status has no 'reopened' value).
  - Genius Claim Status has many values -> NOT used to auto-derive state; the
    engine asks for a value->state mapping if that's all there is.
"""
from __future__ import annotations
import json, os, re
import pandas as pd

_HERE = os.path.dirname(__file__)
try:
    _RAW = json.load(open(os.path.join(_HERE, "..", "assets", "kpi_catalogue.json")))
except Exception:
    _RAW = []
if isinstance(_RAW, dict):                 # new form: {apps, rag_thresholds, metrics, locations}
    _CAT  = _RAW.get("metrics", [])
    _APPS = _RAW.get("apps", {})
    _RAG  = _RAW.get("rag_thresholds", {})
    _LOCATIONS = _RAW.get("locations", [])
    _ENTITY_MAP = _RAW.get("entity_map", {})
else:                                       # legacy form: a bare list of metrics
    _CAT, _APPS, _RAG, _LOCATIONS, _ENTITY_MAP = _RAW, {}, {}, [], {}
_CAT_BY_NAME = {}
for m in _CAT:
    _CAT_BY_NAME.setdefault(re.sub(r"[^a-z0-9]", "", m["name"].lower()), m)


def where_to_see(query):
    """Which app(s) hold a metric, with link placeholders — for 'where can I see X' questions.
    Prefers exact name matches, then prefix, then contains; returns every app for the best tier."""
    q = re.sub(r"[^a-z0-9]", "", str(query).lower())
    qs = q.rstrip("s")
    exact, prefix, contains = [], [], []
    for m in _CAT:
        nm = re.sub(r"[^a-z0-9]", "", m["name"].lower())
        app = m.get("app"); info = _APPS.get(app, {})
        row = {"metric": m["name"], "app": info.get("display", app), "url": info.get("url")}
        if nm == q or nm == qs:
            exact.append(row)
        elif qs and nm.startswith(qs):
            prefix.append(row)
        elif qs and qs in nm:
            contains.append(row)
    best = exact or prefix or contains
    out, seen = [], set()
    for r in best:
        k = (r["metric"], r["app"])
        if k not in seen:
            seen.add(k); out.append(r)
    return out


def rag_for(metric):
    """Owner-documented Red/Amber/Green thresholds for a metric, if any."""
    return _RAG.get(re.sub(r"[^a-z0-9]", "", str(metric).lower()))

def _n(s): return re.sub(r"[^a-z0-9]", "", str(s).lower())

try:
    _STATUS_MAP = json.load(open(os.path.join(_HERE, "..", "assets", "status_value_map.json")))
except Exception:
    _STATUS_MAP = {}


CLOSED_VALUES = {"closed"}
OPEN_VALUES   = {"open"}

CONCEPTS = {
    "claim_id":          ["Claim Number", "CLAIM_NUMBER"],
    "claimant_id":       ["CLAIM_CLAIMANT_NUMBER", "Claim Claimant Number"],
    "status_derived":    ["Claim Status Derived"],
    "status_original":   ["Claim Status Original", "Claim Status"],
    "status_genius":     ["Genius Claim Status"],
    "status_secondary":  ["Claim Secondary Status", "Secondary Claim Status", "File Secondary Status"],
    "reported_date":     ["Reported Date", "Claim Report Date"],
    "opened_date":       ["Opened Date", "Claim Opened Date", "Clam Opened Date"],
    "closed_date":       ["Closed Date", "Claim Closed Date"],
    "reopened_date":     ["Reopened Date"],
    "period_month":      ["Month", "MonthYear"],
    "accident_year":     ["Accident Year"],
    "country":           ["COG_COUNTRY", "Country", "Policy Country"],
    "life_days":         ["Claim Life Days", "CLAIM_LIFE_DAYS_NUMBER"],
    "life_banding":      ["Claim Life Banding", "CLAIM_LIFE_BANDING"],
    "nominal_reserve":   ["Nominal Reserve", "NOMINAL_INDICATOR"],
    "incurred_usd":      ["Incurred (USD)", "USD Incurred", "Incurred USD", "INCURRED_TOTAL_GROSS_USD_AMT", "$ Claims Incurred"],
    "indemnity_paid_usd":["Indemnity (USD)", "USD Indemnity Paid", "Indemnity Paid USD"],
    "expense_paid_usd":  ["Expense Total (USD)", "USD Expense Paid", "Expense Paid USD"],
    "recovery_usd":      ["USD Recovery", "Recoveries USD", "Gross Recoveries"],
    "oslr_usd":          ["OSLR Total (USD)", "Outstanding Reserve USD"],
}


# concept aliases may be overridden/extended from config (assets/column_synonyms.json),
# keeping the in-code dict above only as a default.
try:
    _cs = json.load(open(os.path.join(_HERE, "..", "assets", "column_synonyms.json")))
    if isinstance(_cs.get("concept_aliases"), dict) and _cs["concept_aliases"]:
        CONCEPTS = _cs["concept_aliases"]
except Exception:
    pass


def resolve_schema(columns):
    n2a = {_n(c): c for c in columns}
    schema, used = {}, set()
    for concept, names in CONCEPTS.items():
        for name in names:
            a = n2a.get(_n(name))
            if a:
                schema[concept] = a; used.add(a); break
    return {"concepts": schema, "unmapped": [c for c in columns if c not in used]}


def status_columns(schema):
    """Status columns present, in preference order, with their concept name."""
    c = schema["concepts"]; out = []
    for k in ("status_secondary", "status_derived", "status_original", "status_genius"):
        if c.get(k): out.append((k, c[k]))
    return out


def distinct_values(df, col):
    return sorted(df[col].dropna().astype(str).str.strip().unique().tolist())


def _status_mask(df, schema, state):
    """Mask for a canonical state ('closed'/'open'/'pending') or sub-state
    ('reopened'/'closed_after_reopened'), using the recorded status value map
    (assets/status_value_map.json). Nothing about the values is hardcoded here —
    it comes from that map. Returns (mask, how) or (None, reason)."""
    c = schema["concepts"]
    target = "open" if state == "pending" else state

    # sub-states live only in their named layer, matched by literal value
    subs = _STATUS_MAP.get("sub_states", {})
    if target in subs:
        spec = subs[target]; col = c.get(spec["concept"])
        if col and col in df.columns:
            v = df[col].astype(str).str.strip().str.lower()
            return v == spec["value"].lower(), f"{col} == '{spec['value']}'"
        return None, f"sub-state '{target}' needs {spec['concept']} (not in file)"

    # canonical open/closed via the value map, preferring derived > original > secondary
    if target in _STATUS_MAP.get("canonical_states", ["open", "closed"]):
        for concept in _STATUS_MAP.get("preference_for_open_closed",
                                       ["status_derived", "status_original", "status_secondary"]):
            col = c.get(concept)
            if col and col in df.columns and concept in _STATUS_MAP:
                vmap = {k.lower(): val for k, val in _STATUS_MAP[concept]["values"].items()}
                mapped = df[col].astype(str).str.strip().str.lower().map(vmap)
                if target in set(mapped.dropna().unique()):
                    return mapped == target, f"{col} -> '{target}' (recorded value map)"
        # date fallback only if no status column resolved it
        if target == "closed" and c.get("closed_date"):
            return df[c["closed_date"]].notna(), f"{c['closed_date']} populated"
        if target == "open" and c.get("closed_date"):
            return df[c["closed_date"]].isna(), f"{c['closed_date']} empty"

    present = [col for _, col in status_columns(schema)]
    return None, (f"state '{state}' not resolvable from status column(s) "
                  f"{present or '(none present)'} via the value map — confirm which "
                  f"column/value represents it (e.g. 'declined' is not in the map yet)")


def derive_state(df, schema):
    """Thin wrapper kept for the audit: reports which status columns/values exist."""
    cols = status_columns(schema)
    methods = {concept: f"{col} values: {distinct_values(df, col)[:8]}" for concept, col in cols}
    return {}, methods


# ---- explicit specs (kind, arg) ----
_C = lambda p: ("count", p)
_S = lambda meas: ("sum", meas)
_M = lambda meas, pop: ("mean", (meas, pop))
_MED = lambda meas, pop: ("median", (meas, pop))
_R = lambda n, d: ("ratio", (n, d))
_LIFE = lambda pop: ("life_avg", pop)

SPECS = {
    # counts
    "Closed Claims Count": _C("closed"), "Total Closed Claims": _C("closed"),
    "Closed Volumes": _C("closed"), "Closed Claim Count": _C("closed"),
    "New Claims Count": _C("new"), "Total New Claims": _C("new"),
    "New Volumes": _C("new"), "New Claim Count": _C("new"), "New Claims": _C("new"),
    "Pending Claims Count": _C("pending"), "Pending Claims": _C("pending"),
    "Pending Claim Count": _C("pending"), "Open Claims Count": _C("open"),
    "Reopened Claims Count": _C("reopened"), "Total Reopened Claims": _C("reopened"),
    "Reopened Claim Count": _C("reopened"),
    "Declined Claims": _C("declined"), "Total Declined": _C("declined"),
    # ratios
    "Closing Ratio": _R("closed", "new"),
    "Net Closing Ratio": _R("closed", ("new", "reopened")),
    "Reopened Ratio": _R("reopened", "closed"),
    # financial sums (over the slice)
    "Total Incurred (USD)": _S("incurred_usd"), "Claims Incurred": _S("incurred_usd"),
    "$ Claims Incurred": _S("incurred_usd"), "Indemnity Paid (USD)": _S("indemnity_paid_usd"),
    "$ Indemnity Paid (CGM Share)": _S("indemnity_paid_usd"),
    "Expense and Fees Paid (CGM Share)": _S("expense_paid_usd"),
    "Gross Recoveries": _S("recovery_usd"), "O/S Reserve": _S("oslr_usd"),
    "Outstanding Reserve for Open Claims (CGM Share)": _S("oslr_usd"),
    # averages / medians
    "ACPSC": _M("incurred_usd", "closed"), "ACPOC": _M("incurred_usd", "pending"),
    "Average Claims Cost": _M("incurred_usd", "all"),
    "Average Cycle Time": _LIFE("closed"), "Average Time to Settle": _LIFE("closed"),
    "Time to Settle": _LIFE("closed"),
    "Median Cycle Time": _MED("life_days", "closed"),
}

# ---- catalogue-driven fallback inference ----
# Hints are maintained in assets/inference_hints.json (not in code). Built-in
# defaults are a safety net only if that file is missing.
_DEFAULT_HINTS = {
    "population_hints": [["closed","closed"],["new","new"],["reopen","reopened"],
                         ["pending","pending"],["open","open"],["declin","declined"]],
    "measure_hints": [["incurred","incurred_usd"],["indemnity","indemnity_paid_usd"],
                      ["expense","expense_paid_usd"],["recover","recovery_usd"],
                      ["outstanding reserve","oslr_usd"],["oslr","oslr_usd"]],
    "life_keywords": ["cycle time","time to settle","claim life","days to settle","age "],
}
try:
    _HINTS = json.load(open(os.path.join(_HERE, "..", "assets", "inference_hints.json")))
except Exception:
    _HINTS = {}
_POP_HINTS  = _HINTS.get("population_hints", _DEFAULT_HINTS["population_hints"])
_MEAS_HINTS = _HINTS.get("measure_hints", _DEFAULT_HINTS["measure_hints"])
_LIFE_KW    = _HINTS.get("life_keywords", _DEFAULT_HINTS["life_keywords"])

def _infer(name, comp):
    nl = name.lower()
    pop = next((p for k,p in _POP_HINTS if k in nl), None)
    meas = next((m for k,m in _MEAS_HINTS if k in nl), None)
    if comp == "ratio":
        return None  # two populations not safely inferable -> ask
    if any(w in nl for w in _LIFE_KW):
        return _LIFE(pop or "closed")
    if comp in ("sum",) and meas: return _S(meas)
    if comp == "average":
        if meas: return _M(meas, pop or "all")
        return None
    if comp == "median" and meas: return _MED(meas, pop or "all")
    if comp in ("sum_or_count",):
        if meas: return _S(meas)
        return _C(pop or "all")
    return None


def _mask(df, schema, slice_is, pop):
    if pop == "all": return pd.Series(True, index=df.index), "all rows"
    if slice_is and re.sub(r"[^a-z0-9]","",str(slice_is).lower()) == re.sub(r"[^a-z0-9]","",str(pop).lower()):
        return pd.Series(True, index=df.index), f"file is the '{pop}' slice"
    return _status_mask(df, schema, pop)


def _distinct(df, schema, mask, period_cols):
    idc = schema["concepts"].get("claim_id")
    if not idc: return None, "no claim identifier column"
    sub = df[mask]
    if period_cols:
        pcs = [schema["concepts"].get(p, p) for p in period_cols]
        pcs = [p for p in pcs if p in df.columns]
        if pcs: return int(sub.groupby(pcs)[idc].nunique().sum()), f"distinct {idc} per {pcs}, summed"
    return int(sub[idc].nunique()), f"distinct {idc} (global)"


def compute(metric, df, schema, slice_is=None, period_cols=None, user_filter=None):
    spec = SPECS.get(metric); inferred = False
    if spec is None:
        entry = _CAT_BY_NAME.get(_n(metric))
        if entry is None:
            return {"needs": "definition", "reason": f"'{metric}' not in the catalogue."}
        spec = _infer(metric, entry.get("computation", ""))
        inferred = True
        if spec is None:
            return {"needs": "spec", "reason": (
                f"'{metric}' (definition: {entry['definition']}) needs its column(s)/"
                f"populations specified — I won't guess. Tell me the measure/filter.")}

    _, methods = derive_state(df, schema)
    if user_filter is not None: df = df[user_filter]
    kind, arg = spec
    aud = {"metric": metric, "slice_is": slice_is or "full population",
           "period": period_cols or "none", "derivations": methods,
           "spec_source": "inferred from catalogue (confirm)" if inferred else "explicit"}

    if kind == "count":
        m, how = _mask(df, schema, slice_is, arg)
        if m is None: return {"needs": arg, "reason": how}
        val, cm = _distinct(df, schema, m, period_cols)
        if val is None: return {"needs": "claim_id", "reason": cm}
        aud["method"] = f"{cm}; population {how}"; return {"value": val, "audit": aud}

    if kind == "ratio":
        num_pop, den = arg
        mn, hn = _mask(df, schema, slice_is, num_pop)
        if mn is None: return {"needs": num_pop, "reason": hn}
        num, _ = _distinct(df, schema, mn, period_cols)
        if isinstance(den, tuple):
            tot = 0
            for p in den:
                mp, hp = _mask(df, schema, slice_is, p)
                if mp is None: return {"needs": p, "reason": hp}
                v, _ = _distinct(df, schema, mp, period_cols); tot += v
            den_v, hd = tot, " + ".join(den)
        else:
            md, hd0 = _mask(df, schema, slice_is, den)
            if md is None: return {"needs": den, "reason": hd0}
            den_v, hd = _distinct(df, schema, md, period_cols)[0], den
        aud["method"] = f"distinct({num_pop}) / distinct({hd})"
        return {"value": (num/den_v if den_v else None), "audit": aud}

    if kind in ("sum", "mean", "median"):
        meas, pop = (arg, "all") if kind == "sum" else arg
        mc = schema["concepts"].get(meas)
        if not mc: return {"needs": meas, "reason": f"no column for measure '{meas}'"}
        m, how = _mask(df, schema, slice_is, pop)
        if m is None: return {"needs": pop, "reason": how}
        s = df[m][mc].dropna()
        val = float(s.sum()) if kind == "sum" else float(s.mean()) if kind == "mean" else float(s.median())
        aud["method"] = f"{kind}({mc}) over {how}"; return {"value": val, "audit": aud}

    if kind == "life_avg":
        lc = schema["concepts"].get("life_days"); idc = schema["concepts"].get("claim_id")
        pc = schema["concepts"].get("period_month")
        if not lc: return {"needs": "life_days", "reason": "no claim-life-days column"}
        m, how = _mask(df, schema, slice_is, arg)
        if m is None: return {"needs": arg, "reason": how}
        sub = df[m]
        if pc and idc:
            val = float(sub.groupby([pc, idc])[lc].mean().mean()); meth = f"avg over ({pc},{idc}) of mean({lc})"
        else:
            val = float(sub[lc].mean()); meth = f"mean({lc})"
        aud["method"] = f"{meth} over {how}"; return {"value": val, "audit": aud}


def breakdown(df, schema, by, agg="count", measure=None, user_filter=None):
    """General group-by: count distinct claims (or sum/mean/median of a measure)
    by ANY column. `by` may be a glossary concept or a literal header. Values are
    whatever is in the data — nothing about them is hardcoded."""
    col = schema["concepts"].get(by, by)
    if col not in df.columns:
        return {"needs": "column", "reason": f"column '{by}' not in the file."}
    if user_filter is not None: df = df[user_filter]
    g = df.groupby(df[col].astype(str).str.strip())
    idc = schema["concepts"].get("claim_id")
    if agg == "count":
        res = (g[idc].nunique() if idc else g.size())
        method = f"count distinct {idc or 'rows'} by {col}"
    else:
        mc = schema["concepts"].get(measure, measure)
        if mc not in df.columns:
            return {"needs": "measure", "reason": f"measure column '{measure}' not in the file."}
        res = getattr(g[mc], {"sum":"sum","mean":"mean","median":"median"}[agg])()
        method = f"{agg}({mc}) by {col}"
    out = {str(k): (int(v) if float(v).is_integer() else float(v)) for k, v in res.items()}
    return {"value": out, "total": sum(out.values()),
            "audit": {"breakdown_by": col, "agg": agg, "method": method,
                      "groups": len(out)}}


# ---- entity (Company vs CGM) derivation ---------------------------------
_ENT_EXACT = {}
for _src in ("entity_column", "business_entity_column"):
    for _k, _v in (_ENTITY_MAP.get(_src) or {}).items():
        _ENT_EXACT[_k.strip().lower()] = _v
_ENT_SUB = {k.strip().lower(): v for k, v in (_ENTITY_MAP.get("cgm_subtype") or {}).items()}


def resolve_entity(value):
    """Map a raw Entity / Business Entity value to canonical Company | CGM.
    Returns {entity, cgm_type, matched, source}. Unknown -> entity=None (ask, never guess)."""
    v = str(value).strip(); k = v.lower()
    if k in _ENT_EXACT:
        return {"entity": _ENT_EXACT[k], "cgm_type": _ENT_SUB.get(k), "matched": "exact", "source": v}
    if k.startswith("company") or k == "cegl":          # conservative, unambiguous only
        return {"entity": "Company", "cgm_type": None, "matched": "rule", "source": v}
    if "cgm" in k or "lirma" in k or "lloyds" in k:
        sub = "LIRMA" if ("lirma" in k or "cegl" in k) else ("Lloyds" if ("lloyds" in k or "cual" in k) else None)
        return {"entity": "CGM", "cgm_type": sub, "matched": "rule", "source": v}
    return {"entity": None, "cgm_type": None, "matched": None, "source": v}


def add_entity_column(df, schema):
    """Add canonical '__entity__' (Company | CGM | None) from the Business Entity column
    if present, else the Entity column. Returns (df, audit). Applies to MAR-Operational,
    MAR-Conduct and Claim One Stop exports."""
    c = schema["concepts"]
    src = c.get("business_entity") or c.get("entity")
    if not src or src not in df.columns:
        return df, {"needs": "entity column",
                    "reason": "no 'Business Entity' or 'Entity' column found in the file."}
    df = df.copy()
    df["__entity__"] = df[src].map(lambda x: resolve_entity(x)["entity"])
    unknown = sorted(df.loc[df["__entity__"].isna(), src].astype(str).str.strip().unique().tolist())
    return df, {"derived_from": src, "unmapped_values": unknown}


def entity_split(df, schema, measure=None, agg="count"):
    """Split by canonical entity (Company vs CGM): count distinct claims by default,
    or agg a measure. Surfaces any unmapped source values instead of guessing."""
    df2, info = add_entity_column(df, schema)
    if "needs" in info:
        return info
    out = breakdown(df2, schema, by="__entity__", agg=agg, measure=measure)
    if isinstance(out, dict) and "audit" in out:
        out["audit"]["entity_source"] = info["derived_from"]
        if info["unmapped_values"]:
            out["audit"]["unmapped_entity_values"] = info["unmapped_values"]
    return out


def where_to_find(query):
    """Where a metric/field actually lives: app + the exact Sheet(s) (the location),
    grounded in the KPI list's 'Sheet' column. Exact name match if one exists, else
    every field/metric whose name contains the term — grouped by app, with sheets and
    the matched variants (e.g. currency variants). Sheets cited come ONLY from the
    data; never invent one."""
    q = re.sub(r"[^a-z0-9]", "", str(query).lower()); qs = q.rstrip("s")
    def n(s): return re.sub(r"[^a-z0-9]", "", str(s).lower())
    # comprehensive: every field/metric whose name contains the term (location-finding
    # wants breadth, not a single exact hit)
    hits = [r for r in _LOCATIONS if qs and qs in n(r.get("name"))]
    out = {}
    for r in hits:
        app = r.get("app"); info = _APPS.get(app, {})
        d = out.setdefault(app, {"app": info.get("display", app), "url": info.get("url"),
                                 "primary": bool(info.get("primary")),
                                 "sheets": set(), "entities": set(), "variants": set()})
        if r.get("sheet"): d["sheets"].add(r["sheet"])
        if r.get("entity"): d["entities"].add(r["entity"])
        d["variants"].add(r.get("name"))
    res = [{"app": v["app"], "url": v["url"], "primary": v["primary"],
            "sheets": sorted(v["sheets"]), "entities": sorted(v["entities"]),
            "variants": sorted(v["variants"])} for v in out.values()]
    res.sort(key=lambda x: (not x["primary"], x["app"]))   # main apps first
    return res
