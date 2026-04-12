# =============================================================================
# data/qvd_loader.py
# Phase 1 - Step 1: QVD Reader and DataFrame Loader
# =============================================================================
# Responsibilities:
#   - Load configuration from config.yaml
#   - Generate dummy claims data (when no QVD files available)
#   - Read real QVD files via pyqvd (when available)
#   - Apply smart loading strategy (recent data, chunking, aggregates)
#   - Expose a clean DataFrame to the rest of the app
# =============================================================================

import os
import sys
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Logging setup - all modules use the same logger name "claims"
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("claims.data")


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_config(config_path: str = "config/config.yaml") -> dict:
    """
    Load the central YAML configuration file.

    Args:
        config_path: Relative or absolute path to config.yaml

    Returns:
        Dictionary of all configuration values.

    Raises:
        FileNotFoundError: If the config file cannot be found.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found at: {path.resolve()}")

    with open(path, "r") as f:
        config = yaml.safe_load(f)

    logger.info(f"Config loaded from {path.resolve()}")
    return config


# ---------------------------------------------------------------------------
# Dummy data generator — fully vectorized for 5M+ rows
# ---------------------------------------------------------------------------

def generate_dummy_data(n_rows: int, col_map: dict) -> pd.DataFrame:
    """
    Generate realistic-looking dummy insurance claims data using vectorized
    numpy operations for performance. Supports all 74 real columns.

    Args:
        n_rows:   Number of rows to generate.
        col_map:  Column name mapping from config (so column names match config).

    Returns:
        A Pandas DataFrame with dummy claims data.
    """
    t0 = time.time()
    logger.info(f"Generating {n_rows:,} rows of dummy claims data (vectorized)...")

    rng = np.random.default_rng(42)

    # =====================================================================
    # Reference data pools
    # =====================================================================

    # --- Country ---
    countries = np.array(["US", "UK", "Canada", "Australia", "Germany",
                          "France", "Japan", "Singapore"])
    country_weights = np.array([0.50, 0.25, 0.10, 0.05, 0.03, 0.03, 0.02, 0.02])

    # --- Business Entity / Entity ---
    business_entities = np.array([
        "Acme Insurance Corp", "Global Re Solutions", "Pacific Underwriters",
        "Atlantic Casualty Group", "Northern Shield Insurance",
        "Continental Risk Partners", "Summit Re Holdings",
    ])
    entities = np.array([
        "ACM-US", "ACM-UK", "GRS-INTL", "PAC-APAC", "ATL-EU",
        "NOR-NA", "CON-GLOBAL", "SUM-RE",
    ])

    # --- Status ---
    statuses_derived = np.array(["Open", "Closed", "Pending", "Rejected", "Under Review"])
    status_weights = np.array([0.30, 0.45, 0.10, 0.08, 0.07])
    statuses_original = np.array(["Active", "Finalized", "Awaiting Info",
                                   "Declined", "In Review"])
    system_statuses = np.array(["OPEN", "CLOSED", "PEND", "REJ", "REVIEW"])

    # --- LOB hierarchy ---
    # Executive -> Major -> Minor
    lob_hierarchy = [
        ("Commercial", "Property", ["Fire", "Flood", "Wind", "Earthquake", "Theft"]),
        ("Commercial", "Casualty", ["General Liability", "Auto Liability",
                                     "Workers Comp", "Professional Liability"]),
        ("Commercial", "Marine", ["Cargo", "Hull", "P&I", "Inland Marine"]),
        ("Personal", "Auto", ["Collision", "Comprehensive", "Liability", "PIP"]),
        ("Personal", "Homeowners", ["Dwelling", "Contents", "Liability",
                                     "Loss of Use"]),
        ("Specialty", "Aviation", ["Hull", "Liability", "Passenger"]),
        ("Specialty", "Cyber", ["Data Breach", "Business Interruption",
                                 "Network Security"]),
        ("Reinsurance", "Treaty", ["Quota Share", "Excess of Loss",
                                    "Stop Loss"]),
    ]
    exec_lobs = np.array([h[0] for h in lob_hierarchy])
    major_lobs = np.array([h[1] for h in lob_hierarchy])
    minor_lobs_per = [h[2] for h in lob_hierarchy]

    # --- Claim offices ---
    claim_offices = np.array([
        "New York", "London", "Toronto", "Sydney", "Chicago",
        "Los Angeles", "Dallas", "Atlanta", "Singapore", "Frankfurt",
    ])

    # --- Adjusters ---
    adjuster_first = np.array(["James", "Sarah", "Mohammed", "Emily", "David",
                                "Priya", "John", "Laura", "Ahmed", "Claire",
                                "Robert", "Maria", "Wei", "Fatima", "Carlos"])
    adjuster_last = np.array(["Smith", "Jones", "Patel", "Williams", "Brown",
                               "Taylor", "Davies", "Wilson", "Evans", "Thomas",
                               "Garcia", "Chen", "Kumar", "Ali", "Mueller"])

    # --- Cause of Loss ---
    cause_codes = np.array(["COL01", "COL02", "COL03", "COL04", "COL05",
                             "COL06", "COL07", "COL08", "COL09", "COL10"])
    cause_descrs = np.array([
        "Fire/Smoke Damage", "Water/Flood Damage", "Vehicle Collision",
        "Slip and Fall", "Product Defect", "Weather Event",
        "Theft/Vandalism", "Equipment Failure", "Workplace Injury",
        "Professional Error",
    ])

    # --- Claim Type ---
    claim_type_codes = np.array(["CT01", "CT02", "CT03", "CT04", "CT05", "CT06"])
    claim_type_descrs = np.array(["Property Damage", "Bodily Injury",
                                   "Liability", "Motor", "Marine", "Cyber"])

    # --- Condition/Injury ---
    cid_codes = np.array(["CID01", "CID02", "CID03", "CID04", "CID05"])
    cid_names = np.array(["Fracture", "Burn", "Contusion", "Strain",
                           "Property Loss"])

    # --- Contributing Factor ---
    cf_codes = np.array(["CF01", "CF02", "CF03", "CF04", "CF05"])
    cf_descrs = np.array(["Negligence", "Weather", "Equipment Malfunction",
                           "Human Error", "Natural Disaster"])

    # --- Catastrophe ---
    cat_codes = np.array(["", "CAT001", "CAT002", "CAT003", "CAT004", "CAT005"])
    cat_descrs = np.array(["", "Hurricane Alpha", "Wildfire Season 2023",
                            "Winter Storm Beta", "Earthquake Delta",
                            "Flood Event Gamma"])
    cat_weights = np.array([0.85, 0.04, 0.03, 0.03, 0.03, 0.02])

    # --- Currencies ---
    currencies = np.array(["USD", "GBP", "CAD", "AUD", "EUR", "JPY", "SGD"])
    currency_factors = {"USD": 1.0, "GBP": 0.79, "CAD": 1.36, "AUD": 1.53,
                        "EUR": 0.92, "JPY": 149.5, "SGD": 1.34}

    # --- Coverage codes ---
    coverage_codes = np.array(["COV01", "COV02", "COV03", "COV04", "COV05",
                                "COV06", "COV07", "COV08"])

    # --- Producers ---
    producer_names = np.array([
        "Marsh McLennan", "Aon plc", "Willis Towers Watson", "Arthur Gallagher",
        "Hub International", "Brown & Brown", "Lockton Companies",
        "USI Insurance", "Alliant Insurance", "Acrisure",
    ])
    producer_codes = np.array(["PRD001", "PRD002", "PRD003", "PRD004", "PRD005",
                                "PRD006", "PRD007", "PRD008", "PRD009", "PRD010"])

    # --- Industry ---
    industries = np.array([
        "Manufacturing", "Healthcare", "Technology", "Retail",
        "Construction", "Financial Services", "Transportation",
        "Energy", "Real Estate", "Hospitality",
    ])

    # --- Reserving ---
    reserving_lines = np.array(["RL01", "RL02", "RL03", "RL04", "RL05"])
    reserving_classes = np.array(["Standard", "Excess", "Treaty", "Facultative",
                                   "Pool"])

    # --- Plant Division ---
    plant_divisions = np.array(["DIV-A", "DIV-B", "DIV-C", "DIV-D"])

    # --- Multinational ---
    mn_codes = np.array(["", "MN01", "MN02", "MN03"])
    mn_descrs = np.array(["", "Controlled Master", "Local Admitted",
                           "Freedom of Services"])
    mn_flags = np.array(["N", "Y"])

    # --- Product codes ---
    product_codes = np.array(["P100", "P200", "P300", "P400", "P500"])

    # --- Claim source ---
    claim_sources = np.array(["Direct", "Broker", "Agent", "Online", "Phone"])

    # --- Producing offices ---
    prod_office_codes = np.array(["PO01", "PO02", "PO03", "PO04", "PO05",
                                   "PO06", "PO07", "PO08"])
    prod_offices = np.array(["New York Office", "London Office",
                              "Toronto Office", "Sydney Office",
                              "Chicago Office", "LA Office",
                              "Singapore Office", "Frankfurt Office"])

    # --- DAC codes ---
    dac_codes = np.array(["DAC01", "DAC02", "DAC03", "DAC04", "DAC05"])

    # --- Location of loss ---
    loss_locations = np.array([
        "123 Main St, New York, NY", "45 High Street, London",
        "789 Bay St, Toronto, ON", "10 Harbour St, Sydney",
        "555 Michigan Ave, Chicago, IL", "200 Sunset Blvd, Los Angeles, CA",
        "88 Raffles Place, Singapore", "12 Kaiserstr, Frankfurt",
        "321 Elm St, Dallas, TX", "678 Peachtree Rd, Atlanta, GA",
    ])

    # --- Policy holder names ---
    ph_first = np.array(["Acme", "Global", "Pacific", "United", "Premier",
                          "National", "Metro", "Alliance", "Summit", "Pinnacle",
                          "Atlas", "Nexus", "Zenith", "Vertex", "Apex"])
    ph_last = np.array(["Corp", "Industries", "Holdings", "Enterprises",
                         "Services", "Group", "Solutions", "Partners",
                         "International", "Technologies"])

    # =====================================================================
    # Generate columns — all vectorized
    # =====================================================================
    logger.info("  Generating identifiers and categorical columns...")

    # Claim Number -- fast via pandas Series string ops
    claim_numbers = ("CLM" + pd.Series(np.arange(1, n_rows + 1)).astype(str).str.zfill(7)).values

    # Country
    country_idx = rng.choice(len(countries), size=n_rows, p=country_weights)
    country_col = countries[country_idx]

    # Business Entity & Entity
    be_idx = rng.integers(0, len(business_entities), size=n_rows)
    business_entity_col = business_entities[be_idx]
    entity_col = entities[rng.integers(0, len(entities), size=n_rows)]

    # Status columns (linked)
    status_idx = rng.choice(len(statuses_derived), size=n_rows, p=status_weights)
    status_derived_col = statuses_derived[status_idx]
    status_original_col = statuses_original[status_idx]
    system_status_col = system_statuses[status_idx]

    # DAC Code
    dac_col = dac_codes[rng.integers(0, len(dac_codes), size=n_rows)]

    # LOB hierarchy
    lob_idx = rng.integers(0, len(lob_hierarchy), size=n_rows)
    exec_lob_col = exec_lobs[lob_idx]
    major_lob_col = major_lobs[lob_idx]
    # For minor LOB, pick a random minor within the selected hierarchy
    minor_lob_col = np.empty(n_rows, dtype=object)
    for i_lob in range(len(lob_hierarchy)):
        mask = lob_idx == i_lob
        count = mask.sum()
        if count > 0:
            minors = np.array(minor_lobs_per[i_lob])
            minor_lob_col[mask] = minors[rng.integers(0, len(minors), size=count)]

    # Policy Number -- fast via pandas Series string ops
    pol_nums_int = rng.integers(1, n_rows * 2, size=n_rows)
    policy_numbers = ("POL" + pd.Series(pol_nums_int).astype(str).str.zfill(8)).values

    # Claim Office
    office_col = claim_offices[rng.integers(0, len(claim_offices), size=n_rows)]

    # Responsible Adjuster
    adj_f_idx = rng.integers(0, len(adjuster_first), size=n_rows)
    adj_l_idx = rng.integers(0, len(adjuster_last), size=n_rows)
    adjuster_col = np.char.add(np.char.add(adjuster_first[adj_f_idx], " "),
                                adjuster_last[adj_l_idx])

    # =====================================================================
    # Date columns — vectorized
    # =====================================================================
    logger.info("  Generating date columns...")
    end_ts = int(datetime.today().timestamp())
    start_ts = int((datetime.today() - timedelta(days=5 * 365)).timestamp())

    # Event Date
    event_ts = rng.integers(start_ts, end_ts, size=n_rows)
    event_dates = pd.to_datetime(event_ts, unit="s").normalize()

    # Reported Date: 0-60 days after event
    report_offset = rng.integers(0, 61, size=n_rows)
    reported_dates = event_dates + pd.to_timedelta(report_offset, unit="D")

    # Claim Opened Date: 0-5 days after reported
    open_offset = rng.integers(0, 6, size=n_rows)
    opened_dates = reported_dates + pd.to_timedelta(open_offset, unit="D")

    # Claim Closed Date: only for Closed/Rejected
    is_closed = np.isin(status_derived_col, ["Closed", "Rejected"])
    close_offset = rng.integers(1, 730, size=n_rows)  # 1-730 days after open
    closed_dates = opened_dates + pd.to_timedelta(close_offset, unit="D")
    # Cap at today
    today = pd.Timestamp.today().normalize()
    closed_dates = closed_dates.where(closed_dates <= today, today)
    closed_dates = closed_dates.where(is_closed, pd.NaT)

    # Claim Event Description
    event_desc_templates = np.array([
        "Property damage reported at insured location",
        "Vehicle collision on public road",
        "Water damage from burst pipe",
        "Fire damage to commercial premises",
        "Slip and fall at insured premises",
        "Equipment malfunction causing damage",
        "Storm damage to roof and structure",
        "Theft of insured property",
        "Workplace injury during operations",
        "Product liability incident reported",
    ])
    event_desc_col = event_desc_templates[rng.integers(0, len(event_desc_templates),
                                                        size=n_rows)]

    # Accident Year
    accident_year_col = event_dates.year.values

    # Claim Life Days: derived
    closed_minus_opened = (closed_dates - opened_dates).days
    today_minus_opened = (today - opened_dates).days
    claim_life = np.where(
        is_closed,
        closed_minus_opened,
        today_minus_opened,
    ).astype(np.int32)
    # Floor at 0
    claim_life = np.maximum(claim_life, 0)

    # =====================================================================
    # Currency
    # =====================================================================
    ledger_currency_col = currencies[rng.integers(0, len(currencies), size=n_rows)]

    # =====================================================================
    # Financial columns — lognormal distribution
    # =====================================================================
    logger.info("  Generating financial columns...")

    # Base incurred amount (lognormal)
    incurred_usd = np.round(rng.lognormal(mean=10.0, sigma=1.5, size=n_rows), 2)

    # Indemnity paid: fraction of incurred, only for closed claims
    indemnity_ratio = rng.uniform(0.3, 0.95, size=n_rows)
    indemnity_paid_usd = np.where(
        is_closed,
        np.round(incurred_usd * indemnity_ratio, 2),
        0.0,
    )

    # Outstanding reserve: for open claims
    is_open = ~is_closed
    reserve_ratio = rng.uniform(0.4, 1.0, size=n_rows)
    outstanding_reserve_usd = np.where(
        is_open,
        np.round(incurred_usd * reserve_ratio, 2),
        0.0,
    )

    # Expense reserve
    expense_reserve_usd = np.round(incurred_usd * rng.uniform(0.02, 0.15,
                                                                size=n_rows), 2)

    # Expense paid
    expense_paid_usd = np.where(
        is_closed,
        np.round(expense_reserve_usd * rng.uniform(0.5, 1.0, size=n_rows), 2),
        0.0,
    )

    # Recoveries (small fraction, often zero)
    has_recovery = rng.random(size=n_rows) < 0.15
    recoveries_usd = np.where(
        has_recovery,
        np.round(incurred_usd * rng.uniform(0.05, 0.3, size=n_rows), 2),
        0.0,
    )

    # Ledger amounts: multiply by currency factor
    # Build currency factor array via vectorized lookup
    _cf_keys = np.array(list(currency_factors.keys()))
    _cf_vals = np.array(list(currency_factors.values()))
    _cf_map = dict(zip(_cf_keys, _cf_vals))
    _currency_indices = np.array([_cf_map.get(c, 1.0) for c in currencies])
    currency_idx_arr = rng.integers(0, len(currencies), size=n_rows)  # already generated above
    # Re-use the ledger_currency_col indices: map from currency string to factor
    currency_factor_arr = np.empty(n_rows)
    for i, curr in enumerate(currencies):
        mask = ledger_currency_col == curr
        currency_factor_arr[mask] = currency_factors.get(curr, 1.0)
    indemnity_paid_ledger = np.round(indemnity_paid_usd * currency_factor_arr, 2)
    expense_reserve_ledger = np.round(expense_reserve_usd * currency_factor_arr, 2)
    expense_paid_ledger = np.round(expense_paid_usd * currency_factor_arr, 2)
    recoveries_ledger = np.round(recoveries_usd * currency_factor_arr, 2)
    outstanding_reserve_ledger = np.round(outstanding_reserve_usd * currency_factor_arr, 2)
    incurred_ledger = np.round(incurred_usd * currency_factor_arr, 2)

    # =====================================================================
    # Remaining categorical columns
    # =====================================================================
    logger.info("  Generating remaining categorical columns...")

    # Catastrophe
    cat_idx = rng.choice(len(cat_codes), size=n_rows, p=cat_weights)
    cat_code_col = cat_codes[cat_idx]
    cat_desc_col = cat_descrs[cat_idx]

    # Coverage Code
    coverage_col = coverage_codes[rng.integers(0, len(coverage_codes), size=n_rows)]

    # Cause of Loss
    col_idx = rng.integers(0, len(cause_codes), size=n_rows)
    cause_code_col = cause_codes[col_idx]
    cause_descr_col = cause_descrs[col_idx]

    # Claim Type Code/Description
    ct_idx = rng.integers(0, len(claim_type_codes), size=n_rows)
    ct_code_col = claim_type_codes[ct_idx]
    ct_descr_col = claim_type_descrs[ct_idx]

    # Condition/Injury
    cid_idx = rng.integers(0, len(cid_codes), size=n_rows)
    cid_code_col = cid_codes[cid_idx]
    cid_name_col = cid_names[cid_idx]

    # Contributing Factor
    cf_idx = rng.integers(0, len(cf_codes), size=n_rows)
    cf_code_col = cf_codes[cf_idx]
    cf_descr_col = cf_descrs[cf_idx]

    # Producer
    prod_idx = rng.integers(0, len(producer_codes), size=n_rows)
    prod_code_col = producer_codes[prod_idx]
    prod_name_col = producer_names[prod_idx]

    # Industry
    industry_col = industries[rng.integers(0, len(industries), size=n_rows)]

    # Policy UWY
    policy_uwy_col = rng.integers(2019, 2027, size=n_rows)

    # Policy dates
    policy_eff_offset = rng.integers(-365, 1, size=n_rows)
    policy_eff_dates = event_dates + pd.to_timedelta(policy_eff_offset, unit="D")
    policy_exp_dates = policy_eff_dates + pd.to_timedelta(365, unit="D")

    # Policy Holder Name
    ph_f_idx = rng.integers(0, len(ph_first), size=n_rows)
    ph_l_idx = rng.integers(0, len(ph_last), size=n_rows)
    ph_name_col = np.char.add(np.char.add(ph_first[ph_f_idx], " "), ph_last[ph_l_idx])

    # Reserving
    res_line_col = reserving_lines[rng.integers(0, len(reserving_lines), size=n_rows)]
    res_class_col = reserving_classes[rng.integers(0, len(reserving_classes),
                                                    size=n_rows)]

    # Plant Division
    plant_col = plant_divisions[rng.integers(0, len(plant_divisions), size=n_rows)]

    # Nominal Reserve
    nominal_reserve_col = np.round(rng.lognormal(mean=9.0, sigma=1.0,
                                                  size=n_rows), 2)

    # Multinational
    mn_idx = rng.integers(0, len(mn_codes), size=n_rows)
    mn_code_col = mn_codes[mn_idx]
    mn_desc_col = mn_descrs[mn_idx]
    mn_flag_col = mn_flags[rng.integers(0, len(mn_flags), size=n_rows)]

    # Loss description
    loss_desc_templates = np.array([
        "Damage to insured property from covered peril",
        "Bodily injury sustained at insured premises",
        "Third party liability claim for damages",
        "Motor vehicle damage from collision",
        "Water damage from natural flooding",
        "Fire loss at commercial location",
        "Theft of inventory and equipment",
        "Storm damage to building exterior",
    ])
    loss_desc_col = loss_desc_templates[rng.integers(0, len(loss_desc_templates),
                                                      size=n_rows)]

    # Location of loss
    loss_loc_col = loss_locations[rng.integers(0, len(loss_locations), size=n_rows)]

    # Producing office
    po_idx = rng.integers(0, len(prod_office_codes), size=n_rows)
    po_code_col = prod_office_codes[po_idx]
    po_name_col = prod_offices[po_idx]

    # Product code
    product_col = product_codes[rng.integers(0, len(product_codes), size=n_rows)]

    # Claim source
    source_col = claim_sources[rng.integers(0, len(claim_sources), size=n_rows)]

    # Flags
    mar_flag = rng.choice(["Y", "N"], size=n_rows, p=[0.1, 0.9])
    coinsurance_col = np.round(rng.uniform(0.0, 1.0, size=n_rows), 4)
    bulk_indicator = rng.choice(["Y", "N"], size=n_rows, p=[0.05, 0.95])

    # Signal reserves
    company_signal = rng.choice(["Y", "N"], size=n_rows, p=[0.2, 0.8])
    company_signal_amt = np.where(
        company_signal == "Y",
        np.round(rng.lognormal(mean=10.0, sigma=1.0, size=n_rows), 2),
        0.0,
    )
    mp_signal = rng.choice(["Y", "N"], size=n_rows, p=[0.15, 0.85])
    mp_signal_amt = np.where(
        mp_signal == "Y",
        np.round(rng.lognormal(mean=10.0, sigma=1.0, size=n_rows), 2),
        0.0,
    )

    # Company share
    company_share_col = np.round(rng.uniform(0.1, 1.0, size=n_rows), 4)

    # Block indicator
    block_indicator = rng.choice(["Y", "N"], size=n_rows, p=[0.1, 0.9])

    # =====================================================================
    # Build the DataFrame
    # =====================================================================
    logger.info("  Assembling DataFrame...")

    df = pd.DataFrame({
        "Claim Number": claim_numbers,
        "Country": country_col,
        "Business Entity": business_entity_col,
        "Entity": entity_col,
        "Claim Status Derived": status_derived_col,
        "Claim Status Original": status_original_col,
        "System Claim Status": system_status_col,
        "Claim Dac Code": dac_col,
        "Executive LOB": exec_lob_col,
        "Major LOB": major_lob_col,
        "Minor LOB": minor_lob_col,
        "Policy Number": policy_numbers,
        "Claim Office": office_col,
        "Responsible Adjuster": adjuster_col,
        "Event Date": event_dates,
        "Claim Event Desc": event_desc_col,
        "Reported Date": reported_dates,
        "Claim Opened Date": opened_dates,
        "Claim Closed Date": closed_dates,
        "Accident Year": accident_year_col,
        "ledger Currency": ledger_currency_col,
        "Indemnity Paid USD": indemnity_paid_usd,
        "Expense Reserve USD": expense_reserve_usd,
        "Expense Paid USD": expense_paid_usd,
        "Recoveries USD": recoveries_usd,
        "Outstanding Reserve USD": outstanding_reserve_usd,
        "Incurred USD": incurred_usd,
        "Indemnity Paid Ledger": indemnity_paid_ledger,
        "Expense Reserve Ledger": expense_reserve_ledger,
        "Expense Paid Ledger": expense_paid_ledger,
        "Recoveries Ledger": recoveries_ledger,
        "Outstanding Reserve Ledger": outstanding_reserve_ledger,
        "Incurred Ledger": incurred_ledger,
        "Claim Life Days": claim_life,
        "Catastrophe Code": cat_code_col,
        "Catastrophe Description": cat_desc_col,
        "Coverage Code": coverage_col,
        "Cause of Loss Code": cause_code_col,
        "Cause Of Loss Descr": cause_descr_col,
        "Claim Type Code": ct_code_col,
        "Claim Type Description": ct_descr_col,
        "Condition Injury Damage Code": cid_code_col,
        "Condition Injury Damage Name": cid_name_col,
        "Contributing Factor Code": cf_code_col,
        "Contributing Factor Descr": cf_descr_col,
        "Current Global Producer": prod_code_col,
        "Producer Name": prod_name_col,
        "Industry Explanantion": industry_col,
        "Policy UWY": policy_uwy_col,
        "Policy Effective Date": policy_eff_dates,
        "Policy Expiration Date": policy_exp_dates,
        "Policy Holder Name": ph_name_col,
        "Reserving Line": res_line_col,
        "Reserving Class": res_class_col,
        "Plant Division": plant_col,
        "Nominal Reserve": nominal_reserve_col,
        "MN Description": mn_desc_col,
        "Multinational Code": mn_code_col,
        "MN": mn_flag_col,
        "Loss Description": loss_desc_col,
        "Location of Loss": loss_loc_col,
        "Producing Office Code": po_code_col,
        "Producing Office": po_name_col,
        "Product Code": product_col,
        "Claim Source": source_col,
        "MAR Fast Track Flag": mar_flag,
        "Coinsurance": coinsurance_col,
        "Bulk Claim Indicator": bulk_indicator,
        "Company Signal Reserve": company_signal,
        "Company Singal Reserve Amount": company_signal_amt,
        "Market Place Singal Reserve": mp_signal,
        "Market Place Singal Reserve Amount": mp_signal_amt,
        "Company Share": company_share_col,
        "Block Indicator": block_indicator,
    })

    # Convert low-cardinality string columns to Categorical to save memory
    logger.info("  Converting categorical columns to save memory...")
    categorical_cols = [
        "Country", "Business Entity", "Entity",
        "Claim Status Derived", "Claim Status Original", "System Claim Status",
        "Claim Dac Code", "Executive LOB", "Major LOB", "Minor LOB",
        "Claim Office", "ledger Currency",
        "Catastrophe Code", "Catastrophe Description", "Coverage Code",
        "Cause of Loss Code", "Cause Of Loss Descr",
        "Claim Type Code", "Claim Type Description",
        "Condition Injury Damage Code", "Condition Injury Damage Name",
        "Contributing Factor Code", "Contributing Factor Descr",
        "Current Global Producer", "Producer Name", "Industry Explanantion",
        "Reserving Line", "Reserving Class", "Plant Division",
        "MN Description", "Multinational Code", "MN",
        "Producing Office Code", "Producing Office",
        "Product Code", "Claim Source",
        "MAR Fast Track Flag", "Bulk Claim Indicator",
        "Company Signal Reserve", "Market Place Singal Reserve",
        "Block Indicator",
        "Claim Event Desc", "Loss Description", "Location of Loss",
    ]
    for c in categorical_cols:
        if c in df.columns:
            df[c] = df[c].astype("category")

    elapsed = time.time() - t0
    mem_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
    logger.info(f"Dummy data generated. Shape: {df.shape}")
    logger.info(f"  Time elapsed: {elapsed:.1f}s")
    logger.info(f"  Memory usage: {mem_mb:,.1f} MB")

    return df


# ---------------------------------------------------------------------------
# Real QVD loader
# ---------------------------------------------------------------------------

def load_qvd_file(file_path: str, col_map: dict, recent_months: int) -> pd.DataFrame:
    """
    Load a single QVD file using pyqvd and apply date filtering to avoid
    loading all 20M rows at once.

    Args:
        file_path:     Full path to the .qvd file.
        col_map:       Column name mapping from config.
        recent_months: Only load rows from the last N months.

    Returns:
        A filtered Pandas DataFrame.

    Raises:
        ImportError:  If pyqvd is not installed.
        FileNotFoundError: If the QVD file doesn't exist.
    """
    try:
        from pyqvd import QvdDataFrame          # only imported when needed
    except ImportError:
        raise ImportError(
            "pyqvd is not installed. Run: pip install pyqvd\n"
            "Or set dummy_mode: true in config.yaml to use generated data."
        )

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"QVD file not found: {path.resolve()}")

    logger.info(f"Reading QVD file: {path.name}")
    qvd = QvdDataFrame.from_qvd(str(path))
    df  = qvd.to_pandas()
    logger.info(f"QVD loaded raw shape: {df.shape}")

    # Apply date filter to keep memory usage down
    df = apply_date_filter(df, col_map, recent_months)
    return df


def load_all_qvd_files(qvd_folder: str, col_map: dict, recent_months: int) -> pd.DataFrame:
    """
    Load and combine all .qvd files found in the specified folder.

    Args:
        qvd_folder:    Path to the folder containing QVD files.
        col_map:       Column name mapping from config.
        recent_months: Date window filter to apply to each file.

    Returns:
        A single combined DataFrame from all QVD files.
    """
    folder = Path(qvd_folder)
    qvd_files = list(folder.glob("*.qvd"))

    if not qvd_files:
        raise FileNotFoundError(f"No .qvd files found in: {folder.resolve()}")

    logger.info(f"Found {len(qvd_files)} QVD file(s) in {qvd_folder}")

    frames = []
    for qvd_file in qvd_files:
        try:
            df = load_qvd_file(str(qvd_file), col_map, recent_months)
            frames.append(df)
        except Exception as e:
            logger.error(f"Failed to load {qvd_file.name}: {e}")

    if not frames:
        raise RuntimeError("No QVD files could be loaded successfully.")

    combined = pd.concat(frames, ignore_index=True)
    logger.info(f"All QVD files combined. Total shape: {combined.shape}")
    return combined


# ---------------------------------------------------------------------------
# Smart loading helpers
# ---------------------------------------------------------------------------

def apply_date_filter(df: pd.DataFrame, col_map: dict, recent_months: int) -> pd.DataFrame:
    """
    Filter the DataFrame to only include claims submitted within the last
    N months. This is the primary memory-saving strategy.

    Args:
        df:            Input DataFrame.
        col_map:       Column name mapping from config.
        recent_months: Number of months to look back.

    Returns:
        Date-filtered DataFrame.
    """
    date_col = col_map["submitted_date"]

    if date_col not in df.columns:
        logger.warning(f"Date column '{date_col}' not found. Skipping date filter.")
        return df

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    cutoff = datetime.today() - timedelta(days=recent_months * 30)
    filtered = df[df[date_col] >= cutoff].copy()

    logger.info(
        f"Date filter applied (last {recent_months} months). "
        f"Rows before: {len(df):,}  After: {len(filtered):,}"
    )
    return filtered


def build_aggregated_summary(df: pd.DataFrame, col_map: dict) -> dict:
    """
    Compute high-level summary statistics that are always kept in memory.
    These power quick answers without scanning the full DataFrame.

    Args:
        df:      The loaded claims DataFrame.
        col_map: Column name mapping from config.

    Returns:
        Dictionary of summary metrics.
    """
    c = col_map   # shorthand

    summary = {
        "total_claims":          len(df),
        "status_counts":         df[c["status"]].value_counts().to_dict(),
        "type_counts":           df[c["claim_type"]].value_counts().to_dict(),
        "region_counts":         df[c["region"]].value_counts().to_dict(),
        "total_claim_amount":    round(df[c["claim_amount"]].sum(), 2),
        "total_paid_amount":     round(df[c["paid_amount"]].sum(), 2),
        "total_reserve_amount":  round(df[c["reserve_amount"]].sum(), 2),
        "avg_claim_amount":      round(df[c["claim_amount"]].mean(), 2),
        "avg_days_open":         round(df[c["days_open"]].mean(), 1),
        "max_claim_amount":      round(df[c["claim_amount"]].max(), 2),
        "oldest_open_days":      int(df[df[c["status"]] == "Open"][c["days_open"]].max())
                                 if "Open" in df[c["status"]].values else 0,
        "data_loaded_at":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date_range_start":      str(df[c["submitted_date"]].min().date()),
        "date_range_end":        str(df[c["submitted_date"]].max().date()),
    }

    # --- Additional financial metrics (safe if columns missing) ---
    recoveries_col = c.get("recoveries_usd", "Recoveries USD")
    if recoveries_col in df.columns:
        summary["total_recoveries"] = round(df[recoveries_col].sum(), 2)

    expense_paid_col = c.get("expense_paid_usd", "Expense Paid USD")
    if expense_paid_col in df.columns:
        summary["total_expense_paid"] = round(df[expense_paid_col].sum(), 2)

    nominal_col = c.get("nominal_reserve", "Nominal Reserve")
    if nominal_col in df.columns:
        summary["avg_nominal_reserve"] = round(df[nominal_col].mean(), 2)

    logger.info(
        f"Summary built: {summary['total_claims']:,} claims, "
        f"${summary['total_claim_amount']:,.0f} total value"
    )
    return summary


# ---------------------------------------------------------------------------
# Main ClaimsDataLoader class
# ---------------------------------------------------------------------------

class ClaimsDataLoader:
    """
    Central data access object for the Claims ChatGPT system.

    Usage:
        loader = ClaimsDataLoader()
        loader.load()

        df      = loader.df           # Full working DataFrame
        summary = loader.summary      # Pre-computed summary stats
        col     = loader.col          # Column name mapping shorthand
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Initialise the loader by reading configuration.

        Args:
            config_path: Path to the YAML config file.
        """
        self.config     = load_config(config_path)
        self.col        = self.config["columns"]          # column name map
        self.data_cfg   = self.config["data"]             # data settings
        self.df = None               # type: pd.DataFrame
        self.summary = None          # type: dict
        self._loaded_at = None       # type: datetime

    # ------------------------------------------------------------------
    def load(self) -> pd.DataFrame:
        """
        Main entry point. Loads data from either dummy generator or QVD files
        depending on config setting, then builds the summary.

        Returns:
            The loaded DataFrame (also stored as self.df).
        """
        if self.data_cfg.get("dummy_mode", True):
            logger.info("dummy_mode is ON -- generating synthetic data")
            self.df = generate_dummy_data(
                n_rows  = self.data_cfg["dummy_row_count"],
                col_map = self.col,
            )
        else:
            logger.info("dummy_mode is OFF -- reading QVD files")
            self.df = load_all_qvd_files(
                qvd_folder    = self.data_cfg["qvd_folder"],
                col_map       = self.col,
                recent_months = self.data_cfg["recent_months"],
            )

        # Enforce hard row cap for safety
        max_rows = self.data_cfg.get("max_rows_in_memory", 5_500_000)
        if len(self.df) > max_rows:
            logger.warning(
                f"DataFrame has {len(self.df):,} rows -- capping at {max_rows:,} "
                f"to protect memory. Adjust max_rows_in_memory in config if needed."
            )
            self.df = self.df.tail(max_rows).reset_index(drop=True)

        self.summary    = build_aggregated_summary(self.df, self.col)
        self._loaded_at = datetime.now()

        logger.info("Data load complete.")
        return self.df

    # ------------------------------------------------------------------
    def reload(self) -> pd.DataFrame:
        """
        Force a full reload of the data. Useful for manual refresh commands
        or the scheduled nightly refresh.

        Returns:
            Freshly loaded DataFrame.
        """
        logger.info("Reload triggered -- clearing existing data")
        self.df      = None
        self.summary = None
        return self.load()

    # ------------------------------------------------------------------
    def get_subset(self, status=None, region=None, claim_type=None):
        """
        Return a filtered subset of the DataFrame on demand.
        Used by the RAG pipeline to narrow context for specific questions.

        Args:
            status:     Filter by claim status (e.g. "Open").
            region:     Filter by region (e.g. "US").
            claim_type: Filter by claim type (e.g. "Property Damage").

        Returns:
            Filtered DataFrame (does not modify self.df).

        Raises:
            RuntimeError: If data hasn't been loaded yet.
        """
        if self.df is None:
            raise RuntimeError("Data not loaded. Call loader.load() first.")

        subset = self.df.copy()

        if status:
            subset = subset[subset[self.col["status"]].str.lower() == status.lower()]
        if region:
            subset = subset[subset[self.col["region"]].str.lower() == region.lower()]
        if claim_type:
            subset = subset[subset[self.col["claim_type"]].str.lower() == claim_type.lower()]

        logger.debug(
            f"Subset returned: status={status}, region={region}, "
            f"type={claim_type}. Rows: {len(subset):,}"
        )
        return subset

    # ------------------------------------------------------------------
    @property
    def last_loaded(self) -> str:
        """Human-readable timestamp of when data was last loaded."""
        if self._loaded_at is None:
            return "Not loaded yet"
        return self._loaded_at.strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        rows = len(self.df) if self.df is not None else 0
        return f"<ClaimsDataLoader rows={rows:,} loaded_at='{self.last_loaded}'>"
