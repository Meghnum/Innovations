"""Tests for ai.query_analyzer — intent classification & entity extraction."""

import json
from unittest.mock import patch, MagicMock

import pytest

from ai.query_analyzer import QueryAnalyzer


@pytest.fixture
def analyzer():
    return QueryAnalyzer()


# ── keyword-fallback intent tests ──────────────────────────────────────────

def test_fallback_aggregation_how_many(analyzer):
    result = analyzer._keyword_fallback("How many open claims are there?")
    assert result["intent"] == "aggregation"


def test_fallback_aggregation_total(analyzer):
    result = analyzer._keyword_fallback("What is the total incurred amount?")
    assert result["intent"] == "aggregation"


def test_fallback_lookup_clm_id(analyzer):
    result = analyzer._keyword_fallback("Show me details for CLM12345")
    assert result["intent"] == "lookup"
    assert result["claim_id"] == "CLM12345"


def test_fallback_search_default(analyzer):
    """Questions mentioning a region but no special keywords default to search."""
    result = analyzer._keyword_fallback("Tell me about claims in US")
    assert result["intent"] == "search"
    assert result["region"] == "US"


def test_fallback_high_value_flag(analyzer):
    result = analyzer._keyword_fallback("Show high value claims in UK")
    assert result["high_value"] is True
    assert result["region"] == "UK"


# ── _validate tests ───────────────────────────────────────────────────────

def test_validate_unknown_intent_defaults_to_search(analyzer):
    parsed = {"intent": "banana", "status": None}
    validated = analyzer._validate(parsed)
    assert validated["intent"] == "search"


def test_validate_fills_missing_keys(analyzer):
    validated = analyzer._validate({})
    for key in ("intent", "claim_id", "status", "region", "claim_type",
                "date_range", "high_value"):
        assert key in validated


# ── analyze orchestration ─────────────────────────────────────────────────

def test_analyze_falls_back_on_llm_error(analyzer):
    with patch.object(analyzer, "_llm_analyze", side_effect=Exception("timeout")):
        result = analyzer.analyze("How many open claims?")
    assert result["intent"] == "aggregation"


# ── LLM path tests (mocked ollama) ───────────────────────────────────────

def test_llm_analyze_parses_valid_json(analyzer):
    payload = {
        "intent": "aggregation",
        "claim_id": None,
        "status": "Open",
        "region": None,
        "claim_type": None,
        "date_range": None,
        "high_value": False,
    }
    mock_response = {"message": {"content": json.dumps(payload)}}

    with patch("ai.query_analyzer.ollama") as mock_ollama:
        mock_ollama.chat.return_value = mock_response
        result = analyzer._llm_analyze("How many open claims?")

    assert result["intent"] == "aggregation"
    assert result["status"] == "Open"


def test_llm_analyze_handles_markdown_wrapped_json(analyzer):
    payload = {
        "intent": "lookup",
        "claim_id": "CLM99999",
        "status": None,
        "region": None,
        "claim_type": None,
        "date_range": None,
        "high_value": False,
    }
    wrapped = f"```json\n{json.dumps(payload)}\n```"
    mock_response = {"message": {"content": wrapped}}

    with patch("ai.query_analyzer.ollama") as mock_ollama:
        mock_ollama.chat.return_value = mock_response
        result = analyzer._llm_analyze("Details on CLM99999")

    assert result["intent"] == "lookup"
    assert result["claim_id"] == "CLM99999"
