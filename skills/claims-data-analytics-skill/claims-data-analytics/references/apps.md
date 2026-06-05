# Dashboards (apps) — what's where, and the links

This is the reference behind "where can I see X?" answers. Each metric in the
catalogue is tagged with the dashboard that holds it; the machine-readable
registry (with link placeholders) is in `assets/kpi_catalogue.json` under `apps`.

## How to fill in the links

Each app's `url` is currently `PLACEHOLDER — set this dashboard's URL`. Replace it
with the real dashboard link (e.g. the Qlik Sense app URL) in
`assets/kpi_catalogue.json`. Until then, answers should name the dashboard and say
the link is to be added.

## The dashboards

### MAR - Operational
Operational claims KPIs. **What you'll find here:** new / closed / pending /
reopened claims, closing and net-closing and reopened ratios, ACPOC and ACPSC,
nominal reserves and nominal age, incurred and OSLR, age profiles, time-to-settle,
reserve completion, and static / inactive claims.
- Data sources: PCW (Genius), EMIR (Echo), CRS (Exchanging)
- Refresh: PCW updates the following weekend; other sources load on the 5th of each month
- Coverage: 5 years of financial transactions; claim counts are distinct claim numbers in a group
- Each claim is mapped to a business unit (its country) and a product (its line of business)

### MAR Conduct Dashboard
TCF / conduct reporting. **What you'll find here:** complaints, declinatures,
time to acknowledge, time to effect payment (GPI), and time to respond to
correspondence.
- Data sources: Work View and ClaimsConnect (time to respond/pay/acknowledge,
  declined claims); complaints from Respond via the Complaints Dashboard; other
  data from MAR Operational
- Built by the Claims MI team to improve TCF reporting and reduce dependence on IT

### Portfolio Insight
Portfolio and claims trends by country and line of business across EMEA; also the
one-stop for policy data used in staffing models. **What you'll find here:** claim
frequency, claim lag, open / closed claims volume, policy-with-claim, total claims.
- Data source: PCW
- Coverage: policies underwritten 2005 onwards; claims for the most recent six
  years (from 2020)
- Team: EMEA Claims Data & Insight Team (EU.Claims.MI@Chubb.com)

### Claim One Stop
The latest view of claims across the EMEA region.
- Data sources: Company — PCW; CGM — Subscribe
- Refresh: daily
- Each claim is mapped to a business unit (its country) and a product (its line of business)

### Other dashboards
The catalogue also covers A&H Claims Connect, CGM Claims Insight, Recovery, Fraud,
TPA Performance, and others. Their registry entries carry link placeholders and
brief descriptions to be completed by the owning teams.

## A note that applies across apps

When viewing claim-level counts, **each claim is counted once.** When you drill
into the detail you may see the same claim more than once — that happens when a
claim carries several attributes (more than one claimant, coverage type, or injury
code). This is expected and does not change the headline count.

## Owner targets (Red / Amber / Green)

Owner-set RAG targets are stored in `assets/kpi_catalogue.json` under
`rag_thresholds` and surfaced by `engine.rag_for(metric)`. Examples:

| Metric | Red | Amber | Green |
|---|---|---|---|
| ACPOC / ACPSC | > 10% | 5–10% | < 5% |
| Closing Ratio / Net Closing Ratio | < 85% | 85–100% | > 100% |
| New / Closed / Pending Claims | < 10% | 10–15% | > 15% |
| Nominal Reserves | > 15% | 10–15% | < 10% |
| Nominal Age | < 200 | 200–220 | > 220 |
| Reopened Ratio | > 5% | — | < 5% |
| Reserve Completion (0–20 days) | < 80% | 80–85% | ≥ 85% |
| Declinatures | > 2% | 1–2% | ≤ 1% |
| Time to Acknowledge / Time to Effect Payment (GPI) | > 10 days | 6–10 days | ≤ 5 days |
| Time to Respond to Correspondence (% < 5 days) | < 80% | 80–85% | ≥ 85% |
