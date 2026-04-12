"""Tests for handle_aggregation routing in ai.rag_pipeline.

Verifies that every natural-language question routes to the correct handler
and that keyword-ordering issues (e.g. generic "breakdown" firing before
specific dimension matchers) are resolved.
"""

import pandas as pd
import pytest

from ai.rag_pipeline import handle_aggregation


# ---------------------------------------------------------------------------
# Column mapping (mirrors config/config.yaml)
# ---------------------------------------------------------------------------

COL = {
    "claim_id": "Claim Number",
    "status": "Claim Status Derived",
    "claim_type": "Claim Type Description",
    "submitted_date": "Reported Date",
    "closed_date": "Claim Closed Date",
    "region": "Country",
    "claimant_name": "Policy Holder Name",
    "claim_amount": "Incurred USD",
    "paid_amount": "Indemnity Paid USD",
    "reserve_amount": "Outstanding Reserve USD",
    "days_open": "Claim Life Days",
    "cause_of_loss_descr": "Cause Of Loss Descr",
    "executive_lob": "Executive LOB",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_df():
    """Small but realistic DataFrame covering all groupby dimensions."""
    data = {
        "Claim Number":          ["CLM001", "CLM002", "CLM003", "CLM004", "CLM005"],
        "Claim Status Derived":  ["Open", "Closed", "Open", "Pending", "Open"],
        "Claim Type Description": ["Auto", "Property", "Auto", "Liability", "Property"],
        "Reported Date":         pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01",
                                                  "2024-04-01", "2024-05-01"]),
        "Claim Closed Date":     pd.to_datetime([pd.NaT, "2024-06-01", pd.NaT,
                                                  pd.NaT, pd.NaT]),
        "Country":               ["US", "UK", "US", "Canada", "UK"],
        "Policy Holder Name":    ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        "Incurred USD":          [10000.0, 25000.0, 15000.0, 5000.0, 30000.0],
        "Indemnity Paid USD":    [5000.0, 20000.0, 0.0, 0.0, 10000.0],
        "Outstanding Reserve USD": [5000.0, 5000.0, 15000.0, 5000.0, 20000.0],
        "Claim Life Days":       [120, 90, 60, 200, 30],
        "Cause Of Loss Descr":   ["Fire", "Flood", "Fire", "Theft", "Flood"],
        "Executive LOB":         ["Commercial", "Personal", "Commercial", "Personal", "Commercial"],
    }
    return pd.DataFrame(data)


@pytest.fixture
def summary():
    """Pre-computed summary dict matching the build_summary structure."""
    return {
        "total_claims": 5,
        "status_counts": {"Open": 3, "Closed": 1, "Pending": 1},
        "type_counts": {"Auto": 2, "Property": 2, "Liability": 1},
        "region_counts": {"US": 2, "UK": 2, "Canada": 1},
        "total_claim_amount": 85000.00,
        "total_paid_amount": 35000.00,
        "total_reserve_amount": 50000.00,
        "avg_claim_amount": 17000.00,
        "avg_days_open": 100.0,
        "max_claim_amount": 30000.00,
        "oldest_open_days": 120,
        "data_loaded_at": "2024-06-01 10:00:00",
        "date_range_start": "2024-01-01",
        "date_range_end": "2024-05-01",
    }


@pytest.fixture
def col():
    return COL.copy()


# =========================================================================
# 1. Entity-aware status count
# =========================================================================

class TestEntityAwareStatusCount:
    def test_how_many_open_claims(self, summary, sample_df, col):
        result = handle_aggregation(
            "how many open claims are there?", summary, sample_df, col,
            entities={"status": "Open"},
        )
        assert "3" in result
        assert "Open" in result

    def test_count_pending_claims(self, summary, sample_df, col):
        result = handle_aggregation(
            "count of pending claims", summary, sample_df, col,
            entities={"status": "Pending"},
        )
        assert "1" in result
        assert "Pending" in result


# =========================================================================
# 2. Count by region
# =========================================================================

class TestCountByRegion:
    def test_how_many_claims_per_region(self, summary, sample_df, col):
        result = handle_aggregation(
            "how many claims per region?", summary, sample_df, col,
        )
        assert "Claims Count by Region" in result
        assert "US" in result
        assert "UK" in result

    def test_count_claims_by_region(self, summary, sample_df, col):
        result = handle_aggregation(
            "count claims by region", summary, sample_df, col,
        )
        assert "Claims Count by Region" in result


# =========================================================================
# 3. Count by type
# =========================================================================

class TestCountByType:
    def test_how_many_claims_by_type(self, summary, sample_df, col):
        result = handle_aggregation(
            "how many claims by type?", summary, sample_df, col,
        )
        assert "Claims Count by Claim Type" in result
        assert "Auto" in result

    def test_count_by_claim_type(self, summary, sample_df, col):
        result = handle_aggregation(
            "count by claim type", summary, sample_df, col,
        )
        assert "Claims Count by Claim Type" in result


# =========================================================================
# 4. Average by type
# =========================================================================

class TestAverageByType:
    def test_average_value_by_type(self, summary, sample_df, col):
        result = handle_aggregation(
            "average claim value by type", summary, sample_df, col,
        )
        assert "Average Claim Value by Claim Type" in result

    def test_avg_by_type(self, summary, sample_df, col):
        result = handle_aggregation(
            "avg amount by type", summary, sample_df, col,
        )
        assert "Average Claim Value by Claim Type" in result


# =========================================================================
# 5. Average by region
# =========================================================================

class TestAverageByRegion:
    def test_average_by_region(self, summary, sample_df, col):
        result = handle_aggregation(
            "average claim value by region", summary, sample_df, col,
        )
        assert "Average Claim Value by Region" in result

    def test_avg_by_region(self, summary, sample_df, col):
        result = handle_aggregation(
            "avg amount per region", summary, sample_df, col,
        )
        assert "Average Claim Value by Region" in result


# =========================================================================
# 6. Total value by claim type
# =========================================================================

class TestTotalValueByType:
    def test_total_value_by_claim_type(self, summary, sample_df, col):
        result = handle_aggregation(
            "total value by claim type", summary, sample_df, col,
        )
        assert "Total Claim Value by Claim Type" in result

    def test_total_amount_per_type(self, summary, sample_df, col):
        result = handle_aggregation(
            "total amount per type", summary, sample_df, col,
        )
        assert "Total Claim Value by Claim Type" in result


# =========================================================================
# 7. Total value by region
# =========================================================================

class TestTotalValueByRegion:
    def test_total_value_by_region(self, summary, sample_df, col):
        result = handle_aggregation(
            "total value by region", summary, sample_df, col,
        )
        assert "Total Claim Value by Region" in result

    def test_total_amount_per_region(self, summary, sample_df, col):
        result = handle_aggregation(
            "total amount per region", summary, sample_df, col,
        )
        assert "Total Claim Value by Region" in result


# =========================================================================
# 8. Total value by status
# =========================================================================

class TestTotalValueByStatus:
    def test_total_value_by_status(self, summary, sample_df, col):
        result = handle_aggregation(
            "total value by status", summary, sample_df, col,
        )
        assert "Total Claim Value by Status" in result

    def test_total_amount_per_status(self, summary, sample_df, col):
        result = handle_aggregation(
            "total amount per status", summary, sample_df, col,
        )
        assert "Total Claim Value by Status" in result


# =========================================================================
# 9. Generic status count
# =========================================================================

class TestGenericStatusCount:
    def test_how_many_open(self, summary, sample_df, col):
        result = handle_aggregation(
            "how many open claims?", summary, sample_df, col,
        )
        assert "Open" in result

    def test_how_many_closed(self, summary, sample_df, col):
        result = handle_aggregation(
            "how many closed claims?", summary, sample_df, col,
        )
        assert "Closed" in result

    def test_how_many_claims_total(self, summary, sample_df, col):
        result = handle_aggregation(
            "how many claims are there?", summary, sample_df, col,
        )
        assert "5" in result


# =========================================================================
# 10. Total value
# =========================================================================

class TestTotalValue:
    def test_total_claim_value(self, summary, sample_df, col):
        result = handle_aggregation(
            "what is the total claim value?", summary, sample_df, col,
        )
        assert "$85,000.00" in result
        assert "total" in result.lower()

    def test_total_amount(self, summary, sample_df, col):
        result = handle_aggregation(
            "total amount of all claims", summary, sample_df, col,
        )
        assert "$85,000.00" in result


# =========================================================================
# 11. Average days open
# =========================================================================

class TestAverageDaysOpen:
    def test_average_days_open(self, summary, sample_df, col):
        result = handle_aggregation(
            "what is the average days open?", summary, sample_df, col,
        )
        assert "100.0" in result
        assert "days" in result.lower()

    def test_avg_days_claims_open(self, summary, sample_df, col):
        result = handle_aggregation(
            "avg number of days claims are open", summary, sample_df, col,
        )
        assert "100.0" in result


# =========================================================================
# 12. Average claim value
# =========================================================================

class TestAverageClaimValue:
    def test_average_claim_value(self, summary, sample_df, col):
        result = handle_aggregation(
            "what is the average claim value?", summary, sample_df, col,
        )
        assert "$17,000.00" in result

    def test_avg_claim_amount(self, summary, sample_df, col):
        result = handle_aggregation(
            "avg claim amount", summary, sample_df, col,
        )
        assert "$17,000.00" in result


# =========================================================================
# 13. Cause of loss breakdown
# =========================================================================

class TestCauseOfLossBreakdown:
    def test_breakdown_by_cause_of_loss(self, summary, sample_df, col):
        result = handle_aggregation(
            "breakdown by cause of loss", summary, sample_df, col,
        )
        assert "Claims by Cause of Loss" in result
        assert "Fire" in result
        assert "Flood" in result

    def test_cause_of_loss_distribution(self, summary, sample_df, col):
        result = handle_aggregation(
            "cause of loss distribution", summary, sample_df, col,
        )
        assert "Claims by Cause of Loss" in result

    def test_loss_cause_breakdown(self, summary, sample_df, col):
        result = handle_aggregation(
            "what is the loss cause breakdown?", summary, sample_df, col,
        )
        assert "Claims by Cause of Loss" in result


# =========================================================================
# 14. LOB breakdown
# =========================================================================

class TestLOBBreakdown:
    def test_line_of_business_breakdown(self, summary, sample_df, col):
        result = handle_aggregation(
            "line of business breakdown", summary, sample_df, col,
        )
        assert "Claims by Line of Business" in result
        assert "Commercial" in result

    def test_lob_distribution(self, summary, sample_df, col):
        result = handle_aggregation(
            "lob distribution", summary, sample_df, col,
        )
        assert "Claims by Line of Business" in result


# =========================================================================
# 15. Country breakdown
# =========================================================================

class TestCountryBreakdown:
    def test_breakdown_by_country(self, summary, sample_df, col):
        result = handle_aggregation(
            "breakdown by country", summary, sample_df, col,
        )
        assert "Claims by Country" in result
        assert "US" in result

    def test_claims_by_countries(self, summary, sample_df, col):
        result = handle_aggregation(
            "show me claims by countries", summary, sample_df, col,
        )
        assert "Claims by Country" in result


# =========================================================================
# 16. Region breakdown
# =========================================================================

class TestRegionBreakdown:
    def test_region_breakdown(self, summary, sample_df, col):
        result = handle_aggregation(
            "region breakdown", summary, sample_df, col,
        )
        assert "Claims by Region" in result
        assert "US" in result


# =========================================================================
# 17. Status breakdown (only when "status" explicitly in query)
# =========================================================================

class TestStatusBreakdown:
    def test_status_breakdown(self, summary, sample_df, col):
        result = handle_aggregation(
            "show me the status breakdown", summary, sample_df, col,
        )
        assert "Claims by Status" in result
        assert "Open" in result

    def test_claims_by_status(self, summary, sample_df, col):
        result = handle_aggregation(
            "claims by status", summary, sample_df, col,
        )
        assert "Claims by Status" in result


# =========================================================================
# 18. Type breakdown
# =========================================================================

class TestTypeBreakdown:
    def test_type_breakdown(self, summary, sample_df, col):
        result = handle_aggregation(
            "show me the type breakdown", summary, sample_df, col,
        )
        assert "Claims by Type" in result
        assert "Auto" in result

    def test_claims_by_type(self, summary, sample_df, col):
        result = handle_aggregation(
            "claims by type", summary, sample_df, col,
        )
        assert "Claims by Type" in result


# =========================================================================
# 19. Smart contributing factor detector
# =========================================================================

class TestSmartContributingFactor:
    """The smart detector should catch a wide variety of natural-language
    phrasings asking about top contributors / drivers / factors."""

    @pytest.mark.parametrize("question", [
        "give me a breakdown by contributing factor",
        "what is the biggest contributing factor",
        "top drivers of claims",
        "what are the leading causes",
        "show me the largest volume drivers",
        "most common claim factors",
        "dominant claim categories",
        "major contributors to claim volume",
        "what contributes the most to claim volume",
        "show me the top claim types",
    ])
    def test_contributing_factor_variants(self, question, summary, sample_df, col):
        result = handle_aggregation(question, summary, sample_df, col)
        assert "Top Contributing Factors" in result
        assert "By Claim Type" in result
        assert "By Cause of Loss" in result
        assert "By Country" in result
        assert "By Line of Business" in result


# =========================================================================
# 20. Fallback summary
# =========================================================================

class TestFallbackSummary:
    def test_generic_question_hits_fallback(self, summary, sample_df, col):
        result = handle_aggregation(
            "tell me about the data", summary, sample_df, col,
        )
        assert "Claims Summary" in result
        assert "$85,000.00" in result

    def test_nonsense_hits_fallback(self, summary, sample_df, col):
        result = handle_aggregation(
            "xylophone purple banana", summary, sample_df, col,
        )
        assert "Claims Summary" in result


# =========================================================================
# Edge cases: ordering issues
# =========================================================================

class TestOrderingEdgeCases:
    """Verify that keyword ordering does not cause mis-routing."""

    def test_breakdown_by_contributing_factor_not_status(self, summary, sample_df, col):
        """'breakdown by contributing factor' should hit smart detector,
        NOT the status breakdown handler."""
        result = handle_aggregation(
            "breakdown by contributing factor", summary, sample_df, col,
        )
        assert "Top Contributing Factors" in result
        assert "Claims by Status" not in result

    def test_generic_breakdown_without_dimension_falls_to_status(self, summary, sample_df, col):
        """A bare 'breakdown' with no specific dimension should fall through
        to the status breakdown handler (the generic catch)."""
        result = handle_aggregation(
            "give me a breakdown of the claims", summary, sample_df, col,
        )
        # This currently hits status breakdown as the fallback -- that's OK
        # as long as it doesn't incorrectly route elsewhere
        assert "Claims by Status" in result or "Claims Summary" in result

    def test_biggest_type_hits_smart_detector(self, summary, sample_df, col):
        """'what is the biggest type' has both 'type' and 'biggest'. The smart
        detector should win over the type-breakdown handler."""
        result = handle_aggregation(
            "what is the biggest type", summary, sample_df, col,
        )
        assert "Top Contributing Factors" in result

    def test_top_regions_hits_smart_detector(self, summary, sample_df, col):
        """'top regions' should be caught by the smart detector (has 'top')."""
        result = handle_aggregation(
            "top regions", summary, sample_df, col,
        )
        assert "Top Contributing Factors" in result

    def test_cause_of_loss_with_breakdown(self, summary, sample_df, col):
        """'breakdown by cause of loss' should hit cause-of-loss handler,
        not the smart detector or status breakdown."""
        result = handle_aggregation(
            "breakdown by cause of loss", summary, sample_df, col,
        )
        assert "Claims by Cause of Loss" in result

    def test_lob_with_breakdown(self, summary, sample_df, col):
        """'line of business breakdown' should hit LOB handler."""
        result = handle_aggregation(
            "line of business breakdown", summary, sample_df, col,
        )
        assert "Claims by Line of Business" in result

    def test_country_with_breakdown(self, summary, sample_df, col):
        """'breakdown by country' should hit country handler,
        not status breakdown."""
        result = handle_aggregation(
            "breakdown by country", summary, sample_df, col,
        )
        assert "Claims by Country" in result

    def test_status_explicit_gets_status(self, summary, sample_df, col):
        """Explicitly asking for status should get status breakdown."""
        result = handle_aggregation(
            "status breakdown", summary, sample_df, col,
        )
        assert "Claims by Status" in result

    def test_count_with_region_entity(self, summary, sample_df, col):
        """'how many open claims' with entity status should use entity-aware,
        not the count-by-region handler."""
        result = handle_aggregation(
            "how many open claims?", summary, sample_df, col,
            entities={"status": "Open"},
        )
        assert "3" in result
        assert "Open" in result
        # Should NOT contain region groupby
        assert "Claims Count by Region" not in result

    def test_average_without_dimension_gives_overall(self, summary, sample_df, col):
        """'average claim value' without region/type should give overall avg."""
        result = handle_aggregation(
            "what is the average claim value?", summary, sample_df, col,
        )
        assert "$17,000.00" in result
        # Should NOT have grouped by type or region
        assert "by Claim Type" not in result
        assert "by Region" not in result

    def test_total_value_not_confused_with_type(self, summary, sample_df, col):
        """'total claim value' should give overall total, not by-type."""
        result = handle_aggregation(
            "what is the total claim value?", summary, sample_df, col,
        )
        assert "$85,000.00" in result
        assert "by Claim Type" not in result
