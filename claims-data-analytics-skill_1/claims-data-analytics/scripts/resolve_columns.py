"""
Step 2 of the upload workflow: map the uploaded file's columns to our canonical
fields, and guess which app/dataset the file most resembles.

Why: a business user's export will have arbitrary headers. Before computing any
KPI we must know which uploaded column means which canonical field — and we must
NOT silently guess. This returns confident matches, ambiguous ones (for the
agent to confirm with the user), and unmatched columns.

Matching is conservative:
  - exact normalized match  -> confident
  - one strong fuzzy match  -> confident
  - several near matches    -> ambiguous (ask the user)
  - nothing close           -> unmatched

Usage:
    from resolve_columns import resolve
    res = resolve(uploaded_columns)   # list[str]
"""
from __future__ import annotations
import json, os, re
from difflib import SequenceMatcher

_HERE = os.path.dirname(__file__)
with open(os.path.join(_HERE, "..", "assets", "fields_index.json")) as _f:
    _FIELDS = json.load(_f)
with open(os.path.join(_HERE, "..", "assets", "kpi_catalogue.json")) as _f:
    _RAW = json.load(_f)
# the catalogue moved from a bare metrics list to {apps, metrics, ...}; accept both
_CATALOGUE = _RAW.get("metrics", []) if isinstance(_RAW, dict) else _RAW


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def resolve(columns, strong: float = 0.92, near: float = 0.80) -> dict:
    confident, ambiguous, unmatched = {}, {}, []
    keys = list(_FIELDS.keys())
    for col in columns:
        nc = _norm(col)
        if nc in _FIELDS:
            f = _FIELDS[nc]
            confident[col] = {"canonical": f["canonical"], "definition": f["definition"],
                              "apps": f["apps"], "match": "exact"}
            continue
        scored = sorted(((_ratio(nc, k), k) for k in keys), reverse=True)[:5]
        top = [(s, k) for s, k in scored if s >= near]
        if top and top[0][0] >= strong and (len(top) == 1 or top[0][0] - top[1][0] > 0.06):
            f = _FIELDS[top[0][1]]
            confident[col] = {"canonical": f["canonical"], "definition": f["definition"],
                              "apps": f["apps"], "match": f"fuzzy({top[0][0]:.2f})"}
        elif top:
            ambiguous[col] = [{"canonical": _FIELDS[k]["canonical"],
                               "score": round(s, 2)} for s, k in top]
        else:
            unmatched.append(col)
    return {"confident": confident, "ambiguous": ambiguous, "unmatched": unmatched,
            "guessed_app": _guess_app(confident)}


def _guess_app(confident: dict):
    """Pick the app whose fields best cover the confidently-matched columns."""
    from collections import Counter
    c = Counter()
    for v in confident.values():
        for app in v["apps"]:
            c[app] += 1
    ranked = c.most_common(3)
    return [{"app": a, "matched_fields": n} for a, n in ranked]


_CAT_NORM = [(_norm(m["name"]), m) for m in _CATALOGUE]


def find_metric(name: str):
    """Look up a KPI definition (for citation): exact-name matches if any,
    else the 3 closest catalogue entries by name similarity."""
    nn = _norm(name)
    exact = [m for n2, m in _CAT_NORM if n2 == nn]
    if exact:
        return exact
    return [m for _, m in sorted(_CAT_NORM, key=lambda t: _ratio(nn, t[0]),
                                 reverse=True)[:3]]
