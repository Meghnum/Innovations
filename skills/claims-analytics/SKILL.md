---
name: claims-analytics
description: >
  Use whenever someone asks a question about claims data — including when a
  business user UPLOADS an Excel/CSV and asks for a metric, count, total,
  average, rate, trend, or comparison. Covers our Qlik claims apps (A&H Claims
  Connect, CGM Claims Insight, MAR-Operational, MAR-Conduct, Recovery, Fraud,
  TPA Performance, EMEA Explicit Consent, Consumer Line, and related). Trigger
  on any of our metric/field names or on "how many / how much / what is our
  <metric>". Do NOT use for generic, non-company data questions.
---

# Claims Analytics

This skill lets a business user upload a claims spreadsheet and get a PRECISE,
EXPLAINED, CITED answer using OUR definitions. Precision here depends on three
disciplines: (1) never guess a definition or a column, (2) always know which app
the question belongs to, and (3) always show the work. The same word means
different things in different apps, and ~20% of metric definitions are
industry-standard or proprietary placeholders — so an answer is only as good as
the definition it cites.

## The workflow — follow every step

A file is ANY slice of claims with whatever columns the export carries. Never
assume it is filtered by an indicator or any particular field.

1. **Profile the upload** — `scripts/load_and_profile.py` (sheets, columns,
   dtypes, rows). If it's an already-computed KPI table, read the values; don't
   recompute.
2. **Resolve the schema** — `engine.resolve_schema(columns)` maps the real
   headers to canonical concepts via the glossary (claim id, status fields,
   dates, measures, period candidates), whatever the naming.
3. **Establish what the file represents** — its period basis (accounting period,
   reported/opened/closed year, accident year, or claim status) and whether it
   is the full population or already a slice (e.g. only closed claims). Infer
   from the data; if unclear, ASK. Pass this to compute as `slice_is` /
   `period_cols`.
4. **Look up the definition** in `assets/kpi_catalogue.json` and note provenance.
5. **Compute** — `engine.compute(metric, df, schema, slice_is=..., period_cols=...)`.
   It derives closed/open/pending/reopened/declined from whatever columns exist
   (Derived status preferred, else dates), applies the KPI logic, and returns
   `{value, audit}` — or `{needs, reason}` when a required population isn't
   derivable. If it returns `needs`, ASK for that input; never guess.
5b. **For "by each X" / breakdown questions**, use `engine.breakdown(df,
   schema, by=<column>, agg=count|sum|mean|median)`. It groups by whatever
   column the user names and reports the values that exist in the data — it
   does not assume which statuses or categories are present.
6. **Answer in the required format below**, surfacing the audit/derivation.

## Required answer format (non-negotiable)

Every quantitative answer has four parts:

> **Result** — the number, with units and the period/filters it covers.
>
> **How it was generated** — the method in plain words (e.g. "summed the
> `USD Indemnity Paid` and `USD Expense Paid` columns over 1,240 rows"), pulled
> from `audit.method`, `audit.columns_used`, `audit.rows_used`.
>
> **Citations** — the KPI definition used and its provenance tag, the app it
> came from, and the exact uploaded columns + row count it was calculated on.
>
> **Confidence & caveats** — anything from `audit.caveats`: provenance warnings,
> distinct-count notes, currency-scope mixing, unmatched columns, assumptions.

If you cannot produce all four parts, you do not yet have enough to answer —
ask, don't guess.

## Hard rules

1. **Never invent a definition or a field.** Undefined ⇒ ask. Unmatched column
   ⇒ ask. No silent fuzzy guesses past the resolver's confidence threshold.
2. **Establish the app first.** Names like "New Claims", "Incurred", "Declined
   Claims" recur across apps and resolve differently. Confirm context.
2b. **Identify the period basis.** A file is sliced by the user's selection —
   accounting period, reported/opened/closed year, accident year, or claim
   status. The same date columns may all be present; infer the basis or ASK.
   Columns are shared across apps, so column names alone don't identify the app.
2c. **Use Derived status for open/closed/pending.** `Claim Status Derived`
   re-closes 0-reserve open claims; declinature reads the *secondary* status,
   not the primary. See references/column_dictionary.md.
3. **Never mix currency/scope variants** — `USD ...`, `... (100%)`,
   `... (CGM Share)`, `Ledger ...`/original currency are different measures.
4. **Count DISTINCT ClaimID** unless told otherwise (claims can span rows /
   countries). The engine warns when it counted rows instead.
5. **Be honest about provenance.** Always say whether the definition is
   owner-defined, industry-standard, or proprietary-provisional.
6. **Cite, every time.** A number without its audit block is not an answer.

## Files

- `assets/kpi_catalogue.json` — 316 metrics: name, app, definition, provenance,
  computation hint. The machine-readable source the scripts cite from.
- `assets/fields_index.json` — canonical fields for column resolution.
- `assets/status_value_map.json` — status value domains + roll-ups (engine reads).
- `assets/inference_hints.json` — keyword hints for the fallback inference
  (population/measure/life). Edit here, not in code.
- `assets/column_synonyms.json` — concept aliases (engine reads) + candidate
  synonym groups for review.
- `references/kpi_catalogue.md` — human-readable metric catalogue, by app,
  with provenance tags.
- `references/data_dictionary.md` — raw fields by app.
- `references/column_dictionary.md` — master glossary of every column (shared
  across apps), with roles, the period-basis concept, and the status fields.
- `references/reclassified_dimensions.md` — items mislabeled as KPIs that are
  actually dimensions.
- `references/non_metric_items.md` — chart/navigation objects to ignore.
- `references/business_rules.md` — edge cases (distinct counting, 77/88/99/123
  nominal reserves, incurred sign, ratio formulas).
- `references/kpi_gaps.md` — the 6 proprietary metrics still needing owner
  sign-off.
- `scripts/load_and_profile.py` — profile the upload.
- `scripts/engine.py` — the main path: schema resolution, `breakdown` (group-by
  count/sum/mean by any column), and filter-agnostic `compute`. Status is read
  from the actual values in the file (e.g. `Claim Secondary Status`), not derived
  by hardcoded rules; returns `needs` instead of guessing.
- `scripts/resolve_columns.py` — helper for fuzzy header/metric lookup + citations.
- `scripts/mar_operational.py` / `scripts/compute_kpi.py` — the exact Qlik
  formula logic for MAR-Operational, kept as the canonical-definition reference.
