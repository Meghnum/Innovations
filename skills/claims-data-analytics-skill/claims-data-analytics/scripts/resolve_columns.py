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
_FIELDS = json.load(open(os.path.join(_HERE, "..", "assets", "fields_index.json")))
_CATALOGUE = json.load(open(os.path.join(_HERE, "..", "assets", "kpi_catalogue.json")))


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


def find_metric(name: str):
    """Look up a KPI definition (for citation). Returns the catalogue entry or None."""
    nn = _norm(name)
    exact = [m for m in _CATALOGUE if _norm(m["name"]) == nn]
    if exact:
        return exact
    return sorted(_CATALOGUE, key=lambda m: _ratio(nn, _norm(m["name"])),
                  reverse=True)[:3]
