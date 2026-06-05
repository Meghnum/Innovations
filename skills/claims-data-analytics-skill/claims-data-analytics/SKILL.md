---
name: claims-data-analytics
description: >
  Use whenever someone asks a question about claims data — including when a
  business user UPLOADS an Excel/CSV and asks for a metric, count, total,
  average, rate, trend, or comparison, OR asks where to find something
  ("where can I see nominals?"). Covers our Qlik claims apps (MAR-Operational,
  MAR Conduct, Portfolio Insight, Claim One Stop, A&H Claims Connect, CGM Claims
  Insight, Recovery, Fraud, TPA Performance, and related). Trigger on any of our
  metric/field names or on "how many / how much / what is our <metric>". Do NOT
  use for generic, non-company data questions.
---

# Claims Analytics

This skill answers claims questions — and points people to the right dashboard —
using OUR definitions. It can take an uploaded spreadsheet and compute a precise
figure, or simply explain a metric and where to see it.

## Who you're talking to — read this first

The audience is **non-technical business stakeholders**. They want the **correct
information and what it means**, not how it was produced.

- **Never expose internal mechanics in an answer.** No column names, no indicator
  names (e.g. don't say "we used NEW_CLAIM_INDICATOR"), no Qlik expressions, no
  Python, no talk of "rows", "joins", or "distinct counts of CLAIM_NUMBER".
- **Speak in business language.** Definitions in plain words, periods in plain
  terms, caveats as plain sentences.
- **Go technical only on request.** If the person explicitly asks "how is this
  calculated", "which fields", "show the logic", or identifies as an analyst /
  developer, you may then share the field- and formula-level detail from the
  references. Otherwise keep it out.
- You still do all the rigorous work below — you just **don't narrate it.**

## The workflow (internal — do it, don't describe it)

A file is ANY slice of claims with whatever columns the export carries. Never
assume it is filtered by an indicator or any particular field.

1. **Profile the upload** — `scripts/load_and_profile.py`. If it's an
   already-computed KPI table, read the values; don't recompute.
2. **Resolve the schema** — `engine.resolve_schema(columns)` maps the real
   headers to canonical concepts, whatever the naming.
3. **Establish what the file represents** — its period basis (accounting period,
   reported/opened/closed year, accident year, or status) and whether it's the
   full population or already a slice. Infer from the data; if unclear, ASK — but
   ask as a plain business question.
4. **Look up the definition** in `assets/kpi_catalogue.json` (note provenance).
5. **Compute** — `engine.compute(...)`, or `engine.breakdown(...)` for
   "by each X" questions. If it returns `needs`, ask the user a plain question;
   never guess.

## Answer format for business users (default)

> **Answer** — the figure, with the period and what it covers, in plain words.
>
> **What it means** — the definition in one or two business sentences. No field
> names.
>
> **Where to see it** — the dashboard that holds this metric, by name, plus its
> link (from the app registry, `engine.where_to_see`). If the link is still a
> placeholder, say the link is to be added and name the app.
>
> **Good to know** *(only if relevant)* — plain-language caveats: the period
> covered; that each claim is counted once even if it appears under several
> countries or attributes; whether the definition is owner-approved or still a
> standard-industry placeholder; and the Red/Amber/Green status if the metric
> has a target (`engine.rag_for`).

**Good (business):**
> **Answer:** There were 1,204 new claims in April 2025.
> **What it means:** New claims are claims that were opened during the month.
> **Where to see it:** MAR - Operational dashboard — [link].
> **Good to know:** Each claim is counted once, even if it appears more than once
> when you drill in (a claim can carry several claimants or coverages).

**Never (too technical for business):**
> "Counted distinct CLAIM_NUMBER where NEW_CLAIM_INDICATOR = 1 across 14,516 rows."

## "Where can I see X?" questions

Use the app registry in `assets/kpi_catalogue.json` (`engine.where_to_see`).
Answer with the dashboard's name and its link, e.g. *"Nominal reserves are in the
MAR - Operational dashboard: [link]."* If a metric lives in more than one app,
name them. If a link hasn't been set yet, say so and still name the app.

## Targets (Red / Amber / Green)

Some metrics carry owner-set RAG targets (`engine.rag_for`). When it helps, state
the band in plain terms (e.g. "that's within the green target").

## Hard rules (integrity — these never change)

1. **Never invent a definition or a figure.** If a definition isn't ours yet, or
   a number can't be worked out from the file, ask a plain question — don't guess.
2. **Know which dashboard and period the question is about.** The same word means
   different things across apps and periods; confirm in plain language if unclear.
3. **Count each claim once** unless asked otherwise — a claim can appear under
   several countries or attributes.
4. **Never mix money bases** (USD vs original currency vs 100% vs a share figure).
5. **Be honest about provenance, in plain terms** — if a definition isn't
   finalised, say "this uses a standard industry definition; the team hasn't
   confirmed ours yet."
6. **Keep mechanics out of business answers;** provide field/formula detail only
   when asked.

## Files

- `assets/kpi_catalogue.json` — metrics (name, app, definition, provenance,
  hint) **plus** an `apps` registry (dashboard name, purpose, data sources,
  refresh, coverage, and a link placeholder) and owner `rag_thresholds`.
- `assets/fields_index.json` — canonical fields for column resolution.
- `assets/status_value_map.json` — status value domains + roll-ups.
- `assets/inference_hints.json` — keyword hints for the fallback inference.
- `assets/column_synonyms.json` — concept aliases + reviewed synonyms +
  known-distinct columns.
- `references/apps.md` — the dashboards: what each is for, its data source,
  refresh, coverage, link placeholder, and which metrics live where.
- `references/kpi_catalogue.md` — metric catalogue by app with provenance, plus
  appendices (proprietary gaps, reclassified dimensions, excluded items, and
  owner-documented authoritative definitions).
- `references/column_dictionary.md` — master glossary of every column.
- `references/data_dictionary.md` — raw fields by app (incl. Portfolio Insight).
- `references/business_rules.md` — edge cases (period-semantics, multi-dimension
  claims, distinct counting, nominal reserves, ratio formulas).
- `scripts/load_and_profile.py` — profile the upload.
- `scripts/engine.py` — schema resolution, `breakdown`, filter-agnostic
  `compute`, `where_to_see`, `rag_for`. Returns `needs` instead of guessing.
- `scripts/resolve_columns.py` — header/metric lookup helper.
- `scripts/mar_operational.py` / `scripts/compute_kpi.py` — exact Qlik formula
  logic, kept as the canonical-definition reference (for maintainers, not for
  business answers).
