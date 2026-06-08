---
name: claims-data-analytics
description: >
  Use whenever someone asks a question about claims data — including when a
  business user UPLOADS an Excel/CSV and asks for a metric, count, total,
  average, rate, trend, or comparison, OR asks where to find something
  ("where can I see nominals?"). Covers our Qlik claims apps (MAR-Operational,
  MAR Conduct, Portfolio Insight, Claim One Stop, Claims Connect Dashboard, CGM Claims
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

## "Where can I see X?" questions — answer ONLY from the data

Resolve X to something real in the skill's data, then point to it:
- If X is a **metric or field**, use `engine.where_to_find` — it returns the app(s)
  **and the exact `Sheet`(s)** (the tab/location) where it lives, grounded in the KPI
  list's `Sheet` column, plus the named variants (e.g. USD / 100% / Ledger).
- If X is identified by a **column/indicator** (e.g. BDX / bordereaux claims →
  the **Bulk Claim Indicator**; nominals → the **Nominal Reserve** code), say which
  column identifies it and list the app(s) that contain it.

Rules:
- **Cite the exact tab.** The `Sheet` value IS the location — name app + sheet(s).
  Cite only sheets present in the data; **never invent** a sheet, tab, app, or metric.
- **Give the link for every app you name, or for none** — never some-but-not-others.
  If a link is still a placeholder, say the link is to be added and name the app.
- **Lead with the answer** — don't open by defining the term unless asked.
- "Which app should I use?" → compare only on the registry's grounded facts
  (purpose, data source, refresh, coverage), e.g. Claim One Stop (daily, latest
  EMEA view) vs MAR - Operational (5 years of financials, weekly / 5th-of-month).

## Targets (Red / Amber / Green)

Some metrics carry owner-set RAG targets (`engine.rag_for`). When it helps, state
the band in plain terms (e.g. "that's within the green target").

## Defaults & terminology

- **Line of business (LOB).** "Line of Business" = "LOB". For a breakdown "by LOB",
  default to **Executive LOB** or **Major LOB**; use **Minor LOB** or **Detailed
  (sub) LOB** only when explicitly asked.
- **App routing (prefer the 5 main apps).** Financials & claim dimensions →
  MAR - Operational or Claim One Stop first. Conduct (TTEP, TTACK, TTC, complaints,
  declined) → MAR Conduct Dashboard. Policy / loss ratios / portfolio → Portfolio
  Insight. CGM-entity → CGM Claims Insight (also MAR - Operational / Claim One Stop).
  Use secondary apps only if no main app has it.
- **Period basis (apps differ — never reconcile across them blindly).**
  MAR - Operational = **accounting period** (monthly, indicator-based; period/trend
  questions). Claim One Stop = **claim reported/opened/closed date** (latest position +
  financial movements as of today; "as of now"). Portfolio Insight = **policy
  underwriting year** (policy / loss-ratio / portfolio).
- **Entities.** Two entities: Company and CGM — split when asked. CGM data → CGM
  Claims Insight (+ MAR - Operational / Claim One Stop). UCR is CGM (CGM Claims
  Insight / Transactional App); `where_to_find` reports the entity per location.

## Hard rules (integrity — these never change)

1. **Never invent — anything.** Not a figure, definition, dashboard, tab, app,
   column, or metric. Use only what's in the skill's data. If it isn't there, say so
   plainly and (for a figure) say what's needed — don't guess. A confident invented
   detail is the worst possible failure for this audience.
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
7. **Be tight.** Lead with the answer; no definitional preamble or filler unless
   asked. SLT-grade means precise and short.

## Not for

- Forecasting or predicting future claims, costs, or outcomes.
- Financial, legal, or investment advice or recommendations.
- Any metric, column, app, dashboard, or tab not in the reference data — say it's
  not in scope; never invent one to be helpful.
- Presenting figures from an uploaded export as reconciled against live Qlik.
- Generic, non-company data questions.

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
  `compute`, `where_to_find`, `where_to_see`, `rag_for`, plus entity derivation
  (`resolve_entity` / `entity_split`). Returns `needs` instead of guessing. Render
  every result for the user with `engine.render(result, label=..., measure=...)` —
  it produces clean text (bold figure, $/% formatting, tables for splits with a Total
  row, a muted audit footnote); never show the raw dict.
- `scripts/resolve_columns.py` — header/metric lookup helper.
- `scripts/mar_operational.py` / `scripts/compute_kpi.py` — exact Qlik formula
  logic, kept as the canonical-definition reference (for maintainers, not for
  business answers).
