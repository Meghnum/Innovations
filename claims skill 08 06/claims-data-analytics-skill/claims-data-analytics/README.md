# claims-data-analytics skill

A skill that lets a business user upload a claims spreadsheet (any app, any
format, any slice) and get a precise, plain-language answer using our own KPI and column definitions —
and a pointer to the dashboard where they can see it. Written for non-technical
business users: correct information in business terms, not technical mechanics.

## Layout

```
claims-data-analytics/
  SKILL.md        instructions / workflow / answer format / hard rules
  references/     human-readable knowledge (5 files)
    apps.md                     the dashboards: purpose, data source, refresh, coverage,
                                link placeholders, which metrics live where, RAG targets
    kpi_catalogue.md            metrics + provenance, with appendices incl. owner-documented defs
    column_dictionary.md        master column glossary, period basis, status layering, synonyms
    data_dictionary.md          raw fields by app (incl. Portfolio Insight)
    business_rules.md           period-semantics, multi-dimension claims, currency scope
  assets/         machine-readable config the engine reads (edit here, not in code)
    kpi_catalogue.json          metrics + provenance + hint, plus an app registry
                                (links) and owner RAG thresholds
    fields_index.json           field index for resolution
    status_value_map.json       status value domains + roll-ups (open/closed/declined...)
    column_synonyms.json        concept aliases + reviewed synonyms + known-distinct columns
    inference_hints.json        keyword hints for the fallback inference
  scripts/        the engine
    load_and_profile.py         profile an upload (sheets, columns, dtypes, rows)
    engine.py                   schema resolution + breakdown + filter-agnostic compute
    mar_operational.py          exact Qlik-formula translations (canonical reference)
    resolve_columns.py          header/metric lookup helper
    compute_kpi.py              exact-formula reference path
```

## How it works

1. **Profile** the upload. 2. **Resolve** the real headers to canonical concepts
via the glossary/aliases. 3. **Establish** what the file represents (period basis;
full population vs a slice) — infer or ask. 4. **Look up** the definition + provenance.
5. **Compute** with `engine.py` (counts, ratios, sums, averages, or `breakdown` by
any column). 6. **Answer** with Result / How generated / Citations / Caveats.

Principles: never invent a definition; status & values come from config, not code;
distinct-per-period counts; a claim can span multiple dimensions; return "needs X"
instead of guessing.

## Configuration is data, not code

`status_value_map.json`, `column_synonyms.json`, and `inference_hints.json` are read
by `engine.py` at runtime (with in-code defaults as a safety net). Maintain mappings
there without touching Python.

## Open items

6 proprietary KPIs and ~11 attribute columns still need owner sign-off; value domains
for other categorical columns (bandings/flags/Genius) to be captured; broaden the
explicit metric SPECS; validate computed numbers against the live Qlik dashboard.
