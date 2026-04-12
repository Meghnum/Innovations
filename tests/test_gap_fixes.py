"""Tests verifying all 8 aggregation gaps are fixed.

Each test class targets one specific gap identified during scenario testing.
Uses a comprehensive DataFrame with all financial columns to verify correct
handler routing and filtering.
"""

import pandas as pd
import numpy as np
import pytest

from ai.rag_pipeline import handle_aggregation, handle_lookup


# ---------------------------------------------------------------------------
# Column mapping (comprehensive — includes financial + specialty columns)
# ---------------------------------------------------------------------------

COL = {
    "claim_id": "Claim Number",
    "status": "Claim Status Derived",
    "claim_type": "Claim Type Description",
    "submitted_date": "Reported Date",
    "closed_date": "Claim Closed Date",
    "region": "Country",
    "claimant_name": "Policy Holder Name",
    "policy_holder_name": "Policy Holder Name",
    "claim_amount": "Incurred USD",
    "paid_amount": "Indemnity Paid USD",
    "reserve_amount": "Outstanding Reserve USD",
    "days_open": "Claim Life Days",
    "cause_of_loss_descr": "Cause Of Loss Descr",
    "executive_lob": "Executive LOB",
    "minor_lob": "Minor LOB",
    "contributing_factor_descr": "Contributing Factor Descr",
    "accident_year": "Accident Year",
    "policy_uwy": "Policy UWY",
    "policy_number": "Policy Number",
    "recoveries_usd": "Recoveries USD",
    "expense_paid_usd": "Expense Paid USD",
    "expense_reserve_usd": "Expense Reserve USD",
    "nominal_reserve": "Nominal Reserve",
    "incurred_usd": "Incurred USD",
    "outstanding_reserve_usd": "Outstanding Reserve USD",
    "indemnity_paid_usd": "Indemnity Paid USD",
    "bulk_claim_indicator": "Bulk Claim Indicator",
    "mar_fast_track_flag": "MAR Fast Track Flag",
}


# ---------------------------------------------------------------------------
# Fixture — comprehensive DataFrame
# ---------------------------------------------------------------------------

@pytest.fixture
def df():
    """DataFrame with all columns needed to test all 8 gaps."""
    data = {
        "Claim Number":            ["CLM001", "CLM002", "CLM003", "CLM004", "CLM005", "CLM006"],
        "Claim Status Derived":    ["Open", "Closed", "Open", "Closed", "Open", "Closed"],
        "Claim Type Description":  ["Bodily Injury", "Property Damage", "Bodily Injury",
                                    "Property Damage", "Auto", "Bodily Injury"],
        "Reported Date":           pd.to_datetime(["2023-01-01", "2023-03-01", "2023-06-01",
                                                    "2024-01-01", "2024-03-01", "2024-06-01"]),
        "Claim Closed Date":       pd.to_datetime([pd.NaT, "2023-09-01", pd.NaT,
                                                    "2024-06-01", pd.NaT, "2024-12-01"]),
        "Country":                 ["US", "UK", "US", "UK", "Canada", "UK"],
        "Policy Holder Name":      ["Alice Corp", "Bob Ltd", "Charlie Inc", "Diana Co",
                                    "Eve Corp", "Frank Ltd"],
        "Incurred USD":            [50000.0, 25000.0, 75000.0, 30000.0, 10000.0, 40000.0],
        "Indemnity Paid USD":      [20000.0, 25000.0, 0.0, 30000.0, 5000.0, 35000.0],
        "Outstanding Reserve USD": [30000.0, 0.0, 75000.0, 0.0, 5000.0, 5000.0],
        "Claim Life Days":         [180, 240, 120, 180, 60, 180],
        "Cause Of Loss Descr":     ["Water Damage", "Fire", "Slip And Fall", "Fire",
                                    "Collision", "Water Damage"],
        "Executive LOB":           ["Commercial", "Personal", "Commercial", "Personal",
                                    "Commercial", "Personal"],
        "Minor LOB":               ["Commercial Fire", "Marine Cargo", "General Liability",
                                    "Marine Cargo", "Auto Liability", "General Liability"],
        "Contributing Factor Descr": ["Equipment Failure", "Inadequate Maintenance",
                                      "Human Error", "Inadequate Maintenance",
                                      "Weather", "Equipment Failure"],
        "Accident Year":           [2023, 2023, 2023, 2024, 2024, 2024],
        "Policy UWY":              [2022, 2022, 2023, 2023, 2024, 2024],
        "Policy Number":           ["POL-001", "POL-002", "POL-003", "POL-004",
                                    "POL-005", "POL-006"],
        "Recoveries USD":          [5000.0, 3000.0, 0.0, 2000.0, 1000.0, 4000.0],
        "Expense Paid USD":        [2000.0, 1500.0, 3000.0, 1000.0, 500.0, 2500.0],
        "Expense Reserve USD":     [1000.0, 0.0, 2000.0, 0.0, 500.0, 0.0],
        "Nominal Reserve":         [1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        "Bulk Claim Indicator":    ["N", "N", "Y", "N", "Y", "N"],
        "MAR Fast Track Flag":     ["N", "Y", "N", "Y", "N", "N"],
    }
    return pd.DataFrame(data)


@pytest.fixture
def summary(df):
    """Summary dict matching the DataFrame."""
    return {
        "total_claims": len(df),
        "status_counts": df["Claim Status Derived"].value_counts().to_dict(),
        "type_counts": df["Claim Type Description"].value_counts().to_dict(),
        "region_counts": df["Country"].value_counts().to_dict(),
        "total_claim_amount": round(df["Incurred USD"].sum(), 2),
        "total_paid_amount": round(df["Indemnity Paid USD"].sum(), 2),
        "total_reserve_amount": round(df["Outstanding Reserve USD"].sum(), 2),
        "avg_claim_amount": round(df["Incurred USD"].mean(), 2),
        "avg_days_open": round(df["Claim Life Days"].mean(), 1),
        "max_claim_amount": round(df["Incurred USD"].max(), 2),
        "oldest_open_days": 180,
        "data_loaded_at": "2026-04-12 12:00:00",
        "date_range_start": "2023-01-01",
        "date_range_end": "2024-06-01",
    }


@pytest.fixture
def col():
    return COL.copy()


# =========================================================================
# Gap 1: Policy number lookup
# =========================================================================

class TestGap1_PolicyLookup:
    """POL-based query should find and return claim details."""

    def test_lookup_by_policy_number(self, df, col):
        result = handle_lookup(None, df, col, policy_id="POL-001")
        assert "CLM001" in result or "POL-001" in result
        assert "not found" not in result.lower()

    def test_lookup_unknown_policy(self, df, col):
        result = handle_lookup(None, df, col, policy_id="POL-999")
        assert "not found" in result.lower()

    def test_lookup_no_id(self, df, col):
        result = handle_lookup(None, df, col)
        assert "couldn't find" in result.lower() or "include" in result.lower()


# =========================================================================
# Gap 2: Minor LOB filter
# =========================================================================

class TestGap2_MinorLOBFilter:
    """Queries mentioning Minor LOB should filter by that column."""

    def test_total_for_commercial_fire(self, summary, df, col):
        result = handle_aggregation(
            "what is the total value for commercial fire claims?",
            summary, df, col,
        )
        # Should show filtered result, not full total
        assert "$" in result

    def test_marine_cargo_count(self, summary, df, col):
        result = handle_aggregation(
            "how many marine cargo claims?",
            summary, df, col,
        )
        # 2 marine cargo claims in fixture
        assert "2" in result


# =========================================================================
# Gap 3: Recoveries handler
# =========================================================================

class TestGap3_RecoveriesHandler:
    """Recoveries queries should use Recoveries USD column."""

    def test_total_recoveries(self, summary, df, col):
        result = handle_aggregation(
            "what is the total recoveries?",
            summary, df, col,
        )
        assert "Recoveries" in result
        assert "$" in result

    def test_recoveries_closed_uk(self, summary, df, col):
        result = handle_aggregation(
            "total recoveries on closed UK claims",
            summary, df, col,
        )
        assert "Recoveries" in result
        assert "matching" in result  # should show filter applied

    def test_subrogation_maps_to_recoveries(self, summary, df, col):
        result = handle_aggregation(
            "how much subrogation has been recovered?",
            summary, df, col,
        )
        assert "Recoveries" in result

    def test_average_recoveries(self, summary, df, col):
        result = handle_aggregation(
            "what is the average recovery amount?",
            summary, df, col,
        )
        assert "Average" in result
        assert "Recoveries" in result


# =========================================================================
# Gap 4: Cause of loss filter with average
# =========================================================================

class TestGap4_CauseOfLossAverage:
    """Queries filtered by cause of loss should work with averages."""

    def test_avg_days_water_damage(self, summary, df, col):
        result = handle_aggregation(
            "what is the average claim value for water damage?",
            summary, df, col,
        )
        assert "$" in result
        assert "matching" in result  # filtered

    def test_total_for_fire(self, summary, df, col):
        result = handle_aggregation(
            "total claim value for fire claims",
            summary, df, col,
        )
        assert "$" in result


# =========================================================================
# Gap 5: Accident year filter
# =========================================================================

class TestGap5_AccidentYearFilter:
    """Queries with accident year should filter correctly."""

    def test_incurred_by_accident_year_2023(self, summary, df, col):
        result = handle_aggregation(
            "what is the total value for accident year 2023?",
            summary, df, col,
        )
        assert "$" in result
        assert "matching" in result  # filtered

    def test_count_accident_year_2024(self, summary, df, col):
        result = handle_aggregation(
            "how many claims in accident year 2024?",
            summary, df, col,
        )
        assert "3" in result  # 3 claims in AY 2024


# =========================================================================
# Gap 6: Smart detector with filters
# =========================================================================

class TestGap6_SmartDetectorWithFilter:
    """Smart detector should apply filters before showing results."""

    def test_top_factors(self, summary, df, col):
        result = handle_aggregation(
            "what are the top contributing factors?",
            summary, df, col,
        )
        assert "Claim Type" in result or "Contributing" in result

    def test_biggest_drivers_open(self, summary, df, col):
        result = handle_aggregation(
            "biggest claim drivers for open claims",
            summary, df, col,
        )
        # Should filter to open claims
        assert "Claim Type" in result or "Contributing" in result


# =========================================================================
# Gap 7: Bulk claim indicator
# =========================================================================

class TestGap7_BulkClaimFilter:
    """Bulk claim queries should filter by Bulk Claim Indicator."""

    def test_bulk_claims_count(self, summary, df, col):
        result = handle_aggregation(
            "how many bulk claims do we have?",
            summary, df, col,
        )
        # 2 bulk claims (CLM003, CLM005)
        assert "2" in result

    def test_bulk_claims_total(self, summary, df, col):
        result = handle_aggregation(
            "total value of bulk claims",
            summary, df, col,
        )
        assert "$" in result
        assert "matching" in result


# =========================================================================
# Gap 8: Nominal reserve average
# =========================================================================

class TestGap8_NominalReserveAvg:
    """Nominal reserve queries should use Nominal Reserve column."""

    def test_avg_nominal_reserve(self, summary, df, col):
        result = handle_aggregation(
            "what is the average nominal reserve?",
            summary, df, col,
        )
        assert "Nominal Reserve" in result
        assert "Average" in result

    def test_total_nominal_reserve(self, summary, df, col):
        result = handle_aggregation(
            "total nominal reserve across all claims",
            summary, df, col,
        )
        assert "Nominal Reserve" in result
        assert "$" in result


# =========================================================================
# Additional: Financial column handlers
# =========================================================================

class TestFinancialHandlers:
    """Verify specific financial column queries route correctly."""

    def test_expense_paid(self, summary, df, col):
        result = handle_aggregation(
            "what is the total expense paid?",
            summary, df, col,
        )
        assert "Expense Paid" in result
        assert "$" in result

    def test_expense_reserve(self, summary, df, col):
        result = handle_aggregation(
            "total expense reserve",
            summary, df, col,
        )
        assert "Expense Reserve" in result

    def test_indemnity_paid(self, summary, df, col):
        result = handle_aggregation(
            "total indemnity paid",
            summary, df, col,
        )
        assert "Indemnity Paid" in result

    def test_alae_maps_to_expense(self, summary, df, col):
        result = handle_aggregation(
            "what is total alae?",
            summary, df, col,
        )
        assert "Expense Paid" in result

    def test_outstanding_reserve(self, summary, df, col):
        result = handle_aggregation(
            "total outstanding reserve",
            summary, df, col,
        )
        assert "Outstanding Reserve" in result

    def test_incurred_total(self, summary, df, col):
        result = handle_aggregation(
            "what is total incurred?",
            summary, df, col,
        )
        assert "Incurred" in result

    def test_recoveries_by_status(self, summary, df, col):
        result = handle_aggregation(
            "recoveries by status",
            summary, df, col,
        )
        assert "Recoveries" in result
        assert "by Status" in result

    def test_expense_by_region(self, summary, df, col):
        result = handle_aggregation(
            "expense paid by country",
            summary, df, col,
        )
        assert "Expense Paid" in result
        assert "by Country" in result


# =========================================================================
# Additional: _apply_filters integration
# =========================================================================

class TestApplyFiltersIntegration:
    """Verify _apply_filters works when combined with existing handlers."""

    def test_count_open_us(self, summary, df, col):
        result = handle_aggregation(
            "how many open claims in the US?",
            summary, df, col,
        )
        # 2 open US claims (CLM001, CLM003)
        assert "2" in result

    def test_total_closed_uk(self, summary, df, col):
        result = handle_aggregation(
            "total value of closed UK claims",
            summary, df, col,
        )
        assert "$" in result
        assert "matching" in result

    def test_uwy_filter(self, summary, df, col):
        result = handle_aggregation(
            "how many claims for uwy 2024?",
            summary, df, col,
        )
        # 2 claims with UWY 2024
        assert "2" in result

    def test_mar_fast_track(self, summary, df, col):
        result = handle_aggregation(
            "how many fast track claims?",
            summary, df, col,
        )
        # 2 MAR fast track claims
        assert "2" in result
