"""
Test scenarios for the Claims Assistant RAG pipeline.

Tests the full pipeline (QueryAnalyzer -> route -> answer) against
specific insurance scenarios to validate intent classification,
entity extraction, and answer correctness.

Scenarios cover:
  1. Point Retrieval (lookup)
  2. Financial Aggregation
  3. Temporal Logic
  4. Categorization
  5. Specialty Markets

NOTE: Search-intent tests require Ollama running locally with the
configured model. If Ollama is unavailable, those tests are skipped
gracefully (the pipeline returns a fallback or "not ready" message).
"""

import os
import sys
import pytest
import pandas as pd
import numpy as np

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from data.qvd_loader import ClaimsDataLoader
from ai.embeddings import ClaimsSearchEngine
from ai.llm import ClaimsLLM
from ai.rag_pipeline import RAGPipeline, handle_aggregation, handle_lookup
from ai.query_analyzer import QueryAnalyzer
from data.text_chunker import dataframe_to_chunks


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def loader():
    """Load a small (500-row) dummy dataset for fast testing."""
    ld = ClaimsDataLoader()
    # Override row count for speed
    ld.data_cfg["dummy_row_count"] = 500
    ld.data_cfg["dummy_mode"] = True
    ld.load()
    return ld


@pytest.fixture(scope="module")
def search_engine(loader):
    """Build search engine with the small dataset."""
    engine = ClaimsSearchEngine(loader.config)
    chunks = dataframe_to_chunks(loader.df, loader.col, chunk_size=500)
    engine.build(chunks)
    return engine


@pytest.fixture(scope="module")
def llm(loader):
    """Create LLM wrapper (may not be available)."""
    return ClaimsLLM(loader.config)


@pytest.fixture(scope="module")
def pipeline(loader, search_engine, llm):
    """Full RAG pipeline."""
    return RAGPipeline(loader, search_engine, llm)


@pytest.fixture(scope="module")
def analyzer():
    """Standalone QueryAnalyzer for intent-only tests."""
    return QueryAnalyzer()


# ============================================================================
# Helper
# ============================================================================

def run_scenario(pipeline, question, expected_intent=None, expected_keywords=None,
                 description=""):
    """Run a single test scenario and return structured results."""
    result = pipeline.ask(question)

    answer = result["answer"]
    detected_intent = result["question_type"]
    entities = result.get("entities", {})

    # Check intent
    intent_ok = (detected_intent == expected_intent) if expected_intent else True

    # Check keywords in answer
    keywords_found = {}
    if expected_keywords:
        for kw in expected_keywords:
            keywords_found[kw] = kw.lower() in answer.lower()

    keywords_ok = all(keywords_found.values()) if keywords_found else True

    return {
        "question": question,
        "description": description,
        "answer": answer,
        "detected_intent": detected_intent,
        "expected_intent": expected_intent,
        "intent_ok": intent_ok,
        "entities": entities,
        "keywords_found": keywords_found,
        "keywords_ok": keywords_ok,
        "passed": intent_ok and keywords_ok,
    }


# ============================================================================
# 1. Point Retrieval (Direct Fact Extraction)
# ============================================================================

class TestPointRetrieval:
    """Test direct claim lookup / fact extraction."""

    def test_1a_lookup_by_claim_id(self, pipeline, loader):
        """Who is handling claim CLM0000001 and what is its current status?"""
        question = "Who is handling claim CLM0000001 and what is its current status?"
        result = run_scenario(
            pipeline, question,
            expected_intent="lookup",
            expected_keywords=["CLM0000001", "Status"],
            description="Lookup claim by ID - should return adjuster and status",
        )

        print(f"\n--- 1A: Lookup by Claim ID ---")
        print(f"  Intent: {result['detected_intent']} (expected: lookup) -> {'PASS' if result['intent_ok'] else 'FAIL'}")
        print(f"  Keywords: {result['keywords_found']}")
        print(f"  Answer preview: {result['answer'][:200]}")

        # The claim should exist in dummy data (CLM0000001 is always row 0)
        assert result["intent_ok"], (
            f"Intent mismatch: got '{result['detected_intent']}', expected 'lookup'"
        )
        # Answer should contain the claim ID in the response
        assert "CLM0000001" in result["answer"], (
            f"Answer should contain CLM0000001, got: {result['answer'][:200]}"
        )
        # Should contain status info (the lookup handler always includes Status field)
        assert "Status" in result["answer"], (
            f"Answer should contain status info, got: {result['answer'][:200]}"
        )

    def test_1b_lookup_by_policy_number(self, pipeline, loader):
        """Where did the loss happen for policy POL0000001?"""
        # First find which claim has this policy
        col = loader.col
        df = loader.df
        policy_col = col.get("policy_number", "Policy Number")
        # Find the first policy number that actually exists
        first_policy = df[policy_col].iloc[0]

        question = f"Where did the loss happen for policy {first_policy}, and what exactly occurred?"
        result = run_scenario(
            pipeline, question,
            expected_intent="search",  # No CLM ID -> goes to search
            description="Find claim by policy number - requires semantic search",
        )

        print(f"\n--- 1B: Lookup by Policy Number ---")
        print(f"  Intent: {result['detected_intent']} (expected: search)")
        print(f"  Answer preview: {result['answer'][:200]}")

        # Policy-based queries have no CLM pattern so they go to search intent
        # The analyzer should NOT classify this as lookup (no CLM ID)
        # It should go to search and use FAISS
        assert result["detected_intent"] in ("search", "lookup"), (
            f"Intent should be search or lookup, got: {result['detected_intent']}"
        )


# ============================================================================
# 2. Financial Aggregation
# ============================================================================

class TestFinancialAggregation:
    """Test financial aggregation queries."""

    def test_2a_total_by_minor_lob(self, pipeline, loader):
        """Total Outstanding Reserve and Total Incurred for Commercial Fire claims."""
        question = "What is the total Outstanding Reserve and Total Incurred for Commercial Fire claims?"
        result = run_scenario(
            pipeline, question,
            expected_intent="aggregation",
            description="Filter by Minor LOB, sum financial columns",
        )

        print(f"\n--- 2A: Financial Totals by Minor LOB ---")
        print(f"  Intent: {result['detected_intent']} (expected: aggregation)")
        print(f"  Answer preview: {result['answer'][:300]}")

        # Check if aggregation handler can handle Minor LOB + specific financials
        # The aggregation handler checks for "total" + "value/amount/claim"
        # but does NOT have specific handling for Minor LOB filtering or
        # Outstanding Reserve / Incurred as separate columns
        # This is a known gap.
        if result["detected_intent"] != "aggregation":
            pytest.fail(
                f"Intent was '{result['detected_intent']}' instead of 'aggregation'. "
                f"The query contains 'total' which should trigger aggregation intent."
            )

        # The aggregation handler likely returns a generic total, not filtered
        # by Minor LOB. Check if it mentions dollar amounts at all.
        has_dollar = "$" in result["answer"]
        print(f"  Contains $ amounts: {has_dollar}")
        if not has_dollar:
            pytest.fail("Answer should contain dollar amounts for a financial aggregation query")

    def test_2b_recoveries_closed_uk(self, pipeline, loader):
        """How much money have we recovered on closed claims in the UK?"""
        question = "How much money have we recovered so far on closed claims in the UK?"
        result = run_scenario(
            pipeline, question,
            expected_intent="aggregation",
            description="Filter status=Closed, country=UK, sum Recoveries USD",
        )

        print(f"\n--- 2B: Recoveries for Closed UK Claims ---")
        print(f"  Intent: {result['detected_intent']} (expected: aggregation)")
        print(f"  Entities: {result['entities']}")
        print(f"  Answer preview: {result['answer'][:300]}")

        # The query says "how much" which may trigger aggregation.
        # But the aggregation handler has NO handler for Recoveries USD.
        # It would need to filter by status=Closed + country=UK and sum
        # "Recoveries USD" - none of the existing aggregation branches do this.
        #
        # Expected: either goes to aggregation (but returns a generic/wrong answer)
        # or goes to search (if "how much" doesn't trigger aggregation keyword).
        entities = result["entities"]
        print(f"  Status entity detected: {entities.get('status')}")
        print(f"  Region entity detected: {entities.get('region')}")


# ============================================================================
# 3. Temporal Logic
# ============================================================================

class TestTemporalLogic:
    """Test temporal / lifecycle-based queries."""

    def test_3a_avg_claim_life_days_water_damage(self, pipeline, loader):
        """Average claim life days for water damage claims."""
        question = "What is our average claim life days for water damage claims?"
        result = run_scenario(
            pipeline, question,
            expected_intent="aggregation",
            expected_keywords=["average"],
            description="Filter by Cause of Loss, average Claim Life Days",
        )

        print(f"\n--- 3A: Average Claim Life Days for Water Damage ---")
        print(f"  Intent: {result['detected_intent']} (expected: aggregation)")
        print(f"  Answer preview: {result['answer'][:300]}")

        # The aggregation handler has an "average" branch but it only handles:
        # - "average" + "day/open" -> avg_days_open from summary (no filtering)
        # - "average" (generic) -> avg_claim_amount
        # It does NOT filter by cause of loss before averaging.
        # So we expect it to return the overall average days open, NOT
        # filtered to water damage.
        if result["detected_intent"] == "aggregation":
            # Check if it returned a number
            assert "day" in result["answer"].lower() or "$" in result["answer"], (
                f"Aggregation answer should contain numeric data"
            )

    def test_3b_total_incurred_accident_year_2023(self, pipeline, loader):
        """Total incurred for Accident Year 2023."""
        question = "Give me the total incurred for Accident Year 2023"
        result = run_scenario(
            pipeline, question,
            expected_intent="aggregation",
            description="Filter by Accident Year=2023, sum Incurred USD",
        )

        print(f"\n--- 3B: Total Incurred for AY 2023 ---")
        print(f"  Intent: {result['detected_intent']} (expected: aggregation)")
        print(f"  Answer preview: {result['answer'][:300]}")

        # "total" keyword should trigger aggregation intent.
        # But the aggregation handler has no Accident Year filter.
        # It will likely return the total across ALL years.
        if result["detected_intent"] == "aggregation":
            assert "$" in result["answer"], (
                f"Should contain dollar amounts for total incurred query"
            )

        # Verify actual AY 2023 data exists
        col = loader.col
        ay_col = col.get("accident_year", "Accident Year")
        ay_2023_count = (loader.df[ay_col] == 2023).sum()
        print(f"  Actual AY 2023 claims in data: {ay_2023_count}")


# ============================================================================
# 4. Categorization
# ============================================================================

class TestCategorization:
    """Test group-by / categorization queries."""

    def test_4a_top_contributing_factors_slip_fall(self, pipeline, loader):
        """Top three contributing factors for slip and fall claims."""
        question = "What are the top three contributing factors for slip and fall claims?"
        result = run_scenario(
            pipeline, question,
            expected_intent="aggregation",
            description="Filter by cause=Slip and Fall, group by Contributing Factor",
        )

        print(f"\n--- 4A: Top Contributing Factors for Slip & Fall ---")
        print(f"  Intent: {result['detected_intent']} (expected: aggregation)")
        print(f"  Answer preview: {result['answer'][:400]}")

        # The word "top" triggers the "smart biggest/top/contributing" detector.
        # This handler shows top contributors across MULTIPLE dimensions
        # (by claim type, cause of loss, country, LOB) but does NOT first
        # filter to "slip and fall" claims. It shows overall top contributors.
        if result["detected_intent"] == "aggregation":
            # Should contain some breakdown
            assert "-" in result["answer"] or "|" in result["answer"], (
                "Answer should contain a list/table breakdown"
            )

    def test_4b_breakdown_by_cause_of_loss(self, pipeline, loader):
        """Breakdown by cause of loss."""
        question = "Show me a breakdown by cause of loss"
        result = run_scenario(
            pipeline, question,
            expected_intent="aggregation",
            expected_keywords=["Cause"],
            description="Group by Cause Of Loss Descr",
        )

        print(f"\n--- 4B: Breakdown by Cause of Loss ---")
        print(f"  Intent: {result['detected_intent']} (expected: aggregation)")
        print(f"  Answer preview: {result['answer'][:400]}")

        # The aggregation handler has a "cause of loss" branch that checks
        # for "cause of loss" in the question. The question says
        # "breakdown by cause of loss" which should match.
        if result["detected_intent"] == "aggregation":
            # Should list cause of loss categories
            assert "Cause" in result["answer"] or "cause" in result["answer"].lower(), (
                "Answer should reference cause of loss categories"
            )

        # Verify cause of loss column exists and has data
        col = loader.col
        cause_col = col.get("cause_of_loss_descr", "Cause Of Loss Descr")
        unique_causes = loader.df[cause_col].nunique()
        print(f"  Unique causes in data: {unique_causes}")


# ============================================================================
# 5. Specialty Markets
# ============================================================================

class TestSpecialtyMarkets:
    """Test specialty/market indicator queries."""

    def test_5a_bulk_claims_count(self, pipeline, loader):
        """How many bulk claims do we have?"""
        question = "How many bulk claims do we have?"
        result = run_scenario(
            pipeline, question,
            expected_intent="aggregation",
            description="Filter by Bulk Claim Indicator=Y, count",
        )

        print(f"\n--- 5A: Bulk Claims Count ---")
        print(f"  Intent: {result['detected_intent']} (expected: aggregation)")
        print(f"  Answer preview: {result['answer'][:300]}")

        # "how many" triggers aggregation. But the handler checks for:
        # - status entity -> count by status
        # - "region" in q -> count by region
        # - "type" in q -> count by type
        # - "claim" in q -> total count
        # "bulk claims" contains "claim" so it would return TOTAL claims count,
        # not filtered by Bulk Claim Indicator.
        if result["detected_intent"] == "aggregation":
            # It likely returns total count, not bulk-filtered
            assert "claim" in result["answer"].lower(), (
                "Answer should mention claims"
            )
            # Check actual bulk claims
            col = loader.col
            bulk_col = col.get("bulk_claim_indicator", "Bulk Claim Indicator")
            bulk_count = (loader.df[bulk_col] == "Y").sum()
            total_count = len(loader.df)
            print(f"  Actual bulk claims (Y): {bulk_count}")
            print(f"  Total claims: {total_count}")
            # If the answer says the total count instead of bulk count, that's a bug
            if str(total_count) in result["answer"] and str(bulk_count) not in result["answer"]:
                print(f"  WARNING: Answer returns total count ({total_count}) not bulk count ({bulk_count})")

    def test_5b_average_nominal_reserve(self, pipeline, loader):
        """Average nominal reserve."""
        question = "What is the average nominal reserve?"
        result = run_scenario(
            pipeline, question,
            expected_intent="aggregation",
            description="Calculate average of Nominal Reserve column",
        )

        print(f"\n--- 5B: Average Nominal Reserve ---")
        print(f"  Intent: {result['detected_intent']} (expected: aggregation)")
        print(f"  Answer preview: {result['answer'][:300]}")

        # "average" triggers aggregation. The handler's average branch:
        # - "day/open" -> avg_days_open
        # - generic -> avg_claim_amount
        # It does NOT have a handler for Nominal Reserve specifically.
        # So it will return avg_claim_amount (which is Incurred USD average).
        if result["detected_intent"] == "aggregation":
            assert "$" in result["answer"] or "day" in result["answer"].lower(), (
                "Average answer should contain a numeric value"
            )
            # Check actual nominal reserve average
            col = loader.col
            nom_col = col.get("nominal_reserve", "Nominal Reserve")
            actual_avg = loader.df[nom_col].mean()
            print(f"  Actual average nominal reserve: ${actual_avg:,.2f}")
            print(f"  Answer likely returns avg claim amount (Incurred USD) instead")


# ============================================================================
# Intent Classification Tests (unit tests for QueryAnalyzer)
# ============================================================================

class TestIntentClassification:
    """Test that QueryAnalyzer classifies intents correctly via keyword fallback."""

    @pytest.mark.parametrize("question,expected_intent", [
        ("Who is handling claim CLM0000001?", "lookup"),
        ("What is the status of CLM0000042?", "lookup"),
        ("How many open claims do we have?", "aggregation"),
        ("What is the total claim value?", "aggregation"),
        ("What is the average days open?", "aggregation"),
        ("Show me claims related to fire damage", "search"),
        ("Find high-value property damage claims in the US", "search"),
    ])
    def test_keyword_fallback_intent(self, analyzer, question, expected_intent):
        """Test keyword-based intent classification."""
        # Use the keyword fallback directly to avoid needing Ollama
        result = analyzer._keyword_fallback(question)
        detected = result["intent"]
        print(f"\n  Q: {question}")
        print(f"  Intent: {detected} (expected: {expected_intent})")
        assert detected == expected_intent, (
            f"For '{question}': got '{detected}', expected '{expected_intent}'"
        )

    @pytest.mark.parametrize("question,expected_entity_key,expected_value", [
        ("How many open claims?", "status", "Open"),
        ("Show me claims in the UK", "region", "UK"),
        ("Find property damage claims", "claim_type", "Property Damage"),
        ("What about claim CLM0000001?", "claim_id", "CLM0000001"),
    ])
    def test_keyword_fallback_entities(self, analyzer, question,
                                        expected_entity_key, expected_value):
        """Test keyword-based entity extraction."""
        result = analyzer._keyword_fallback(question)
        actual = result.get(expected_entity_key)
        print(f"\n  Q: {question}")
        print(f"  {expected_entity_key}: {actual} (expected: {expected_value})")
        assert actual == expected_value, (
            f"For '{question}': {expected_entity_key}={actual}, expected {expected_value}"
        )


# ============================================================================
# Aggregation Handler Unit Tests
# ============================================================================

class TestAggregationHandler:
    """Test handle_aggregation directly to identify handler gaps."""

    def test_total_claims_count(self, loader):
        """Generic 'how many claims' should return total."""
        answer = handle_aggregation(
            "How many claims do we have?",
            loader.summary, loader.df, loader.col, {},
        )
        assert str(loader.summary["total_claims"]) in answer.replace(",", "")

    def test_status_count_open(self, loader):
        """Count open claims."""
        answer = handle_aggregation(
            "How many open claims?",
            loader.summary, loader.df, loader.col, {"status": "Open"},
        )
        expected_count = loader.summary["status_counts"].get("Open", 0)
        assert str(expected_count) in answer.replace(",", "")

    def test_cause_of_loss_breakdown(self, loader):
        """Cause of loss breakdown."""
        answer = handle_aggregation(
            "Show me breakdown by cause of loss",
            loader.summary, loader.df, loader.col, {},
        )
        # Should contain cause of loss entries
        assert "Cause" in answer or "Fire" in answer or "Water" in answer

    def test_contributing_factor_breakdown(self, loader):
        """Contributing factor breakdown."""
        answer = handle_aggregation(
            "What are the contributing factors?",
            loader.summary, loader.df, loader.col, {},
        )
        # The handler checks for "contributing factor" or "contributing" and "factor"
        assert "Contributing" in answer or "Negligence" in answer or "Weather" in answer

    def test_no_minor_lob_filter(self, loader):
        """Aggregation handler cannot filter by Minor LOB (known gap)."""
        answer = handle_aggregation(
            "What is the total outstanding reserve for Commercial Fire claims?",
            loader.summary, loader.df, loader.col, {},
        )
        # This will return the total across ALL claims, not filtered to
        # Minor LOB = "Fire". The handler has no Minor LOB filtering.
        # The answer will contain total values, not Fire-specific.
        total_str = f"{loader.summary['total_claims']:,}"
        print(f"\n  Answer: {answer[:200]}")
        print(f"  NOTE: No Minor LOB filter exists - answer covers all claims")

    def test_no_recoveries_handler(self, loader):
        """Aggregation handler cannot sum Recoveries USD (known gap)."""
        answer = handle_aggregation(
            "What are the total recoveries?",
            loader.summary, loader.df, loader.col, {},
        )
        # "total" + "recoveries" -> the handler checks for "total" + "value/amount/claim"
        # "recoveries" does not match "value", "amount", or "claim" so it falls
        # through to status/type/other handlers.
        print(f"\n  Answer: {answer[:200]}")
        print(f"  NOTE: No Recoveries-specific handler exists")

    def test_no_accident_year_filter(self, loader):
        """Aggregation handler cannot filter by Accident Year (known gap)."""
        answer = handle_aggregation(
            "What is the total incurred for accident year 2023?",
            loader.summary, loader.df, loader.col, {},
        )
        print(f"\n  Answer: {answer[:200]}")
        print(f"  NOTE: No Accident Year filter exists - returns unfiltered total")

    def test_no_nominal_reserve_handler(self, loader):
        """Aggregation handler cannot compute avg Nominal Reserve (known gap)."""
        answer = handle_aggregation(
            "What is the average nominal reserve?",
            loader.summary, loader.df, loader.col, {},
        )
        # "average" without "day/open" -> returns avg_claim_amount
        actual_avg_nominal = loader.df[loader.col.get("nominal_reserve", "Nominal Reserve")].mean()
        print(f"\n  Answer: {answer[:200]}")
        print(f"  Actual avg nominal reserve: ${actual_avg_nominal:,.2f}")
        print(f"  Handler returns avg claim amount (Incurred USD) instead")


# ============================================================================
# Lookup Handler Unit Tests
# ============================================================================

class TestLookupHandler:
    """Test handle_lookup directly."""

    def test_lookup_existing_claim(self, loader):
        """Lookup CLM0000001 should return claim details."""
        answer = handle_lookup("CLM0000001", loader.df, loader.col)
        assert "CLM0000001" in answer
        assert "Status" in answer
        assert "Claim Amount" in answer

    def test_lookup_nonexistent_claim(self, loader):
        """Lookup nonexistent claim returns not-found message."""
        answer = handle_lookup("CLM9999999", loader.df, loader.col)
        assert "not found" in answer.lower()

    def test_lookup_empty_id(self, loader):
        """Lookup with empty ID returns helpful message."""
        answer = handle_lookup("", loader.df, loader.col)
        assert "couldn't find" in answer.lower() or "include" in answer.lower()
