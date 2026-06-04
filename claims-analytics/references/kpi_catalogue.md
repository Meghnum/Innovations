# KPI Catalogue

Computed metrics by Qlik app. Each definition is tagged with its provenance:
OWNER-DEFINED (authoritative), INDUSTRY-STANDARD (safe default, confirm thresholds),
or PROPRIETARY (provisional — confirm with the owning team before relying on it).
Dimensions, chart objects and navigation labels have been moved out — see other files.

## A&H Claims Connect Database

- **% CSP Achieved - Basic Book/Direct Marketing/NAC**  `[PROPRIETARY (confirm with owner)]` — Percentage of claims in the Basic Book / Direct Marketing / NAC books that were handled via the CSP (Claims Service Provider) route. CSP, NAC and the book segments are internal definitions — confirm exact numerator/denominator with the A&H team.
- **% Fast Track Acieved**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Percentage of claims handled through the fast-track (simplified, low-touch) route in the period = Fast Track Claims / total eligible claims x 100. (Source name misspelled 'Acieved'.)
- **% Fast Track Target**  `[INDUSTRY-STANDARD (confirm thresholds)]` — The target/benchmark percentage of claims that should be handled via fast track in the period.
- **% Fast Track Throughput**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Percentage of fast-track claims completed (closed) relative to fast-track claims entering the route in the period.
- **Acceptance Rate**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Percentage of decided claims that were accepted (not declined or walked away) = accepted claims / total decided claims x 100.
- **Avarage Paid**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Average amount paid per claim = total paid (indemnity + expense) / number of paid claims. (Source name misspelled 'Avarage'.)
- **Average Cycle Time**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Average elapsed days from claim reported (or opened) to closed, across claims closed in the period.
- **CSP Ingested Claims - Basic Book/Direct Marketing/NAC**  `[PROPRIETARY (confirm with owner)]` — Count of claims in the Basic Book / Direct Marketing / NAC books ingested via the CSP route. Proprietary segmentation — confirm with the A&H team.
- **Claim Office Country**  `[OWNER-DEFINED]` — Country name of claim office
- **Claims**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Count of claims meeting the selected criteria. Confirm whether this counts DISTINCT ClaimID (see business_rules.md).
- **Class 3 Check**  `[PROPRIETARY (confirm with owner)]` — An internal conduct-risk check tied to the 'Class 3' classification. Proprietary — confirm definition with the Conduct Risk team.
- **Closed Claims**  `[OWNER-DEFINED]` — Total number of closed calims based on given criteria
- **Closed No Payment**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Count of claims closed without any indemnity payment (closed at nil / no-pay).
- **Declinature Rate**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Percentage of decided (or new) claims that were declined = declined claims / total decided claims x 100.
- **Declined Claims**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Total number of claims declined in the period.  _(name reused across apps — confirm context)_
- **Declined Claims**  `[OWNER-DEFINED]` — Total number of claims declined  _(name reused across apps — confirm context)_
- **Fast Track Claims**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Count of claims handled via the fast-track route in the period.
- **Median Cycle Time**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Median elapsed days from reported (or opened) to closed across closed claims; less sensitive to outliers than the average.
- **New Claims**  `[OWNER-DEFINED]` — Total number of new claims based on criteria  _(name reused across apps — confirm context)_
- **Policy Number**  `[OWNER-DEFINED]` — Policy number  _(name reused across apps — confirm context)_
- **Policy Ref**  `[OWNER-DEFINED]` — Policy reference number
- **Total Claim - Basic Book/Direct Marketing/NAC**  `[PROPRIETARY (confirm with owner)]` — Total claim count across the Basic Book / Direct Marketing / NAC books. Proprietary segmentation — confirm with the A&H team.
- **Total Closed Claims**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Total number of claims closed in the period.
- **Total Declined**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Total number of claims declined in the period.
- **Total Fast Track Claims**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Total number of claims handled via the fast-track route in the period.
- **Total Opened**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Total number of claims opened in the period.

## CGM Claims Insight

- **$ Claims Incurred**  `[OWNER-DEFINED]` — Total claim amount for selected filters in USD
- **$ Expense & Fees Paid (CGM Share)**  `[OWNER-DEFINED]` — Total expense and fees paid for selected filters in USD
- **$ Expense & Fees Reserve (CGM Share)**  `[OWNER-DEFINED]` — Total expense and fees reserve for selected filters in USD
- **$ Indemnity Paid (CGM Share)**  `[OWNER-DEFINED]` — Total indemnity paid for selected filters in USD
- **$ Indemnity Reserve (CGM Share)**  `[OWNER-DEFINED]` — Total indemnity reserve for selected filters in USD
- **Account for Renewal**  `[OWNER-DEFINED]` — Total number of accounts for renewal
- **Account value (CGM Share)**  `[OWNER-DEFINED]` — Total account value in USD (CGM only)
- **Claim Count**  `[OWNER-DEFINED]` — Total claims count
- **Claims Count**  `[OWNER-DEFINED]` — Total claims Count
- **Claims Incurred**  `[OWNER-DEFINED]` — Total claims incurred
- **Closed - Fees Only**  `[OWNER-DEFINED]` — Count and percentage of close claims with fees only
- **Closed - Indemnity Settlement**  `[OWNER-DEFINED]` — Count and percentage of closed claims with indemnity settlement
- **Closed - No Indemnity & Fees**  `[OWNER-DEFINED]` — Count and percentage of claim with no indemnity amount or fees
- **Closed Claim Count**  `[OWNER-DEFINED]` — Count on total closed claims based on selected criteria  _(name reused across apps — confirm context)_
- **Closed Claims Count**  `[OWNER-DEFINED]` — Total number of closed claims
- **Closed Claims Lifecycle (Days)**  `[OWNER-DEFINED]` — Difference in number of working days between reported date and closed claims latest movement days
- **Expense and Fees Paid (CGM Share)**  `[OWNER-DEFINED]` — Total expense and other fees paid (CGM share only)
- **Expense and Fees Reserve (CGM Share)**  `[OWNER-DEFINED]` — Total expense and fees reserve (CGM only)
- **First Time Renewal**  `[OWNER-DEFINED]` — Total first time renewal amount in USD
- **GROSS WRITTEN PREMIUM**  `[OWNER-DEFINED]` — Gross written premium
- **Incurred for Closed Claims (CGM Share)**  `[OWNER-DEFINED]` — Total incurred amount for closed claim in USD (CGM only)
- **Incurred for Open Claims (CGM Share)**  `[OWNER-DEFINED]` — Total incurred amount for open claims
- **Indemnity Paid (CGM Share)**  `[OWNER-DEFINED]` — Total Indemnity paid (For CGM only)
- **Indemnity Paid for Open Claims (CGM Share)**  `[OWNER-DEFINED]` — Total indemnity paid for open claims (CGM only)
- **Indemnity Reserve (CGM Share)**  `[OWNER-DEFINED]` — Total Indemnity reserve (CGM only)
- **Long Standing Account**  `[OWNER-DEFINED]` — Total long standing amount in USD
- **MAJOR LINE**  `[OWNER-DEFINED]` — Major Line of Business name
- **MINOR LINE**  `[OWNER-DEFINED]` — Minor Line Of Business name
- **NET WRITTEN PREMIUM**  `[OWNER-DEFINED]` — Net written premium
- **O/S Reserve**  `[OWNER-DEFINED]` — Total outstanding reserve
- **Open**  `[OWNER-DEFINED]` — Count and percentage of  open claims
- **Open - Declined**  `[OWNER-DEFINED]` — Count and percentage of declined claims
- **Open Claims Count**  `[OWNER-DEFINED]` — Total number of open claims
- **Open Claims Lifecycle (Days)**  `[OWNER-DEFINED]` — Difference in number of working days between reported date and open claims latest movement days
- **Outstanding Reserve for Open Claims (CGM Share)**  `[OWNER-DEFINED]` — Total outstanding loss reserve for CGM only
- **POLICY ACCOUNT COUNT**  `[OWNER-DEFINED]` — Total number of policy count by major and minor LOB

## CGM Claims Performance_UAT_Final

- **Count of UCRs received monthly**  `[OWNER-DEFINED]` — Count of UCRs received monthly refers to the total number of Unreported Claims Reserves (UCRs) that are recorded or acknowledged by the insurance company within a given month.
UCRs are estimates of the reserves set aside by an insurance company for claims that have occurred but have not yet been reported by policyholders.
- **Data Completeness**  `[OWNER-DEFINED]` — Data completeness refers to the extent to which all required data is present and accounted for in financial reports and MI systems. It ensures that no critical data is missing, which is essential for accurate analysis, decision-making, and regulatory compliance.
Why -This sheet has been created to provide a comprehensive view of all vendors, detailing the financials and management information (MI) of both closed and open claims, along with the monthly count of UCRs.
- **Incurred indemnity Vs Incurred fees**  `[OWNER-DEFINED]` — Incurred indemnity and incurred fees are terms used to describe different types of costs associated with insurance claims.
Incurred indemnity refers to the total amount of money that an insurance company expects to pay out to policyholders for covered losses.
Incurred fees refer to the expenses that an insurance company incurs in the process of handling and settling claims.
- **Open Vs Closed Claims**  `[OWNER-DEFINED]` — It refer to the status of an insurance claim during the claims process. 
An open claim is one that has been reported to the insurance company but has not yet been fully resolved or settled. A closed claim is one that has been fully resolved and settled by the insurance company
- **Referrals**  `[OWNER-DEFINED]` — It refer to the process where an insurance agent or broker recommends a potential client to an insurance company or another agent. Referrals can also occur within the claims process when a claim is referred to a specialist or another department for further handling.  _(name reused across apps — confirm context)_

## Cladding Report Company

- **Accident Year**  `[OWNER-DEFINED]` — Year of accident
- **Adjuster Name**  `[OWNER-DEFINED]` — Name of the adjuster for the claim
- **Broker**  `[OWNER-DEFINED]` — Name of broker of the policy associated to the claim
- **Claim CAT Code**  `[OWNER-DEFINED]` — Not available
- **Claim Closed Date**  `[OWNER-DEFINED]` — Date when claim closed
- **Claim Event Date**  `[OWNER-DEFINED]` — Not available
- **Claim Number**  `[OWNER-DEFINED]` — Claim number  _(name reused across apps — confirm context)_
- **Claim Opened Date**  `[OWNER-DEFINED]` — Date when claim opened
- **Claim Status**  `[OWNER-DEFINED]` — Status of the claim
- **Claim Type Code**  `[OWNER-DEFINED]` — Not available
- **Coinsurance Indicator**  `[OWNER-DEFINED]` — Exclusive/Lead/Follow
- **Expense Paid (USD)**  `[OWNER-DEFINED]` — Expense paid in USD
- **Expense Reserved (USD)**  `[OWNER-DEFINED]` — The total reserve for every claim that is open, reopened or closed in the maximum selected accounting period - in USD
- **Incurred (USD)**  `[OWNER-DEFINED]` — Total Incurred in USD
- **Indemnity Paid (USD)**  `[OWNER-DEFINED]` — Indemnity paid in USD
- **Indemnity Reserved (USD)**  `[OWNER-DEFINED]` — Indemnity reserve in USD
- **Insured Name**  `[OWNER-DEFINED]` — Name of insured person / entity  _(name reused across apps — confirm context)_
- **Policy Number**  `[OWNER-DEFINED]` — Policy number  _(name reused across apps — confirm context)_
- **Primary / Excess**  `[OWNER-DEFINED]` — Not available
- **Recovery (USD)**  `[OWNER-DEFINED]` — Recovery in USD
- **Reported Date**  `[OWNER-DEFINED]` — Claim reported date
- **Responsible Adjuster Code**  `[OWNER-DEFINED]` — Adjuster code handling the claim
- **Underwriting Year**  `[OWNER-DEFINED]` — Year of policy underwriting

## Claims Assistance Provider Scorecard

- **Average Abandonment Time**  `[OWNER-DEFINED]` — Average Time to Abandon in HH MM SS
- **Average Case Cost**  `[OWNER-DEFINED]` — Total Invoice Value paid over Total Operationally Closed Cases
- **Average Speed of Answer**  `[OWNER-DEFINED]` — Average Speed of Answer in HH MM SS
- **Calls Abandoned**  `[OWNER-DEFINED]` — Total Calls Offered minus Total Calls Answered
- **Calls Abandoned Rate %**  `[OWNER-DEFINED]` — Number of abandoned over the Total Calls Offered
- **Calls Answered**  `[OWNER-DEFINED]` — Total Calls Answered
- **Calls Answered Rate %**  `[OWNER-DEFINED]` — Total Calls Answered over Total Calls Offered
- **Calls Offered**  `[OWNER-DEFINED]` — Total Calls Offered
- **Declined Cases**  `[OWNER-DEFINED]` — Cases Declined
- **Declined to New Cases**  `[OWNER-DEFINED]` — Declined Cases against New Cases Received
- **EUR Net Savings Current'**  `[OWNER-DEFINED]` — Net Savings Value for EUR for reporting Month
- **New Cases**  `[OWNER-DEFINED]` — New Assistance Cases Received
- **Number of Checked Cases**  `[OWNER-DEFINED]` — Number of checked cases
- **Outcome-Passed**  `[OWNER-DEFINED]` — Outcome minus Passed
- **Quality Checked %**  `[OWNER-DEFINED]` — Number of checked cases over New Assistance Cases Received
- **ROW Net Savings Current'**  `[OWNER-DEFINED]` — Net Savings Value for ROW for reporting Month
- **Total EUR Net Savings**  `[OWNER-DEFINED]` — Total Net Savings Value for EUR
- **Total Invoice Value**  `[OWNER-DEFINED]` — Total Invoice Value paid in €
- **Total Net Savings**  `[OWNER-DEFINED]` — Total Net Savings
- **Total Net Savings Current'**  `[OWNER-DEFINED]` — Total Net Savings Value for reporting Month
- **Total Opened Cases**  `[OWNER-DEFINED]` — Opened Cases in a Period
- **Total Operationally Closed**  `[OWNER-DEFINED]` — Total Operationally Closed
- **Total ROW Net Savings**  `[OWNER-DEFINED]` — Total Net Savings Value for ROW
- **Total USA Net Savings**  `[OWNER-DEFINED]` — Total Net Savings Value for USA
- **USA Net Savings Current'**  `[OWNER-DEFINED]` — Net Savings Value for USA for reporting Month

## EMEA Explicit Consent

- **Count of Not Yet Determined Claims**  `[OWNER-DEFINED]` — Count of Not Yet Determined Claims by Policy Country and Month Year
- **Count of Not Yet Determined Claims by Claim Type and Month Year**  `[OWNER-DEFINED]` — Count of Not Yet Determined Claims by Claim Type and Month Year

## Fraud Dashbord

- **% Suspected of Fraud**  `[OWNER-DEFINED]` — Percentage of suspected fraud
- **Accepted for Investigation %**  `[OWNER-DEFINED]` — Percentage of suspected fraud accepted for investigation
- **Closed No Impact**  `[OWNER-DEFINED]` — Closed without any saving
- **Closed with Impact**  `[OWNER-DEFINED]` — Indicator to show Fraud claim records which are are closed and have a Savings assigned.
- **Count of Claim Number**  `[OWNER-DEFINED]` — Total number of claims
- **Country**  `[OWNER-DEFINED]` — Country Name  _(name reused across apps — confirm context)_
- **Fraud Expense (USD)**  `[OWNER-DEFINED]` — Fraud claim related expenses in USD
- **Impact Rate**  `[OWNER-DEFINED]` — Close with Impact to Closed without impact ratio
- **Major LOB**  `[OWNER-DEFINED]` — Major LOB name  _(name reused across apps — confirm context)_
- **Net Saving (USD)**  `[OWNER-DEFINED]` — Saving minus Expenses in USD
- **New Claims Count**  `[OWNER-DEFINED]` — Count of new claim within selected period  _(name reused across apps — confirm context)_
- **Primary Referral Source**  `[OWNER-DEFINED]` — Category or Type of Primary Fraud threat Referral Source: Adjuster or third party etc
- **Region**  `[OWNER-DEFINED]` — Region as UKISA or CE or MENA
- **Saving (USD)**  `[OWNER-DEFINED]` — Fraud claim savings in USD
- **Saving Banding USD**  `[OWNER-DEFINED]` — Banding to group savings
- **Suspected Fraud**  `[OWNER-DEFINED]` — Count of suspected fraud
- **Total Closed**  `[OWNER-DEFINED]` — Total number of fraud cases closed
- **Total Gross Reserved**  `[OWNER-DEFINED]` — Total gross reserved based on selected criteria
- **Year Closed**  `[OWNER-DEFINED]` — Year the fraud closed

## M7 Pipeline Report Issue Tracker

- **Count**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Generic count of records meeting the selected criteria.

## MAR-Conduct

- **% 5 Days and Under**  `[OWNER-DEFINED]` — Percentage of claims where time to acknowledge loss within 5 days
- **% Time to Effect Payment**  `[OWNER-DEFINED]` — % Time to Effect Payment  difference between recieved date and payment date
- **5 Days and Under**  `[OWNER-DEFINED]` — Number of cases where all queries processed and responded to within 5 days of SLA standard
- **5 Days and Under**  `[OWNER-DEFINED]` — Number of cases where all payment payments processed within 5 working days of SLA standard
- **5 Days and Under**  `[OWNER-DEFINED]` — Number of cases claims acknowledged within 5 days of SLA standard
- **Average Time to Acknowledge**  `[OWNER-DEFINED]` — Average days it took to acknowledge claim from reported date
- **Avg Working Days**  `[OWNER-DEFINED]` — Average days to respond to the correspondence
- **Complaints Received**  `[OWNER-DEFINED]` — Total number of complaint received based on criteria
- **Complaints to New Claims %**  `[OWNER-DEFINED]` — Percentage of complaints with resepct to new claim
- **Declined Claims**  `[OWNER-DEFINED]` — Total number of claims declined  _(name reused across apps — confirm context)_
- **Declined Claims to New Claims %**  `[OWNER-DEFINED]` — Percentage of declined claims vs new claim
- **New Claims**  `[OWNER-DEFINED]` — Total number of new claims based on criteria  _(name reused across apps — confirm context)_
- **Over 5 Days**  `[OWNER-DEFINED]` — Number of cases responded over 5 days
- **Time to Effect Payment**  `[OWNER-DEFINED]` — Average days it took to complete payment from received date i.e. time to get payment processed
- **Time to Respond to Correspondence**  `[OWNER-DEFINED]` — Percentage of claims where time to respond to correspondence below 5 days  based on Workview arrival date

## MAR-Operational

- **ACPOC**  `[OWNER-DEFINED]` — The incurred value of all open or reopened claims divided by the count of those claims selected
- **ACPSC**  `[OWNER-DEFINED]` — The incurred value of all closed claims divided by the count of those claims selected
- **Age Profile - 12 - 24 Months**  `[OWNER-DEFINED]` — Count of claims where the age of the closed/Open & Reopen claim is between 12 months old and 24 months old
- **Age Profile - 24 Months <**  `[OWNER-DEFINED]` — Count of claims where the age of the closed/Open & Reopen claim is less than 6 months old
- **Age Profile - 6 - 12 Months**  `[OWNER-DEFINED]` — Count of claims where the age of the closed/Open & Reopen claim is between 6 months old and 12 months old
- **Age Profile - Under 6 Months Old**  `[OWNER-DEFINED]` — Count of claims where the age of closed/Open & Reopen claim is less than 6 months old
- **Average Time to Settle**  `[OWNER-DEFINED]` — Average number of days to settle claim
- **Closed Claim Count**  `[OWNER-DEFINED]` — Count on total closed claims based on selected criteria  _(name reused across apps — confirm context)_
- **Closed Claims 12 Month Rolling Avarage**  `[OWNER-DEFINED]` — Average closed claims in last 12 months based on selected criteria
- **Closed No Payment Claim Count**  `[OWNER-DEFINED]` — Count of claims closed without any payment  based on selected criteria
- **Closed Volumes**  `[OWNER-DEFINED]` — Number of closed claims for selected criteria
- **Closing Ratio**  `[OWNER-DEFINED]` — Claims/Claimants that have been closed in the accounting period divided by the Claims/Claimants that have been opened in the accounting period
- **Expense Paid in Period - USD**  `[OWNER-DEFINED]` — Total expense amount paid in the selected period in USD
- **Expense to Indemnity Ratio**  `[OWNER-DEFINED]` — Ratio of indemnity by expense paid
- **Inactive Claims (>270 Days)**  `[OWNER-DEFINED]` — Number of claims inactive for more tha 270 days
- **Incurred Movement Paid in Period - USD**  `[OWNER-DEFINED]` — Incurred Movement in Period - USD check with elise
- **Incurred Movement in Period - USD**  `[OWNER-DEFINED]` — OSLR Movement in Period - USD  check with elise
- **Indemnity Paid in Period - USD**  `[OWNER-DEFINED]` — Total indemnity amount paid in the selected period in USD
- **Net Closing Ratio**  `[OWNER-DEFINED]` — Claims/Claimants that have been closed in the accounting period divided by the Claims/Claimants that have been opened and reopened in the accounting period
- **New Claim Count**  `[OWNER-DEFINED]` — Count of total new claims based on selected criteria
- **New Claims 12 Month Rolling Avarage**  `[OWNER-DEFINED]` — Average new claims in last 12 months based on selected criteria
- **New Volumes**  `[OWNER-DEFINED]` — Number of new claims for selected criteria
- **New claim reserve uncertain**  `[OWNER-DEFINED]` — Claim with a nominal reserve of 123
- **New claim reserve uncertain - high value**  `[OWNER-DEFINED]` — Claim with a nominal reserve of 99
- **No financial exposure expected to Chubb**  `[OWNER-DEFINED]` — Claim with a nominal reserve of 77
- **Nominal Age**  `[OWNER-DEFINED]` — The average of age of Claims/Claimants that hold a nominal reserve in the time period selected
- **Nominal Reserve**  `[OWNER-DEFINED]` — The sum of reserves on any claim with cumulative gross (DACs 1&2), Original Currency reserve fitting logic outlined: Reserves = 77, 88, 99 or 123. Built into Broadview for 77 and 123. 88 and 99 is calculated in Qlik Sense
- **OSLR Movement Paid in Period - USD**  `[OWNER-DEFINED]` — Total outstanding loss reserve paid in the selected period in USD
- **OSLR Movement in Period - USD**  `[OWNER-DEFINED]` — Total outstanding loss reserve paid in the selected period in USD
- **Open for Recoiveries**  `[OWNER-DEFINED]` — Number of open claims with recoveries expected // Number of claim with nominal value of 88
- **Pending Claim Count**  `[OWNER-DEFINED]` — Total pending claim count
- **Pending Claims**  `[OWNER-DEFINED]` — Number of pending claims for selected criteria
- **Reopened Claims Count**  `[OWNER-DEFINED]` — Count of reopened claims based on selected criteria
- **Reopened Ratio**  `[OWNER-DEFINED]` — Claims/Claimants that have been reopened in the accounting period divided by the Claims/Claimants that have been closed in the accounting period
- **Reserve Completion (0-30 Calendar Days)**  `[OWNER-DEFINED]` — Percentage of cases reserve completed within 30 days
- **Reserve ending in 001 for Local Regulatory Reason**  `[PROPRIETARY (confirm with owner)]` — Claims whose reserve amount ends in '001', used as an internal marker for a local regulatory reason. Proprietary convention — confirm with the reserving team.
- **Time to Settle**  `[OWNER-DEFINED]` — Total time taken to settle claim
- **Total New Claims**  `[OWNER-DEFINED]` — Total new claims based on selected criteria
- **Total Reopened Claims**  `[OWNER-DEFINED]` — Total number of reopened claims
- **Total Reopened Ratio**  `[OWNER-DEFINED]` — Ratio of reopened claims
- **Value - 1 Year Static Claims**  `[OWNER-DEFINED]` — Incurred total of Claims that are opened or reopened in the accounting period where there has been no financial movement for 365 days
- **Volume - 1 Year Static Claims**  `[OWNER-DEFINED]` — Claims that are opened or reopened in the accounting period where there has been no financial movement for 365 days

## Recovery Dashboard

- **Adjuster**  `[OWNER-DEFINED]` — Adjuster name
- **COG Country**  `[OWNER-DEFINED]` — COG Country name
- **Claim Handler**  `[OWNER-DEFINED]` — Claims handler name
- **Claim Number**  `[OWNER-DEFINED]` — Claim number  _(name reused across apps — confirm context)_
- **Cluster**  `[OWNER-DEFINED]` — Country cluster
- **Country**  `[OWNER-DEFINED]` — Country Name  _(name reused across apps — confirm context)_
- **Est. Pipeline USD**  `[OWNER-DEFINED]` — This KPI header would be updated as Pending Recovery Est USD in new model. This shows the Pending aggregated Recovery Amounts in Pipeline.
- **Est. Recovery Pipeline USD**  `[OWNER-DEFINED]` — Estimated recovery pipeline by year in USD
- **Gross Paid**  `[OWNER-DEFINED]` — Total amount paid for selected criteria in USD
- **Gross Recoveries**  `[OWNER-DEFINED]` — Total recoveries based on the selected crietria (filter)
- **Gross Recoveries**  `[OWNER-DEFINED]` — Total recoveries for the selected quarter
- **Gross paid**  `[OWNER-DEFINED]` — Total amount paid for selected criteria in USD
- **Insured Name**  `[OWNER-DEFINED]` — name of the insured person  _(name reused across apps — confirm context)_
- **Major LOB**  `[OWNER-DEFINED]` — Major LOB name  _(name reused across apps — confirm context)_
- **Minor LOB**  `[OWNER-DEFINED]` — Minor LOB name
- **New Claims Count**  `[OWNER-DEFINED]` — Count of new claim within selected period  _(name reused across apps — confirm context)_
- **Paids Ratio**  `[OWNER-DEFINED]` — The ratio of Gross Paid Indemnity in a Period to Total Indemnity Paid through the year
- **Paids and OSLR max month total**  `[OWNER-DEFINED]` — Paid and outstanding loss reserve monthly amount by year (same as gross paid)
- **Pending Claims Count**  `[OWNER-DEFINED]` — Total pending claims count
- **Pipeline Claims Count**  `[OWNER-DEFINED]` — This KPI header would be updated as Pending Recovery Claims Count in new model. This shows the Pending cont of Claims which have a potential Recovery oppurtunity.
- **QuarterYear**  `[OWNER-DEFINED]` — Quarter year is derived from claim accounting period
- **Recovery Ratio**  `[OWNER-DEFINED]` — Ratio of Total recovery to Total Indemnity paid in a  period
- **Referral Ratio**  `[OWNER-DEFINED]` — Referral ration as total referrals by total new claims
- **Referrals**  `[OWNER-DEFINED]` — Total number of referrals  _(name reused across apps — confirm context)_
- **Unreserved %**  `[OWNER-DEFINED]` — This used to represent the % of Unresreved Claims but I don't think this would be included in new model

## TPA Performance Dashboard

- **% Acknowledgements Issued Within SLA**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Percentage of claims acknowledged within the SLA standard (commonly 5 working days).
- **% Against New Cases In The Month**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Generic ratio of the subject count to new cases (claims) opened in the month x 100. Confirm the numerator in context.
- **% Claim Reserves Registered Within SLA**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Percentage of claims where the reserve was registered within the SLA standard.
- **% Correspondence Answered Within SLA**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Percentage of correspondence answered within the SLA standard.
- **% Of Abandoned Calls**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Abandoned calls / calls offered x 100.
- **% Of Cases Answered Within SLA**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Percentage of telephony cases answered within the SLA target time = answered within SLA / calls offered x 100.
- **% Payments Issued Within SLA**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Percentage of payments processed/issued within the SLA standard.
- **Average Claims Cost**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Average total cost per claim = total (indemnity + expense) / number of claims.
- **Average Days Open - Closed Claims**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Average number of days a closed claim was open (reported/opened to closed).
- **Average Days To Acknowledge Claims**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Mean working days from claim reported to acknowledged.
- **Average Days To Answer Comms**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Mean working days to respond to correspondence/queries.
- **Average Days To Answer Communication**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Mean working days to respond to correspondence/queries.
- **Average Days To Issue Payment**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Mean working days from payment received/approved to payment issued.
- **Average Days To Issue Payment'**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Mean working days from payment received/approved to payment issued. (Trailing quote is a source typo.)
- **Average Days To Register Claim Reserve**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Mean working days from claim open to reserve registered.
- **Complaints % Against New Cases In The Month**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Complaints received in the month / new cases (claims) in the month x 100.
- **Complaints As A % Of New Claims**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Complaints received / new claims in the period x 100.
- **Complaints As A % Of New Claims By Vendor**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Complaints as a percentage of new claims, broken down by TPA/vendor.
- **Complaints In Month**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of complaints received in the month.
- **Declinature Review 'Passed**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of declinature decisions that passed QA review. (Stray quote is a source typo.)
- **Declinature Review Fails**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of declinature decisions that failed QA review.
- **Declinatures % Of New Claims In Reporting Period**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Declined claims / new claims in the reporting period x 100.
- **Declinatures As % Of New Claims In Reporting Period**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Declined claims / new claims in the reporting period x 100.
- **Fraud Referrals % Of New Claims**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Fraud referrals / new claims in the period x 100.
- **No Of Calls Answered Within SLA**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of calls answered within the SLA target time.
- **Number Of Cases In Litigation**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Count of claims currently in litigation.
- **Number Of Fraud Referrals**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Count of claims referred for fraud investigation.
- **Number Of Identified Recoveries**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Count of claims with an identified recovery opportunity.
- **Quality Check '- Passed**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of claim QA checks passed. (Stray quote is a source typo.)
- **Quality Check'- Failed**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of claim QA checks failed. (Stray quote is a source typo.)
- **Quality Check'- Passed (Month) %**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Percentage of claim QA checks passed in the month = passed / total checked x 100. (Stray quote is a source typo.)
- **Quality Check- Failed (Month) %**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Percentage of claim QA checks failed in the month = failed / total checked x 100.
- **Recoveries % Of New Claims**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Claims with an identified recovery / new claims in the period x 100.
- **SLA Declinatures In Reporting Period**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of declinatures issued within SLA in the reporting period.
- **TPA Handling Fee**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Fee paid to the TPA for handling claims in the period.
- **Telephony - % Of Cases Answered Within SLA**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Percentage of telephony cases answered within SLA = answered within SLA / offered x 100.
- **Telephony - Abandoned Ratio**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Abandoned calls / calls offered x 100.
- **Telephony - No Of Calls Answered Within SLA**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of calls answered within the SLA target time.
- **Telephony - No. Of Abandoned Calls**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of calls abandoned before being answered.
- **Total Complaints**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Total number of complaints received in the period.
- **Total Paid - Indemnity & Expenses**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Sum of indemnity paid plus expense paid in the period.
- **Total Upheld**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of complaints upheld (decided in the complainant's favour).
- **Vendor Performance Management Levels**  `[PROPRIETARY (confirm with owner)]` — The internal tiering/levels framework used to manage TPA/vendor performance. Proprietary — confirm with vendor management.
- **Volume Of Calls Abandoned**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of calls abandoned (caller hung up before being answered).
- **Volume Of Calls Answered**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of calls answered.
- **Volume Of Calls Answered Within SLA**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of calls answered within the SLA target time.
- **Volume Of Calls Offered**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Total number of inbound calls presented to the queue.
- **Volume Of New Claims>5 Days**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Number of new claims not acknowledged/actioned within 5 days.
- **Walkaway Claims**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Count of claims the claimant withdrew or abandoned before a decision was reached.
- **Walkaways As % Of New Claims In Reporting Period**  `[INDUSTRY-STANDARD (confirm thresholds)]` — Walkaway claims / new claims in the reporting period x 100.

## Transactional App

- **Annual Caseload**  `[OWNER-DEFINED]` — Total cases in a yeat
- **Average Response Time in Working Days Where We are Lead**  `[OWNER-DEFINED]` — Provides Average Response Time in Working Days Where We are Lead by Bureau Lead Adjuster Name wise
- **CGM Company**  `[OWNER-DEFINED]` — Provides Volume of transactions processed within 4 days and Volume of transactions processed Outside 4 days for CGM Company for Rollimg 4 months
- **CGM Syndicate**  `[OWNER-DEFINED]` — Provides Volume of transactions processed within 4 days and Volume of transactions processed Outside 4 days for CGM Syndicate for rolling 4 months
- **CGM Total Trasnaction Processed - Birmingham**  `[OWNER-DEFINED]` — Total number of CGM transaction processed inBirmingham
- **CGM Total Trasnaction Processed - Glasgow**  `[OWNER-DEFINED]` — Total number of CGM transaction processed in Glasgow
- **CGM Total Trasnaction Processed - London**  `[OWNER-DEFINED]` — Total number of CGM transaction processed in London
- **Closed Claim Indicator**  `[OWNER-DEFINED]` — Total Number of Closed claims
- **Count of Response Time Days**  `[OWNER-DEFINED]` — Count of transaction by response time days
- **Detailed Chart**  `[OWNER-DEFINED]` — Provides the Tabular view
- **ECF Queried Response Type per Total Adviced per Business Unit**  `[OWNER-DEFINED]` — ECF Response time for Queries and Rejections Volume and Queries and Rejections %age per Total Adviced Response Type
- **FTE**  `[OWNER-DEFINED]` — Total FTE
- **In SLA**  `[OWNER-DEFINED]` — Percetage of transactions within SLA
- **Monthly Caseload**  `[OWNER-DEFINED]` — Total casesd in a month
- **New & Closed Claim Volumes Last 12 Months - Lead Only**  `[OWNER-DEFINED]` — Total number of New & Closed Claim Volumes Last 12 Months - Lead Only
- **New & Closed Claim Volumes Last 12 Months by LOB - Lead Only**  `[OWNER-DEFINED]` — Total number of New & Closed Claim Volumes Last 12 Months by LOB - Lead Only
- **New Claim Indicator**  `[OWNER-DEFINED]` — Total Number of New claims
- **Number on Month**  `[OWNER-DEFINED]` — Number of YTD month
- **Open Claim Incurred Value by LOB & CGM Entity**  `[OWNER-DEFINED]` — Total Number of Open Claim Incurred Value by LOB & CGM Entity
- **Open Claim Volume by LOB & CGM Entity**  `[OWNER-DEFINED]` — Total Number of Open Claim Volume by LOB & CGM Entity
- **Out SLA**  `[OWNER-DEFINED]` — Percetage of transactions taken more time than SLA
- **Overall % Month to date - Overall**  `[OWNER-DEFINED]` — Provides Overall % Month to Date by Participant role wise
- **Overall Month to date - Overall**  `[OWNER-DEFINED]` — Provides Overall Month to Date by Participant role wise
- **Overall Volume % Month to Date**  `[OWNER-DEFINED]` — Total number of Overall Volume % Month to date for Within SLA , Outside SLA and Grand Total by LOB and Participant role wise
- **Overall Volume % Month to Date**  `[OWNER-DEFINED]` — Total number of Overall Volume % Month to date for Within SLA , Outside SLA and Grand Total by Participant role, Office and Bureau Lead Adjuster Name wise
- **Overall Volume Month to Date**  `[OWNER-DEFINED]` — Total number of Overall Volume Month to date for Within SLA , Outside SLA and Grand Total by Participant role, Office and Bureau Lead Adjuster Name wise
- **Overall Volume Month to Date**  `[OWNER-DEFINED]` — Total number of Overall Volume Month to date for Within SLA , Outside SLA and Grand Total by LOB and Participant role wise
- **Pending Claims Indicator**  `[OWNER-DEFINED]` — Total Number of Pending Claims
- **Response Time Processed**  `[OWNER-DEFINED]` — Number of Transactions Processed
- **Response Time in Days(Birmingham) - Both count and %**  `[OWNER-DEFINED]` — Response time in days and in percentage by year in Birmingham
- **Response Time in Days(Glasgow) - Both count and %**  `[OWNER-DEFINED]` — Response time in days and in percentage by year in Glasgow
- **Response Time in Days(London) - Both count and %**  `[OWNER-DEFINED]` — Response time in days and in percentage by year in London
- **Response Times Per Business Unit**  `[OWNER-DEFINED]` — Response Time Within SLA and Outside SLA
- **Rolling 4 months by LOB**  `[OWNER-DEFINED]` — Provides With SLA and Outside SLA count for Rolling 4 months by LOB wise
- **Rolling 4 months by LOB and Month wise( Bar Chart)**  `[OWNER-DEFINED]` — Provides Rolling 4 months by LOB and Month wise for within SLA and Outside SLA
- **Rolling 4 months by Month wise**  `[OWNER-DEFINED]` — Provides Rolling 4 months by Month wise for within SLA and Outside SLA
- **Rolling 4 months by Month wise(both count and %)**  `[OWNER-DEFINED]` — Provides Rolling 4 months by Month wise for within SLA(Count), Within SLA(%), Outside SLA(Count) and Outside SLA(%)
- **Static Claims Portfolio by Business Unit and by LOB**  `[OWNER-DEFINED]` — Total Number of Static Volumes, Static Volume % of Total Pending, Static Reserve and Static Reserve % of Total Pending Reserve by Business unit and by LOB
- **Table View**  `[OWNER-DEFINED]` — Provides the Tabular view of Broker Claims Volume and Vlaue view
- **Total Transaction**  `[OWNER-DEFINED]` — Total number of Transactions
- **Total Transaction Processed by - CUAL Vs CEG**  `[OWNER-DEFINED]` — Number of Transactions based on Entity
- **Total Transaction Processed by - London, Glasgow and Birmingham**  `[OWNER-DEFINED]` — Number of Transactions based on Office Location
- **Transaction Processed by Adjuster**  `[OWNER-DEFINED]` — Number of transactions processed by adjuster
- **Transaction Processed by Broker**  `[OWNER-DEFINED]` — Transactions Processed count of Response Time Days
- **Transaction Processed by LOB**  `[OWNER-DEFINED]` — Number of Transaction by Lines of Business
- **Transaction Volumes & Speed of Performance**  `[OWNER-DEFINED]` — Count of Response Time Days and Within SLA % Broker wise
- **Year Month**  `[OWNER-DEFINED]` — Year Month for Lloyd's and LIRMA


---

# Appendix A — Proprietary KPIs needing owner sign-off

6 metrics are proprietary to your business. Provisional definitions are in the
catalogue tagged PROPRIETARY; replace them with the owning team's authoritative wording.

## A&H Claims Connect Database (4)
- [ ] % CSP Achieved - Basic Book/Direct Marketing/NAC  (sheet: CSP Usage)
- [ ] CSP Ingested Claims - Basic Book/Direct Marketing/NAC  (sheet: CSP Usage)
- [ ] Class 3 Check  (sheet: Conduct Risk)
- [ ] Total Claim - Basic Book/Direct Marketing/NAC  (sheet: CSP Usage)

## MAR-Operational (1)
- [ ] Reserve ending in 001 for Local Regulatory Reason  (sheet: Nominals)

## TPA Performance Dashboard (1)
- [ ] Vendor Performance Management Levels  (sheet: Case Analysis & Data Quality)

---

# Appendix B — Reclassified dimensions (were labelled KPIs)

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

---

# Appendix C — Non-metric items (excluded)

Chart/table objects and navigation labels from the source list. Not analysable metrics —
the skill should ignore these if a user references them.

## TPA Performance Dashboard

- **All Figures On This Tab Relate To The Most Recent Scorecard Submission.**  `[NAVIGATION/LABEL]` — Explanatory note on the tab, not a metric. Exclude from analysis.
- **Click Here For Direct Access To The AP Dashboard**  `[NAVIGATION/LABEL]` — Navigation link, not a metric. Exclude from analysis.
- **Click Here To Declinatures Tab**  `[NAVIGATION/LABEL]` — Navigation link, not a metric. Exclude from analysis.
- **Click Here To Fraud Tab**  `[NAVIGATION/LABEL]` — Navigation link, not a metric. Exclude from analysis.
- **Click Here To Recent TPA Scorecard Level**  `[NAVIGATION/LABEL]` — Navigation link, not a metric. Exclude from analysis.
- **Click Here To Service & Performance Tab'**  `[NAVIGATION/LABEL]` — Navigation link, not a metric. Exclude from analysis.
- **Click Here To TPA Scorecard Gap Analysis Tab**  `[NAVIGATION/LABEL]` — Navigation link, not a metric. Exclude from analysis.
- **Customer Metrics Rag Table By Vendor**  `[CHART/TABLE OBJECT]` — A Red/Amber/Green status table of customer-service metrics per vendor — a presentation object, not a single metric.
- **Declinatures Overview By TPA**  `[CHART/TABLE OBJECT]` — A chart object showing declinatures broken down by TPA, not a single metric.
- **Financial Overview By Year**  `[CHART/TABLE OBJECT]` — A chart object showing financials by year, not a single metric.
- **Financials  Overview By TPA**  `[CHART/TABLE OBJECT]` — A chart object showing financials broken down by TPA, not a single metric.
- **Fraud Referrals Overview By TPB**  `[CHART/TABLE OBJECT]` — A chart object showing fraud referrals by TPA (source says 'TPB'), not a single metric.
- **Telephony Stats By Year**  `[CHART/TABLE OBJECT]` — A chart object showing telephony stats by year, not a single metric.
- **Telephony Stats Overview By TPA**  `[CHART/TABLE OBJECT]` — A chart object showing telephony stats by TPA, not a single metric.
- **Total Recovery By Vendor**  `[CHART/TABLE OBJECT]` — Sum of recoveries broken down by TPA/vendor — a chart breakdown of the recovery total.

---

# Appendix D — Owner-documented definitions (authoritative)

These supersede earlier industry-standard placeholders; provenance is OWNER-DEFINED.

- **New Claims** — Claims opened in one accounting period.
- **Closed Claims** — Claims closed in one accounting period.
- **Pending Claims** — Claims with a status of open or reopened at the end of an accounting period.
- **Reopened Claims** — Claims reopened in the accounting period.
- **Closing Ratio** — Claims closed in the accounting period divided by claims opened in the accounting period.
- **Net Closing Ratio** — Claims closed in the accounting period divided by claims opened and reopened in the accounting period.
- **Reopened Ratio** — Claims reopened in the accounting period divided by claims closed in the accounting period.
- **ACPOC** — The incurred value of all open or reopened claims divided by the count of those claims (Average Cost per Outstanding Claims).
- **ACPSC** — The incurred value of all closed claims divided by the count of closed claims (Average Cost per Settled Claims).
- **Claim Life Days** — Days open (reported to closed for closed claims; reported to current date for pending claims) divided by the count of those claims.
- **Time to Settle** — The average claim life days for all closed claims selected.
- **Incurred** — Indemnity + expenses + reserves − recoveries.
- **Nominal Reserves** — The sum of reserves on any claim with a cumulative gross (DACs 1 & 2) original-currency reserve of 77, 88, 99 or 123.
- **Nominal Age** — The average age of claims holding a nominal reserve in the period selected.
- **Inactive Claims (>270 days)** — Count of open or reopened claims with no financial transaction for 270 days or more.
- **Volume - 1 Year Static Claims** — Claims opened or reopened in the accounting period with no financial movement for 365 days.
- **Value - 1 Year Static Claims** — Incurred total of claims opened or reopened in the accounting period with no financial movement for 365 days.
- **Paid Indemnity** — The paid indemnity in the time period selected.
- **Paid Expenses** — The paid expenses in the time period selected.
- **FNOL to First Indemnity** — Days from the reported date to the first indemnity payment in Genius.
- **FNOL to Final Indemnity** — Days from the reported date to the last indemnity payment in Genius.
- **Reserve Completion (0-20 Business days)** — Count of claims where registration (opened date − reported date) was below 20 business days, against all claims opened in that accounting period.
- **Claim Frequency** — The percentage of distinct claims per policy.
- **Claim Lag** — The time gap between a policy's effective date and when the first claim is reported.
- **Closed Claims Volume** — Claims reported based on underwriting year, now closed.
- **Open Claims Volume** — Claims reported based on underwriting year, still open.
- **Policy with Claim** — The percentage of policies which have at least one claim on them.
- **Total Claims** — Claims reported with respect to underwriting year.
