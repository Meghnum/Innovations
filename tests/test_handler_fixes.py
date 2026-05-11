"""Tests for the 5 handler fixes in rag_pipeline.handle_aggregation:

  Fix 1a: Bottom-N row-level
  Fix 1b: Bottom-N grouped / fewest-per-group
  Fix 2:  Date range "between X and Y" / "from X to Y"
  Fix 3:  Major LOB filter (incl. excluding / not-found message)
  Fix 4:  Generalized unique/distinct count
  Fix 5:  Multi-dimensional pivot "by A and by B"
"""
import pandas as pd
import pytest

from ai.rag_pipeline import handle_aggregation


COL = {
    "claim_id": "Claim Number",
    "status": "Claim Status Derived",
    "claim_type": "Claim Type Description",
    "submitted_date": "Reported Date",
    "closed_date": "Claim Closed Date",
    "claim_closed_date": "Claim Closed Date",
    "event_date": "Event Date",
    "region": "Country",
    "country": "Country",
    "policy_holder_name": "Policy Holder Name",
    "claim_amount": "Incurred USD",
    "paid_amount": "Indemnity Paid USD",
    "reserve_amount": "Outstanding Reserve USD",
    "major_lob": "Major LOB",
    "minor_lob": "Minor LOB",
    "executive_lob": "Executive LOB",
    "accident_year": "Accident Year",
    "policy_number": "Policy Number",
    "incurred_usd": "Incurred USD",
    "indemnity_paid_usd": "Indemnity Paid USD",
    "expense_paid_usd": "Expense Paid USD",
    "outstanding_reserve_usd": "Outstanding Reserve USD",
    "nominal_reserve": "Nominal Reserve",
}


@pytest.fixture
def df():
    return pd.DataFrame({
        "Claim Number":            [f"CLM{i:03d}" for i in range(1, 13)],
        "Claim Status Derived":    ["Open", "Closed", "Open", "Closed", "Open", "Closed",
                                     "Open", "Pending", "Open", "Closed", "Pending", "Open"],
        "Claim Type Description":  ["BI"] * 12,
        "Reported Date":           pd.to_datetime([
            "2020-03-15", "2020-07-10", "2021-02-20", "2021-11-05",
            "2022-06-01", "2023-01-15", "2019-09-09", "2024-02-01",
            "2020-01-05", "2021-12-31", "2022-08-22", "2023-05-17",
        ]),
        "Event Date":              pd.to_datetime([
            "2020-01-10", "2020-06-01", "2021-01-05", "2021-10-20",
            "2022-05-15", "2023-01-01", "2019-08-08", "2024-01-20",
            "2019-12-30", "2021-11-30", "2022-07-15", "2023-04-01",
        ]),
        "Claim Closed Date":       pd.to_datetime([pd.NaT] * 12),
        "Country":                 ["US", "UK", "US", "UK", "Canada", "UK",
                                     "US", "US", "Canada", "UK", "US", "Canada"],
        "Policy Holder Name":      [f"Holder {i}" for i in range(1, 13)],
        "Major LOB":               ["A&H", "A&H", "Marine", "Marine", "Auto", "Auto",
                                     "Property", "Property", "Casualty", "Casualty",
                                     "A&H", "Marine"],
        "Minor LOB":               ["A&H"] * 12,
        "Executive LOB":           ["Commercial"] * 12,
        "Accident Year":           [2020, 2020, 2021, 2021, 2022, 2023,
                                     2019, 2024, 2019, 2021, 2022, 2023],
        "Policy Number":           ["POL-A", "POL-A", "POL-B", "POL-C", "POL-D", "POL-D",
                                     "POL-E", "POL-F", "POL-G", "POL-H", "POL-I", "POL-J"],
        "Incurred USD":            [100.0, -50.0, 9000.0, 200.0, 500.0, 7500.0,
                                     1.0, 250.0, 50.0, 80.0, 30.0, 60.0],
        "Indemnity Paid USD":      [50.0, 20.0, 3000.0, 100.0, 200.0, 2500.0,
                                     0.0, 100.0, 25.0, 40.0, 10.0, 30.0],
        "Expense Paid USD":        [10.0, 5.0, 1000.0, 20.0, 50.0, 800.0,
                                     0.0, 25.0, 5.0, 8.0, 3.0, 6.0],
        "Outstanding Reserve USD": [40.0, 25.0, 5000.0, 80.0, 250.0, 4200.0,
                                     1.0, 125.0, 20.0, 32.0, 17.0, 24.0],
        "Nominal Reserve":         [1.0] * 12,
    })


@pytest.fixture
def summary(df):
    return {
        "total_claims": len(df),
        "status_counts": df["Claim Status Derived"].value_counts().to_dict(),
        "type_counts":   df["Claim Type Description"].value_counts().to_dict(),
        "region_counts": df["Country"].value_counts().to_dict(),
        "total_claim_amount": round(df["Incurred USD"].sum(), 2),
        "total_paid_amount": round(df["Indemnity Paid USD"].sum(), 2),
        "total_reserve_amount": round(df["Outstanding Reserve USD"].sum(), 2),
        "avg_claim_amount": round(df["Incurred USD"].mean(), 2),
        "avg_days_open": 100,
        "max_claim_amount": float(df["Incurred USD"].max()),
        "oldest_open_days": 100,
        "data_loaded_at": "2026-04-16 12:00:00",
        "date_range_start": "2019-08-08",
        "date_range_end": "2024-02-01",
    }


@pytest.fixture
def col():
    return COL.copy()


# ---------- Fix 1a: Bottom-N row-level ----------
def test_fix1a_bottom_n_rows(df, summary, col):
    out = handle_aggregation("Show me the bottom 10 claims by incurred value", summary, df, col, {})
    assert "Bottom 10" in out
    # Expect 10 bullet rows
    assert out.count("\n- ") == 10
    # Lowest value first
    assert "-50" in out or "-$50" in out or "$-50" in out


# ---------- Fix 1b: Bottom-N grouped ----------
def test_fix1b_least_open_by_lob(df, summary, col):
    out = handle_aggregation("Which Major LOB has the least open claims?", summary, df, col, {})
    # Among Open claims: A&H=1, Marine=1, Auto=1, Property=1, Casualty=1 — any of them
    assert "has the fewest claims" in out or "Bottom 1" in out or "least" in out.lower()


# ---------- Fix 2: Date range "between X and Y" ----------
def test_fix2_between_two_dates(df, summary, col):
    out = handle_aggregation(
        "Total expense paid for claims with event dates between Jan 1, 2020 and December 31, 2021.",
        summary, df, col, {},
    )
    # Of 12 rows, events in [2020-01-01, 2021-12-31] are rows 1,2,3,4,10 → 5 rows
    assert "matching" in out
    assert "5 matching" in out or "(5" in out
    assert "Expense Paid" in out


def test_fix2_from_to_years(df, summary, col):
    out = handle_aggregation(
        "Total incurred from 2020 to 2021",
        summary, df, col, {},
    )
    assert "matching" in out
    # rows reported in 2020-2021: 1,2,3,4,9,10 → 6
    assert "6 matching" in out or "(6" in out


# ---------- Fix 3: Major LOB filter ----------
def test_fix3_major_lob_include(df, summary, col):
    out = handle_aggregation("Total incurred for Marine claims", summary, df, col, {})
    # Marine rows: 3, 4, 12 → 9000+200+60 = 9260
    assert "9,260" in out or "9260" in out


def test_fix3_major_lob_excluding(df, summary, col):
    out = handle_aggregation(
        "Total nominal reserve excluding the Casualty and Auto LOBs",
        summary, df, col, {},
    )
    # 12 rows - 2 Auto - 2 Casualty = 8 matching
    assert "8 matching" in out or "(8" in out


def test_fix3_major_lob_not_found(df, summary, col):
    out = handle_aggregation(
        "What is the split of Indemnity vs Expense for the Cyber LOB?",
        summary, df, col, {},
    )
    assert "cyber" in out.lower()
    assert "available" in out.lower()
    assert "A&H" in out and "Marine" in out


# ---------- Fix 4: Generalized unique/distinct count ----------
def test_fix4_unique_policy_numbers(df, summary, col):
    out = handle_aggregation(
        "How many unique policy numbers are there?", summary, df, col, {},
    )
    # 10 unique policies (POL-A and POL-D repeat)
    assert "10" in out
    assert "unique" in out.lower()


def test_fix4_unique_with_more_than(df, summary, col):
    out = handle_aggregation(
        "How many unique policy numbers have filed more than one claim?",
        summary, df, col, {},
    )
    # POL-A (2 claims) and POL-D (2 claims) = 2
    assert "2" in out
    assert "more than" in out.lower()


# ---------- Fix 5: Multi-dim pivot ----------
def test_fix5_pivot_by_and_by(df, summary, col):
    out = handle_aggregation(
        "Give me a breakdown of claims by Major LOB and by Claim Status",
        summary, df, col, {},
    )
    assert "|" in out  # markdown table
    assert "Major LOB" in out
    # Column headers should contain statuses
    assert "Open" in out and "Closed" in out
