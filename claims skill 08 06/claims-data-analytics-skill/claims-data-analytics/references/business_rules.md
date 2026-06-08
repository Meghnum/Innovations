# Business Rules & Calculation Conventions

Edge cases that change results. The MAR-Operational section is now derived from
the live Qlik expressions (KPI_List Sheet2) and is verified in code.

## Indicator semantics — indicators are period-stamped (core data model)

In the source model the claim-state indicators are stamped against accounting
periods (MonthYear), NOT against the claim as a whole:

- **NEW_CLAIM_INDICATOR = 1** only in the claim's FIRST accounting period — the
  period in which it was opened (claim opened Jan-2025 -> =1 in 202501 only).
- **REOPENED_CLAIM_INDICATOR** behaves the same way — =1 only in the accounting
  period of the reopen event.
- **CLOSED_CLAIM_INDICATOR = 1** only in the period in which the claim closed.
- **PENDING_CLAIM_INDICATOR = 1** in every accounting period from the claim's
  first period until it is closed — a multi-period *state*, not a single event.

Implications for counting:
- New / Closed / Reopened are single-period *events*, so over a multi-period
  file `sum over MonthYear of distinct CLAIM_NUMBER` equals the unique count of
  those events.
- Pending spans many periods, so the same sum counts a claim once per period it
  is pending — a **period-weighted volume**, not a unique-claim count. Be explicit
  about which is meant: a single DISTINCT count for unique pending claims, the
  per-period sum for the scorecard figure.

## A claim spans multiple dimensions

A single CLAIM_NUMBER can appear across multiple Country / LOB / Major & Minor
LOB / Product / Coverage rows. Therefore:
- Claim counts must use **DISTINCT CLAIM_NUMBER**.
- A breakdown "by country" (or LOB / product / coverage) assigns a claim to
  **each** value it touches, so the sum of a by-dimension breakdown can exceed
  the unique claim count. The answer must say so.

## MAR-Operational data model (from live Qlik)
- **IDs / grain.** Every count/ratio KPI exists at two grains, switched by the
  Qlik variable `vClaimsSources`:
  - `claim` grain → counts `CLAIM_NUMBER` using the `*_CLAIM_INDICATOR` flags.
  - `claimant` grain → counts `CLAIM_CLAIMANT_NUMBER` using the
    `*_CLAIMANT_INDICATOR` flags.
  The agent must know which grain a question wants. Default is `claim`.
- **Distinct-per-period, not global.** `sum(aggr(count(DISTINCT id), MonthYear))`
  counts distinct ids *within each MonthYear* then sums. A claim active across
  two months is counted in both. Some KPIs aggregate over `(MonthYear,
  COG_COUNTRY)` (Pending Claims Count, Reopened Ratio). A naive global distinct
  count is WRONG for these.
- **Indicator flags** are matched as the string value: `INDICATOR = '1'`
  (STATIC uses `'2'`, registration uses `'1'`/`'0'`).

### Indicator columns
`NEW_/CLOSED_/REOPENED_/PENDING_` × `CLAIM`/`CLAIMANT` `_INDICATOR`,
plus `STATIC_CLAIM_INDICATOR` (1-year static = '2'), `NOMINAL_INDICATOR`,
`REGISTRATION_INDICATOR`, `INACTIVE_INDICATOR`.

### Measures / dimensions
`CLAIM_LIFE_DAYS_NUMBER`, `INCURRED_TOTAL_GROSS_USD_AMT`; dims `MonthYear`,
`COG_COUNTRY`, `CLAIM_LIFE_BANDING` (values e.g. `'1) 0-3 Months'`).

### Verified KPI definitions (claim grain shown)
- **Closing Ratio** = Σ_MonthYear distinct(closed) ÷ Σ_MonthYear distinct(new).
- **Net Closing Ratio** = closed ÷ (new + reopened), each Σ_MonthYear distinct.
- **Reopened Ratio** = reopened ÷ closed, each Σ over (MonthYear, COG_COUNTRY).
- **Total New / Closed Claims** = Σ_MonthYear distinct with that indicator.
- **Pending Claims Count** = Σ over (MonthYear, COG_COUNTRY) distinct, PENDING=1.
- **Volume - 1 Year Static** = distinct claims, PENDING=1 & STATIC=2 (global).
- **Time to Settle / Average Time to Settle** (identical formulas) =
  mean over (MonthYear, claim) of claim life days, CLOSED=1.
- **ACPSC / ACPOC** = mean `INCURRED_TOTAL_GROSS_USD_AMT` over CLOSED / PENDING
  rows (row-level average).
- **Age Profile** buckets = distinct PENDING claims in the named life bandings.
- **Nominal Reserves** = distinct claims, NOMINAL=1. **Nominal Age** = mean over
  MonthYear of mean life days, NOMINAL=1.
- **Reserve Completion (0-30)** = registered-new ÷ (registered-new +
  unregistered-new), distinct claims.
- **Inactive Claims (>270 Days)** = distinct PENDING & INACTIVE claims.

## Currency / scope variants — never mix
`USD ...`, `... (100%)`, `... (CGM Share)`, `Ledger ...`/original currency are
different measures. Never add or compare across them without converting.

## Nominal reserve codes (reference)
77 = no exposure expected; 88 = open for recoveries; 99 = new, uncertain, high
value; 123 = new, uncertain. `NOMINAL_INDICATOR=1` flags a nominal-reserve claim.

## Known data-quality notes
Source names/definitions contain typos (e.g. "Acieved", "Avarage"). Treat the
catalogue's canonical name as authoritative; flag placeholders.

## TODO with owning teams
- [ ] Confirm default grain for ambiguous questions (claim vs claimant).
- [ ] Validate computed numbers against the live Qlik dashboard.
- [ ] Fill the 6 remaining proprietary definitions (references/kpi_gaps.md).

## EMEA Unreserved Report (SOX control)

A SOX control replacing the old Unregistered Claims and Incomplete Claims controls,
operated like the Nominals control: owners use the MI to manage reserving in their
area; only a monthly attestation that the control is operating is required. Listed
claims are open in Workview or Claims Connect with **either** no associated Genius
file (*unregistered*) **or** a Genius file showing a zero indemnity reserve and
active file status (*unreserved*). Claims under 30 days old from reported date, or
with the reserve-not-required flag ticked in either source system, are considered
**managed** and excluded.

## Finding BDX / bordereaux (bulk) claims

BDX / bordereaux claims are the **bulk** claims, identified by the **Bulk Claim
Indicator** column (Bulk vs Normal). To answer "where can I find BDX claims",
name the Bulk Claim Indicator and list the app(s) that carry it — do not invent a
"BDX dashboard". Block Indicator (CGM) identifies the TPA, not BDX — keep them
separate.

## Line of business (LOB)

"Line of Business" and "LOB" mean the same thing. The LOB hierarchy, broad to
granular, is: **Executive LOB → Major LOB → Minor LOB → Detailed LOB (sub-LOB)**.

**Default:** when asked for analysis "by line of business" or "by LOB", break down
by **Executive LOB** or **Major LOB** (the executive/major level). Use **Minor LOB**
or **Detailed (sub) LOB** only when the user explicitly asks for that finer
granularity.

## App routing & priority

Five main apps carry most data — prefer them; fall back to secondary apps (Claims
Connect, Recovery, Fraud, TPA, Transactional, etc.) only if a main app lacks it.
- **Financials and claim dimensions** → check **MAR - Operational** or **Claim One
  Stop** first.
- **Conduct** — Time to Effect Payment (TTEP), Time to Acknowledge (TTACK), Time to
  Correspondence (TTC), complaints, declined → **MAR Conduct Dashboard**.
- **Policy, loss ratios, portfolio performance** — anything policy-related →
  **Portfolio Insight**.
- **CGM-entity claims** → **CGM Claims Insight** (CGM only); CGM data also sits in
  **MAR - Operational** and **Claim One Stop**.

## Period basis by app (MAR - Operational vs Claim One Stop vs Portfolio Insight)

Each app is built on a different time dimension, so the **same KPI for "the same
period" will legitimately differ across apps** — never reconcile one against another
without accounting for this:
- **MAR - Operational** — **accounting period**. All financials and claims are on an
  accounting-period basis; monthly, indicator-based (NEW / CLOSED / REOPENED /
  PENDING). Use for period and trend questions.
- **Claim One Stop** — **claim reported / opened / closed date**. The latest position
  of every claim and total financial movements as of today (point-in-time). Use for
  "as of now" questions; slice by claim dates, not accounting period.
- **Portfolio Insight** — **policy underwriting year**. Policy, loss-ratio and
  portfolio questions are on an underwriting-year basis.

## Entities — Company vs CGM

Two business entities: **Company** and **CGM** (some data is shared = "Company and
CGM"; vendor/TPA data is separate). When the business asks for Company and CGM
separately, split by entity. CGM data lives in **CGM Claims Insight (CGM only)** and
also in **MAR - Operational** and **Claim One Stop**. **UCR** references (UCR,
UCR_SUBSCRIBE, UCR_ENERGY) are **CGM**, found in CGM Claims Insight and the
Transactional App; UCR_SUBSCRIBE and UCR_ENERGY are distinct (never merge).

**Row-level derivation (MAR - Operational, MAR - Conduct, Claim One Stop exports).**
These exports carry two columns that identify the entity; prefer **Business Entity**
when present, else **Entity**:
- **Entity** — `Company - Broadview`, `Company - Broadview Echo` → **Company**;
  `Exchanging - LIRMA`, `Lloyds 1882 - CRS`, `Lloyds 2488 - CRS` → **CGM**.
- **Business Entity** — `CEGL` → **Company** (Company is always CEGL);
  `CGM`, `CGM CEGL` (LIRMA CGM), `CGM CUAL` (Lloyds CGM) → **CGM**.

So CGM splits further into LIRMA CGM (`CGM CEGL` / `Exchanging - LIRMA`) and Lloyds CGM
(`CGM CUAL` / the Lloyds CRS values). To split a file Company vs CGM, derive the entity
per row from these columns. Any value not in this map is reported as unmapped — ask,
don't guess. (`engine.resolve_entity` / `entity_split` implement this.)
