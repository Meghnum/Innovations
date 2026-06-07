# Column Knowledge Base (master glossary)

Columns are shared across apps — a single de-duplicated glossary, not a per-app list.
`role`: ID / DIM / DATE / MEASURE / $ (money — check currency scope) / FLAG / BAND / META.
**[CONFIRM]** = still needs the owning team; the skill must ask rather than assume.

## Period basis (set by the download selection, not the app)

A file is sliced by what was selected: accounting period (`Month`), claim reported /
opened / closed year, accident year, or claim status. The same date/year columns may
all be present; the skill infers the basis or ASKS — it must not assume.

## Claim status fields — values & layering (authoritative)

Three layers, most to least granular:

- **Claim Secondary Status** — values: `Opened`, `Reopened`, `Closed`,
  `Closed after Reopened`, `Declined`. Roll-up to canonical state: Opened &
  **Reopened -> open**; Closed, **Closed after Reopened** & **Declined -> closed**.
  (Declined is only visible here; it can be counted specifically and also counts
  toward closed.)
- **Claim Status Original** — 2 values `Opened`/`Closed`. A business-friendly
  simplification of secondary (Reopened->Opened, Closed after Reopened->Closed).
- **Claim Status Derived** — `Opened`/`Closed`; sits on top of Original and
  additionally forces open-but-0-reserve claims to Closed. **Preferred for
  open/closed logic.**
- **Genius Claim Status** — many values; NOT used for auto open/closed (needs a
  value->state mapping if relied on).

The machine-readable version the engine uses is `assets/status_value_map.json`.


## Synonyms / aliases

Column synonyms live in `assets/column_synonyms.json`:
- **concept_aliases** — aliases the engine resolves on. Casing/spacing variants
  already match via normalization, so only genuinely different wordings are listed
  (e.g. `claim_id` <- `System Claim Number`).
- **synonym_groups** — 27 reviewed true synonyms for the interpretation layer.
- **known_distinct** — look-alike columns confirmed to be DIFFERENT and never to be
  merged: `Adjuster` vs `Responsible Adjuster` vs `Source Adjuster`;
  `Loss Location` vs `Incident Country`; `UCR_ENERGY` vs `UCR_SUBSCRIBE`.

## Glossary

### Identifiers

| Column | Definition |
|---|---|
| Certificate Number | Insurance certificate identifier under a master policy. |
| Claim Number | Unique claim identifier. |
| Master Policy Number | Master/umbrella policy reference under which sub-policies sit. |
| MN/FN Number | Multinational (MN/FN) number for the policy. |
| Policy Number | Policy number the claim sits under. |
| Policy Reference | Policy reference number. |

### Dimensions / attributes

| Column | Definition |
|---|---|
| Accident Year | Year of accident/loss (a period basis option). |
| Adjuster | Name of the handling adjuster. |
| Adjuster Name | Name of the handling adjuster. |
| Block Indicator | For CGM, identifies the TPA handling the claim. (Source dictionary also lists a Yes/No block indicator in other contexts.) |
| Broker | Broker name. |
| Business Entity | Business entity (e.g. CEGL/CGM). |
| Business Unit Description | Name of the business unit. |
| CAT Code | Catastrophe code (claim grouping). |
| CAT Description | Catastrophe description. |
| Catastrophe | Catastrophe/event grouping the claim belongs to. |
| Cause of Loss | Cause of loss. |
| Claim Closure Reason | Reason the claim was closed. |
| Claim Dac Code | Direct/Assumed/Ceded/Retro-ceded code for the claim. |
| Claim Event Desc | Description of the claim event. |
| Claim Event Description | Description of the claim event. |
| Claim Office | Claim office location handling the claim. |
| Claim Secondary Status | Secondary status on the file, independent of the primary (e.g. secondary = Declined while original = Closed). |
| Claim Source | Source/system the claim came from. |
| Claim Status | Status of the claim. |
| Claim Status Derived | Qlik-adjusted status: a claim open in the source system but holding 0 reserve is forcefully closed in the Qlik load script. Basis for open/closed determination. |
| Claim Status Original | The claim's original (unadjusted) source status. |
| Claim System | Source claims system (Claims Connect / Workview / CGM). |
| Claim Type | Type of claim. |
| Claims Connect Product | Product within Claims Connect. |
| Class 3 Description | 'Class 3' classification description (internal taxonomy). **[CONFIRM]** |
| Cluster | Country cluster (regional grouping). |
| Coinsurance | Coinsurance role (Lead/Follow/Exclusive). |
| Condition Injury Damage | Condition / injury / damage classification of the loss. **[CONFIRM]** |
| Conditional Damage | No standard term 'Conditional Damage' found online; nearest is 'Consequential Damage' (indirect loss following a primary insured event). Likely a variant or internal field. **[CONFIRM]** |
| Contributing Factor | Contributing factor to the loss. **[CONFIRM]** |
| Country | Country (owner-confirmed same as `Policy Country` / `COG_COUNTRY`). |
| Coverage | Coverage on the claim. |
| Currency Code (Ledger) | Original/ledger currency code. |
| Current Global Producer | Current global producer for the account. |
| DAC Code | Direct/Assumed/Ceded/Retro-ceded code (AR1) for the transaction. |
| Declinature Reason | Reason a claim was declined. |
| Detailed LOB | Detailed line of business. |
| Entity | Underwriting/legal entity (e.g. Company / Lloyd's). |
| Event Code | Event/claim group code. |
| Event Description | Description of the claim event. |
| Executive LOB | Executive line of business. |
| File Secondary Status | File-level secondary status, independent of the primary. |
| Genius Claim Status | Claim status as held in the Genius source system. |
| Genius Coverage Code | Coverage code from the Genius system. |
| Genius Coverage Description | Coverage description from the Genius system. |
| Genius Level Indicator | Genius handling level: Fast Track or Level 1/2/3 or other. |
| Global Broker | Global broker name. |
| Industry | Industry/trade of the insured. |
| Industry Explanantion | Industry description (source typo 'Explanantion'). |
| Insured Name | Name of the insured. |
| ledger Currency | Original/ledger currency code. |
| Line Type | Line type classification. **[CONFIRM]** |
| Lloyd's Country of Origin | Lloyd's country of origin for the risk. |
| Location of Loss | Location of the loss. |
| Loss Description | Description of the loss. |
| Loss Location | Country/location of the loss. |
| Major LOB | Major line of business. |
| Minor LOB | Minor line of business. |
| Misc 1 | Miscellaneous field 1 (content varies by programme). **[CONFIRM]** |
| Misc 2 | Miscellaneous field 2 (content varies by programme). **[CONFIRM]** |
| Misc 3 | Miscellaneous field 3 (content varies by programme). **[CONFIRM]** |
| Misc 4 | Miscellaneous field 4 (content varies by programme). **[CONFIRM]** |
| MN Description | Multinational programme description. |
| Month | Accounting-period month the row belongs to (period basis for MAR-Operational). |
| Multinational Account Code | Multinational account code. |
| Name Insured | Name of the insured. |
| Nominal Reserve | Nominal reserve code (77/88/99/123 logic). |
| Plant Division | Plant/division (energy context). **[CONFIRM]** |
| Policy Cluster | Regional cluster by policy. |
| Policy Country | Country (owner-confirmed same as `Country` / `COG_COUNTRY`). |
| Policy Holder Name | Name of the policy holder. |
| Policy Source | System the policy was extracted from. |
| Producer Name | Producer name. |
| Producer/Broker Name | Producer or broker name. |
| Producing Office | Office that produced the business. |
| Producing Office Code | Code for the producing office. |
| Product Code | Product code. |
| Reported To | The adjuster the claim was reported to. |
| Reserving Class | Reserving class / European LOB. |
| Reserving Line | Reserving line (product of the policy). |
| Responsible Adjuster | Name of the responsible adjuster. |
| Risk Category | Customer/business size segment: Small Business / Mid Market / Big / Large. |
| Risk Category Description | Description of the customer/business size segment (Small Business / Mid Market / Big / Large). |
| Secondary Claim Status | Secondary status on the file, independent of the primary (e.g. secondary = Declined while original = Closed). |
| Underwriting Year | Year the policy was underwritten. |

### Dates

| Column | Definition |
|---|---|
| Claim Closed Date | Date the claim was closed. |
| Claim Event Date | Date of the claim event/loss. |
| Claim Opened Date | Date the claim was opened. |
| Claim Report Date | Date the claim was reported. |
| Clam Opened Date | Date the claim was opened (source typo 'Clam'). |
| Closed Date | Date the claim was closed. |
| Declinature Date | Date the claim was declined. |
| Event Date | Date of the claim event/loss. |
| First Declinature | Date the claim was first declined. |
| First Payment | Date of first payment. |
| Last Document Received | Date the last document was received. |
| Last Payment | Date of last payment. |
| Loss Date | Date of loss. |
| Opened Date | Date the claim was opened. |
| Policy Effective Date | Policy inception/effective date. |
| Policy Expiration Date | Policy expiry date. |
| Reload Date | Data reload/refresh date for the record (provisional). **[CONFIRM]** |
| Reopened Date | Date the claim was last reopened. |
| Reported Date | Date the claim was reported. |

### Measures (numeric)

| Column | Definition |
|---|---|
| Claim Life Days | Days the claim has been open (reported/opened to closed or current). |
| Reserve Completion - Business Days | Business days taken to complete the reserve. |

### Financial measures (mind the currency scope)

| Column | Definition |
|---|---|
| CGM Signal Reserve Amount | CGM signal-reserve amount. |
| Chubb Share | The company's share of the risk/claim. |
| Company Signal Reserve Amount | Company signal-reserve amount. |
| Expense Paid Ledger | Expense paid, original currency. |
| Expense Paid USD | Expense paid in USD. |
| Expense Reserve (Ledger) | Expense reserve, original currency. _(aka Expense Reserve Ledger)_ |
| Expense Reserve USD | Expense reserve in USD. |
| Expense Total (Ledger) | Total expense, original currency. |
| Expense Total (USD) | Total expense in USD. |
| Incurred (USD) | Incurred total in USD (Indemnity+Expense+Reserves-Recoveries). Used by ACPSC/ACPOC. _(aka Incurred USD)_ |
| Incurred Ledger | Total incurred, original currency. |
| Incurred Total (Ledger) | Total incurred, original currency. |
| Indemnity (USD) | Indemnity amount in USD. |
| Indemnity Paid Ledger | Indemnity paid, original currency. |
| Indemnity Paid USD | Indemnity paid in USD. |
| Indemnity Total (Ledger) | Total indemnity, original currency. |
| OSLR Total (Ledger) | Outstanding loss reserve total, original currency. |
| OSLR Total (USD) | Outstanding loss reserve total in USD. |
| Outstanding Reserve Ledger | Outstanding reserve, original currency. |
| Outstanding Reserve USD | Outstanding reserve in USD. |
| Recoveries Ledger | Recoveries, original currency. |
| Recoveries USD | Recoveries in USD. |
| USD Expense Paid | Expense paid in USD. |
| USD Expense Reserve | Expense reserve in USD. |
| USD Incurred | Incurred total in USD (Indemnity+Expense+Reserves-Recoveries). |
| USD Indemnity Paid | Indemnity paid in USD. |
| USD Indemnity Reserve | Indemnity reserve in USD. |
| USD Recovery | Recovery amount in USD. |

### Flags / indicators

| Column | Definition |
|---|---|
| Bulk Claim Indicator | Bulk vs Normal claim. BDX / bordereaux claims ARE the bulk claims — use this indicator to identify BDX claims, and report which app(s) contain it. |
| CGM Signal Reserve Flag | CGM signal-reserve flag. |
| Coinsurance Indicator | Coinsurance indicator (Lead/Follow/Exclusive). |
| Company Signal Reserve Flag | Company signal-reserve flag (1900/2700/3700/4700 exposure markers). |
| Fast Track Flag | Whether the claim is fast-track. |
| In Litigation? | Whether the claim is in litigation (Yes/No). |
| Is Litigation? | Whether the claim is in litigation (Yes/No). |
| MAR Fast Track Flag | Whether the claim is a MAR fast-track claim. |
| Multinational | Whether the policy is multinational. |
| Recovery Referral Flag | Whether a recovery referral exists for the claim. |
| Vulnerable Customers | Vulnerable-customer flag. |

### Bandings

| Column | Definition |
|---|---|
| Claim Life Banding | Age banding of the claim, e.g. '1) 0-3 Months'. |
| Incurred Banding (USD) | Banding of incurred amount in USD. |
| Multinational Banding | Whether policy is multinational (banding). |
| Registration Completion Banding 10 days | Whether registration completed within 10 days. |
| Registration Completion Banding 5 days | Whether registration completed within 5 days. |
| Registration Completion Banding SOX | Days between client submission and system registration (SOX banding). |

### Export metadata

| Column | Definition |
|---|---|
| Row | Export row index (no business meaning). _(aka Row #)_ |

## Line of business (LOB) — default level

"Line of Business" = "LOB". For a breakdown "by LOB", default to `Executive LOB` or
`Major LOB`; only use `Minor LOB` or `Detailed LOB` (sub-LOB) when explicitly asked.

## Entity columns (MAR - Operational, MAR - Conduct, Claim One Stop)

| Column | Value | Canonical entity | Note |
|---|---|---|---|
| Entity | Company - Broadview | Company | |
| Entity | Company - Broadview Echo | Company | |
| Entity | Exchanging - LIRMA | CGM | LIRMA |
| Entity | Lloyds 1882 - CRS | CGM | Lloyds |
| Entity | Lloyds 2488 - CRS | CGM | Lloyds |
| Business Entity | CEGL | Company | Company is always CEGL |
| Business Entity | CGM | CGM | |
| Business Entity | CGM CEGL | CGM | LIRMA CGM |
| Business Entity | CGM CUAL | CGM | Lloyds CGM |

Prefer **Business Entity** when present, else **Entity**. Values outside this map are
reported as unmapped (ask, don't guess).
