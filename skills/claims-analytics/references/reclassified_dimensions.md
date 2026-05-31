# Reclassified Dimensions

These were labelled as KPIs in the source but are dimensions/attributes, not metrics.
Treat them as breakdown/filter fields, not as numbers to compute.

## A&H Claims Connect Database

- **2 Year Status** — Status banding flagging whether a claim has been open/reopened for 2 years or more. A dimension, not a metric.
- **Actime Claim** — Appears to be a typo for 'Active Claim' — a flag/count of claims currently open/active. Confirm intended spelling and whether count or flag.
- **Certificate Number** — Insurance certificate identifier. A dimension/attribute, not a metric.
- **Claim Country** — Country associated with the claim. A dimension, not a metric.
- **Class 3 Description** — Text description of the internal 'Class 3' classification. A dimension; the classification itself is proprietary.
- **Declinature Reason** — Reason a claim was declined. A dimension, not a metric.
- **Master Policy** — Master policy reference under which sub-policies/certificates sit. A dimension/identifier.

## M7 Pipeline Report Issue Tracker

- **Due Diligence Workflow** — Due-diligence workflow stage/status for a vendor in onboarding. A dimension.
- **Split By Current Position** — A chart split (breakdown) of pipeline items by their current position/stage. A dimension.
- **Split By Onboarding Type** — A chart split of pipeline items by onboarding type. A dimension.
- **Split By Stall Issue** — A chart split of pipeline items by the issue causing them to stall. A dimension.
- **Status** — Status of the tracked item. A dimension, not a metric.
- **Vendor Activity Type** — Type of vendor activity. A dimension, not a metric.
