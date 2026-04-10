# Claims Assistant — Full Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the Claims Assistant's reasoning accuracy, reliability, and UI by replacing keyword routing with LLM-based intent extraction, adding FAISS pre-filtering, robust retry/fallback, a Professional Dark Streamlit UI with inline Plotly charts, and richer Teams Adaptive Cards.

**Architecture:** QueryAnalyzer extracts structured intent + entities from every question before routing. The RAG pipeline uses those entities to pre-filter the DataFrame before FAISS search, drops low-confidence results, and retries/falls back gracefully if the LLM is slow. The Streamlit UI is rebuilt from scratch in a dark theme with response-type-specific rendering (charts for aggregations, tables for lookups/search). The Teams bot maps response types to rich Adaptive Card templates.

**Tech Stack:** Python 3.8+, pandas, FAISS-CPU, sentence-transformers (all-MiniLM-L6-v2), Ollama (gemma3:4b), Streamlit, Plotly, botbuilder-core, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `requirements.txt` | Update | Add plotly |
| `config/config.yaml` | Update | Add 4 new AI keys |
| `ai/query_analyzer.py` | **Create** | LLM-based intent + entity extraction |
| `ai/embeddings.py` | Update | Add `search_with_filter()` method |
| `ai/llm.py` | Update | Rewrite `build_prompt()` with 4-block structure |
| `ai/rag_pipeline.py` | Rewrite | Integrate QueryAnalyzer, pre-filter, retry chain |
| `ui/streamlit_app.py` | Rewrite | Professional Dark UI with Plotly charts |
| `bot/adaptive_cards.py` | **Create** | Adaptive Card templates per response type |
| `bot/teams_bot.py` | Update | Map response types to Adaptive Cards |
| `notifications/teams_notify.py` | **Create** | Teams webhook alert sender |
| `notifications/rules_engine.py` | **Create** | Threshold-based trigger logic |
| `scheduler/refresh_scheduler.py` | **Create** | Scheduled refresh + daily summary |
| `tests/test_query_analyzer.py` | **Create** | QueryAnalyzer unit tests |
| `tests/test_embeddings.py` | **Create** | Filter search unit tests |
| `tests/test_llm.py` | **Create** | Prompt builder unit tests |
| `tests/test_rag_pipeline.py` | **Create** | Pipeline integration tests |

---

## Task 1: Config + Dependencies

**Files:**
- Modify: `requirements.txt`
- Modify: `config/config.yaml`

- [ ] **Step 1: Add plotly to requirements.txt**

Open `requirements.txt` and add this line in the AI & Embeddings section:

```
plotly>=5.0.0              # Inline charts in Streamlit + PNG export for Teams cards
```

- [ ] **Step 2: Add 4 new config keys to config.yaml**

In `config/config.yaml`, under the `ai:` block, add after `top_k_results`:

```yaml
  query_analyzer_timeout: 8      # seconds for QueryAnalyzer LLM call before fallback
  faiss_score_threshold: 0.35    # drop FAISS results below this cosine similarity
  llm_retry_count: 2             # LLM attempts before falling back to summary stats
  llm_timeout: 30                # seconds per LLM attempt
```

- [ ] **Step 3: Verify config loads cleanly**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
python -c "from data.qvd_loader import load_config; c = load_config('config/config.yaml'); print(c['ai'])"
```

Expected output includes all keys: `query_analyzer_timeout`, `faiss_score_threshold`, `llm_retry_count`, `llm_timeout`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt config/config.yaml
git commit -m "config: add plotly dependency and 4 new AI tuning keys"
```

---

## Task 2: QueryAnalyzer — LLM Intent + Entity Extraction

**Files:**
- Create: `ai/query_analyzer.py`
- Create: `tests/test_query_analyzer.py`

- [ ] **Step 1: Create tests/test_query_analyzer.py with failing tests**

```bash
mkdir -p /Users/meghnumnirwal/chatgpt-claims/tests
```

Create `tests/test_query_analyzer.py`:

```python
# tests/test_query_analyzer.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock, patch
from ai.query_analyzer import QueryAnalyzer

CONFIG = {
    "ai": {
        "ollama_model": "gemma3:4b",
        "ollama_host": "http://localhost:11434",
        "query_analyzer_timeout": 8,
    }
}


def make_analyzer():
    return QueryAnalyzer(CONFIG)


# ── Keyword fallback tests (no Ollama needed) ──────────────────────────────

def test_fallback_aggregation_how_many():
    qa = make_analyzer()
    result = qa._keyword_fallback("How many open claims are there?")
    assert result["intent"] == "aggregation"
    assert result["status"] == "Open"


def test_fallback_aggregation_total():
    qa = make_analyzer()
    result = qa._keyword_fallback("What is the total claim value?")
    assert result["intent"] == "aggregation"


def test_fallback_lookup_clm_id():
    qa = make_analyzer()
    result = qa._keyword_fallback("Tell me about claim CLM0000042")
    assert result["intent"] == "lookup"
    assert result["claim_id"] == "CLM0000042"


def test_fallback_search_default():
    qa = make_analyzer()
    result = qa._keyword_fallback("Show me medical claims in London")
    assert result["intent"] == "search"
    assert result["region"] == "London"
    assert result["claim_type"] == "Medical"


def test_fallback_high_value_flag():
    qa = make_analyzer()
    result = qa._keyword_fallback("Show high value motor claims")
    assert result["high_value"] is True


def test_validate_unknown_intent_defaults_to_search():
    qa = make_analyzer()
    result = qa._validate({"intent": "nonsense"})
    assert result["intent"] == "search"


def test_validate_fills_missing_keys():
    qa = make_analyzer()
    result = qa._validate({"intent": "aggregation"})
    assert "claim_id" in result
    assert "status" in result
    assert "region" in result
    assert result["claim_id"] is None


# ── analyze() falls back when LLM fails ───────────────────────────────────

def test_analyze_falls_back_on_llm_error():
    qa = make_analyzer()
    with patch.object(qa, "_llm_analyze", side_effect=Exception("connection refused")):
        result = qa.analyze("How many open claims?")
    assert result["intent"] == "aggregation"


# ── _llm_analyze parses clean JSON ────────────────────────────────────────

def test_llm_analyze_parses_valid_json():
    qa = make_analyzer()
    mock_response = MagicMock()
    mock_response.response = '{"intent":"aggregation","claim_id":null,"status":"Open","region":"London","claim_type":null,"date_from":null,"date_to":null,"high_value":false}'

    with patch("ai.query_analyzer.ollama") as mock_ollama:
        mock_client = MagicMock()
        mock_ollama.Client.return_value = mock_client
        mock_client.generate.return_value = mock_response
        result = qa._llm_analyze("How many open claims in London?")

    assert result["intent"] == "aggregation"
    assert result["status"] == "Open"
    assert result["region"] == "London"


def test_llm_analyze_handles_markdown_wrapped_json():
    qa = make_analyzer()
    mock_response = MagicMock()
    mock_response.response = '```json\n{"intent":"lookup","claim_id":"CLM0000001","status":null,"region":null,"claim_type":null,"date_from":null,"date_to":null,"high_value":false}\n```'

    with patch("ai.query_analyzer.ollama") as mock_ollama:
        mock_client = MagicMock()
        mock_ollama.Client.return_value = mock_client
        mock_client.generate.return_value = mock_response
        result = qa._llm_analyze("Tell me about CLM0000001")

    assert result["intent"] == "lookup"
    assert result["claim_id"] == "CLM0000001"
```

- [ ] **Step 2: Run tests — verify they all fail with ImportError**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
python -m pytest tests/test_query_analyzer.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'ai.query_analyzer'`

- [ ] **Step 3: Create ai/query_analyzer.py**

```python
# =============================================================================
# ai/query_analyzer.py
# Phase 2 Overhaul: LLM-based intent + entity extraction
# =============================================================================
# Replaces keyword-based detect_question_type() with a structured LLM call.
# Returns a dict with intent, claim_id, status, region, claim_type, date range.
# Falls back to keyword matching if the LLM is unavailable or returns bad JSON.
# =============================================================================

import json
import logging
import re
from typing import Optional

logger = logging.getLogger("claims.query_analyzer")

ANALYSIS_PROMPT = """Analyze this insurance claims question and return ONLY a JSON object.

Question: {question}

Return this exact JSON structure (use null for unknown fields):
{{
  "intent": "aggregation or lookup or search or trend or comparison",
  "claim_id": "CLM0000042 or null",
  "status": "Open or Closed or Pending or Rejected or Under Review or null",
  "region": "London or North West or South East or Midlands or Scotland or Wales or null",
  "claim_type": "Medical or Motor or Property or Liability or Life or Travel or null",
  "date_from": "YYYY-MM-DD or null",
  "date_to": "YYYY-MM-DD or null",
  "high_value": true or false
}}

Intent definitions:
- aggregation: counts, totals, averages, percentages, breakdowns by group
- lookup: finding a specific claim by its ID (e.g. CLM0000042)
- search: finding claims that match criteria without a specific ID
- trend: patterns or changes over time periods
- comparison: comparing metrics across regions, types, or time periods

Return ONLY the JSON object. No explanation. No markdown.
"""

VALID_INTENTS = {"aggregation", "lookup", "search", "trend", "comparison"}
VALID_STATUSES = {"Open", "Closed", "Pending", "Rejected", "Under Review"}
VALID_REGIONS = {"London", "North West", "South East", "Midlands", "Scotland", "Wales"}
VALID_TYPES = {"Medical", "Motor", "Property", "Liability", "Life", "Travel"}

AGGREGATION_KEYWORDS = [
    "how many", "total", "count", "sum", "average", "avg",
    "breakdown", "split", "percentage", "percent", "%",
    "overall", "across all", "in total", "give me the number",
    "what is the", "how much",
]


class QueryAnalyzer:
    """
    Classifies a natural language question into structured intent + entities.

    Uses the local LLM for classification. Falls back to keyword matching
    if the LLM is unavailable, times out, or returns malformed output.

    Usage:
        analyzer = QueryAnalyzer(config)
        result = analyzer.analyze("How many open claims in London?")
        # result = {
        #   "intent": "aggregation",
        #   "claim_id": None,
        #   "status": "Open",
        #   "region": "London",
        #   "claim_type": None,
        #   "date_from": None,
        #   "date_to": None,
        #   "high_value": False,
        # }
    """

    def __init__(self, config: dict):
        """
        Args:
            config: Full loaded config dict from config.yaml
        """
        self.ai_cfg = config["ai"]
        self.model_name = self.ai_cfg["ollama_model"]
        self.host = self.ai_cfg["ollama_host"]
        self.timeout = self.ai_cfg.get("query_analyzer_timeout", 8)

    def analyze(self, question: str) -> dict:
        """
        Analyze a question and return structured intent + entity dict.

        Tries LLM-based analysis first. Falls back to keyword matching on failure.

        Args:
            question: Plain English question from the user.

        Returns:
            Dict with keys: intent, claim_id, status, region, claim_type,
            date_from, date_to, high_value.
        """
        try:
            result = self._llm_analyze(question)
            if result:
                logger.debug(f"QueryAnalyzer (LLM): {result}")
                return result
        except Exception as e:
            logger.warning(f"QueryAnalyzer LLM failed: {e} — using keyword fallback")

        result = self._keyword_fallback(question)
        logger.debug(f"QueryAnalyzer (fallback): {result}")
        return result

    def _llm_analyze(self, question: str) -> Optional[dict]:
        """
        Call the local LLM to classify the question.

        Returns:
            Validated dict or None if parsing fails.

        Raises:
            Exception: If Ollama is unreachable (triggers fallback in analyze()).
        """
        import ollama
        client = ollama.Client(host=self.host)
        prompt = ANALYSIS_PROMPT.format(question=question)

        response = client.generate(
            model=self.model_name,
            prompt=prompt,
            options={"temperature": 0.0, "num_predict": 200},
        )

        text = response.response.strip()

        # Strip markdown code fences if present
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    text = part
                    break

        try:
            parsed = json.loads(text)
            return self._validate(parsed)
        except json.JSONDecodeError:
            logger.warning(f"QueryAnalyzer: LLM returned non-JSON: {text[:100]}")
            return None

    def _validate(self, parsed: dict) -> dict:
        """
        Validate and normalise a parsed JSON dict from the LLM.

        Ensures all keys exist and values are within expected sets.
        Unknown values are reset to None rather than raising errors.

        Args:
            parsed: Raw dict from json.loads()

        Returns:
            Validated dict with all 8 required keys.
        """
        intent = parsed.get("intent", "search")
        if intent not in VALID_INTENTS:
            intent = "search"

        status = parsed.get("status")
        if status and status not in VALID_STATUSES:
            status = None

        region = parsed.get("region")
        if region and region not in VALID_REGIONS:
            region = None

        claim_type = parsed.get("claim_type")
        if claim_type and claim_type not in VALID_TYPES:
            claim_type = None

        return {
            "intent":     intent,
            "claim_id":   parsed.get("claim_id"),
            "status":     status,
            "region":     region,
            "claim_type": claim_type,
            "date_from":  parsed.get("date_from"),
            "date_to":    parsed.get("date_to"),
            "high_value": bool(parsed.get("high_value", False)),
        }

    def _keyword_fallback(self, question: str) -> dict:
        """
        Keyword-based classification — the original detect_question_type() logic,
        extended with entity extraction. Used when LLM is unavailable.

        Args:
            question: User's question string.

        Returns:
            Dict with all 8 required keys.
        """
        q = question.lower()

        # Intent
        intent = "search"
        if any(kw in q for kw in AGGREGATION_KEYWORDS):
            intent = "aggregation"
        elif re.search(r'\bclm\d+\b', q):
            intent = "lookup"

        # Claim ID
        claim_id_match = re.search(r'\bclm\d+\b', q, re.IGNORECASE)
        claim_id = claim_id_match.group(0).upper() if claim_id_match else None

        # Status
        status = None
        for s in ["Under Review", "Open", "Closed", "Pending", "Rejected"]:
            if s.lower() in q:
                status = s
                break

        # Region
        region = None
        for r in VALID_REGIONS:
            if r.lower() in q:
                region = r
                break

        # Claim type
        claim_type = None
        for t in VALID_TYPES:
            if t.lower() in q:
                claim_type = t
                break

        # High value flag
        high_value = "high value" in q or "high-value" in q or "large claim" in q

        return {
            "intent":     intent,
            "claim_id":   claim_id,
            "status":     status,
            "region":     region,
            "claim_type": claim_type,
            "date_from":  None,
            "date_to":    None,
            "high_value": high_value,
        }
```

- [ ] **Step 4: Run tests — all should pass**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
python -m pytest tests/test_query_analyzer.py -v
```

Expected: 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/query_analyzer.py tests/test_query_analyzer.py
git commit -m "feat: add QueryAnalyzer for LLM-based intent and entity extraction"
```

---

## Task 3: FAISS Filter Search Method

**Files:**
- Modify: `ai/embeddings.py` (add method to `ClaimsSearchEngine`)
- Create: `tests/test_embeddings.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_embeddings.py`:

```python
# tests/test_embeddings.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest
from ai.embeddings import ClaimsSearchEngine

CONFIG = {
    "ai": {
        "embedding_model": "all-MiniLM-L6-v2",
        "top_k_results": 3,
        "faiss_score_threshold": 0.35,
    }
}

SAMPLE_CHUNKS = [
    {"chunk_id": 0, "df_index": 0, "claim_id": "CLM0000001",
     "text": "Claim CLM0000001 is an Open Medical claim submitted in London with value £45,000."},
    {"chunk_id": 1, "df_index": 1, "claim_id": "CLM0000002",
     "text": "Claim CLM0000002 is a Closed Motor claim submitted in Scotland with value £12,000."},
    {"chunk_id": 2, "df_index": 2, "claim_id": "CLM0000003",
     "text": "Claim CLM0000003 is a Pending Property claim submitted in Wales with value £78,000."},
    {"chunk_id": 3, "df_index": 3, "claim_id": "CLM0000004",
     "text": "Claim CLM0000004 is an Open Medical claim submitted in London with value £120,000."},
    {"chunk_id": 4, "df_index": 4, "claim_id": "CLM0000005",
     "text": "Claim CLM0000005 is a Rejected Liability claim submitted in Midlands with value £5,500."},
]


@pytest.fixture(scope="module")
def engine():
    eng = ClaimsSearchEngine(CONFIG)
    eng.build(SAMPLE_CHUNKS)
    return eng


def test_engine_builds_successfully(engine):
    assert engine.is_ready
    assert engine.index.ntotal == 5


def test_regular_search_returns_results(engine):
    results = engine.search("medical claims in London")
    assert len(results) > 0
    assert all("score" in r for r in results)


def test_search_with_filter_restricts_to_allowed_indices(engine):
    # Only allow df_index 0 and 3 (both London Medical)
    allowed = {0, 3}
    results = engine.search_with_filter("medical claims London", allowed)
    returned_indices = {r["df_index"] for r in results}
    assert returned_indices.issubset(allowed), f"Got indices outside allowed set: {returned_indices}"


def test_search_with_filter_empty_allowed_set(engine):
    # No indices allowed — should return empty list gracefully
    results = engine.search_with_filter("anything", set())
    assert results == []


def test_search_with_filter_returns_scores(engine):
    allowed = {0, 1, 2, 3, 4}
    results = engine.search_with_filter("open medical claim", allowed)
    assert all("score" in r for r in results)
    # Scores should be in descending order
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
```

- [ ] **Step 2: Run tests — verify failures**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
python -m pytest tests/test_embeddings.py -v 2>&1 | head -20
```

Expected: `AttributeError: 'ClaimsSearchEngine' object has no attribute 'search_with_filter'`

- [ ] **Step 3: Add search_with_filter to ClaimsSearchEngine**

In `ai/embeddings.py`, add this method inside the `ClaimsSearchEngine` class, after the `search()` method (around line 270):

```python
    def search_with_filter(
        self,
        query: str,
        allowed_df_indices: set,
        top_k: int = None,
    ) -> list:
        """
        Search the FAISS index but only return results whose df_index
        is in the allowed_df_indices set.

        How it works:
          1. Search FAISS with top_k * 5 to get a wide candidate set
          2. Post-filter candidates to only those in allowed_df_indices
          3. Return up to top_k results in score order

        This avoids rebuilding the index per query — the full index is
        always searched, candidates are just filtered afterward.

        Args:
            query:              User's question string.
            allowed_df_indices: Set of df_index values (ints) to allow.
            top_k:              Max results to return (defaults to config value).

        Returns:
            List of chunk dicts with scores, filtered to allowed indices.
            Empty list if no allowed indices or index not built.
        """
        import faiss

        if not self._built:
            raise RuntimeError("Search engine not built. Call engine.build(chunks) first.")

        if not allowed_df_indices:
            return []

        top_k = top_k or self.ai_cfg["top_k_results"]
        # Search wider than needed so filtering still yields top_k results
        wide_k = min(top_k * 5, self.index.ntotal)

        query_vec = self.model.encode([query], convert_to_numpy=True).astype("float32")
        faiss.normalize_L2(query_vec)

        distances, indices = self.index.search(query_vec, wide_k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            chunk = self.chunks[idx]
            if chunk["df_index"] in allowed_df_indices:
                result = chunk.copy()
                result["score"] = round(float(dist), 4)
                results.append(result)
                if len(results) >= top_k:
                    break

        return results
```

- [ ] **Step 4: Run tests — all should pass**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
python -m pytest tests/test_embeddings.py -v
```

Expected: 5 tests PASS. (Note: first run downloads ~80MB embedding model if not cached.)

- [ ] **Step 5: Commit**

```bash
git add ai/embeddings.py tests/test_embeddings.py
git commit -m "feat: add search_with_filter to ClaimsSearchEngine for entity-filtered FAISS search"
```

---

## Task 4: Improved Prompt Engineering

**Files:**
- Modify: `ai/llm.py` (rewrite `build_prompt()`)
- Create: `tests/test_llm.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_llm.py`:

```python
# tests/test_llm.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from ai.llm import build_prompt

COL = {
    "claim_id": "ClaimID", "status": "Status", "claim_type": "ClaimType",
    "submitted_date": "SubmittedDate", "closed_date": "ClosedDate",
    "region": "Region", "claimant_name": "ClaimantName",
    "claim_amount": "ClaimAmount", "paid_amount": "PaidAmount",
    "reserve_amount": "ReserveAmount", "days_open": "DaysOpen",
}

SUMMARY = {
    "total_claims": 10000,
    "total_claim_amount": 48200000.0,
    "total_paid_amount": 19000000.0,
    "total_reserve_amount": 17000000.0,
    "avg_claim_amount": 4820.0,
    "avg_days_open": 87.3,
    "status_counts": {"Open": 3487, "Closed": 4012},
    "region_counts": {"London": 2100},
    "type_counts": {"Medical": 3000},
    "data_loaded_at": "2026-04-10 07:00:00",
    "date_range_start": "2024-04-10",
    "date_range_end": "2026-04-10",
}

CONTEXT_ROW = pd.DataFrame([{
    "ClaimID": "CLM0000001", "Status": "Open", "ClaimType": "Medical",
    "SubmittedDate": "2024-03-21", "ClosedDate": None,
    "Region": "London", "ClaimantName": "Sarah Jones",
    "ClaimAmount": 45000.0, "PaidAmount": 0.0,
    "ReserveAmount": 32000.0, "DaysOpen": 387,
}])


def test_prompt_contains_hard_rules():
    prompt = build_prompt("How many open claims?", pd.DataFrame(), COL, SUMMARY)
    assert "never break" in prompt.lower() or "must never" in prompt.lower()
    assert "Do not invent" in prompt or "Never invent" in prompt


def test_prompt_contains_chain_of_thought_instruction():
    prompt = build_prompt("Any question", pd.DataFrame(), COL, SUMMARY)
    assert "step" in prompt.lower()
    assert "reason" in prompt.lower() or "internally" in prompt.lower()


def test_prompt_contains_output_format_rules():
    prompt = build_prompt("Any question", pd.DataFrame(), COL, SUMMARY)
    assert "table" in prompt.lower()
    assert "bold" in prompt.lower() or "**" in prompt


def test_prompt_contains_summary_figures():
    prompt = build_prompt("Any question", pd.DataFrame(), COL, SUMMARY)
    assert "10,000" in prompt or "10000" in prompt
    assert "48,200,000" in prompt or "48200000" in prompt or "48.2" in prompt


def test_prompt_includes_context_rows_when_provided():
    prompt = build_prompt("Tell me about CLM0000001", CONTEXT_ROW, COL, SUMMARY)
    assert "CLM0000001" in prompt
    assert "Sarah Jones" in prompt
    assert "£45,000" in prompt


def test_prompt_says_no_data_when_context_empty():
    prompt = build_prompt("Find claims", pd.DataFrame(), COL, SUMMARY)
    assert "None found" in prompt or "no relevant" in prompt.lower()


def test_prompt_ends_with_answer_marker():
    prompt = build_prompt("Any question", pd.DataFrame(), COL, SUMMARY)
    assert prompt.strip().endswith("ANSWER:")
```

- [ ] **Step 2: Run tests — verify failures**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
python -m pytest tests/test_llm.py -v 2>&1 | head -30
```

Expected: Several tests FAIL (current prompt missing chain-of-thought, format rules, hard rules).

- [ ] **Step 3: Rewrite build_prompt() in ai/llm.py**

Replace the existing `build_prompt()` function (lines 83–172) with:

```python
def build_prompt(
    question: str,
    context_rows: pd.DataFrame,
    col: dict,
    summary: dict,
) -> str:
    """
    Build the 4-block prompt sent to the LLM.

    Block 1 — Role + hard rules (anti-hallucination)
    Block 2 — Chain-of-thought instruction (internal reasoning only)
    Block 3 — Structured context (summary stats + relevant rows)
    Block 4 — Output format rules

    Args:
        question:     The user's plain English question.
        context_rows: DataFrame rows returned by FAISS search (may be empty).
        col:          Column name mapping from config.
        summary:      Pre-computed summary stats dict.

    Returns:
        A formatted prompt string ending with "ANSWER:".
    """

    # ── Block 1: Role + Hard Rules ─────────────────────────────────────────
    block1 = """You are a Claims Data Analyst for an insurance company.

Rules you must never break:
- Only use numbers explicitly present in the data below. Never invent or estimate figures.
- If a Claim ID is mentioned in the retrieved rows, cite it in your answer.
- Format all currency as £ with comma separators (e.g. £45,000 not 45000).
- If the answer is not in the provided data, say exactly: "I don't have that information in the current dataset."
- Do not apologise or hedge. Give direct, factual, professional answers.
- Do not make up claim IDs, amounts, names, or dates."""

    # ── Block 2: Chain-of-thought instruction ─────────────────────────────
    block2 = """Before writing your answer, reason through these steps internally (do NOT output the reasoning):
1. What exactly is being asked?
2. Which rows or summary figures directly answer it?
3. What calculation or lookup is needed?
Then output ONLY the final answer."""

    # ── Block 3: Structured context ───────────────────────────────────────
    summary_block = f"""DATASET SUMMARY (as of {summary.get('data_loaded_at', 'unknown')}):
- Total claims: {summary.get('total_claims', 'N/A'):,}
- Total claim value: £{summary.get('total_claim_amount', 0):,.2f}
- Total paid: £{summary.get('total_paid_amount', 0):,.2f}
- Total reserves: £{summary.get('total_reserve_amount', 0):,.2f}
- Average claim value: £{summary.get('avg_claim_amount', 0):,.2f}
- Average days open: {summary.get('avg_days_open', 'N/A')} days
- Status breakdown: {summary.get('status_counts', {})}
- Region breakdown: {summary.get('region_counts', {})}
- Claim type breakdown: {summary.get('type_counts', {})}
- Date range: {summary.get('date_range_start', '')} to {summary.get('date_range_end', '')}"""

    if context_rows is not None and len(context_rows) > 0:
        context_lines = ["RELEVANT CLAIMS RETRIEVED:"]
        for _, row in context_rows.iterrows():
            def s(field):
                val = row.get(col.get(field, ""), "N/A")
                return "N/A" if pd.isna(val) else str(val)

            def c(field):
                try:
                    return f"£{float(row.get(col.get(field, ''), 0)):,.2f}"
                except Exception:
                    return "N/A"

            submitted_str = s("submitted_date")
            submitted_str = submitted_str[:10] if submitted_str != "N/A" else "N/A"
            closed_str = s("closed_date")
            closed_str = closed_str[:10] if closed_str != "N/A" else "Still open"

            line = (
                f"- Claim {s('claim_id')}: {s('status')} {s('claim_type')} | "
                f"Claimant: {s('claimant_name')} | Region: {s('region')} | "
                f"Submitted: {submitted_str} | Closed: {closed_str} | "
                f"Amount: {c('claim_amount')} | Paid: {c('paid_amount')} | "
                f"Reserve: {c('reserve_amount')} | Days open: {s('days_open')}"
            )
            context_lines.append(line)
        context_block = "\n".join(context_lines)
    else:
        context_block = "RELEVANT CLAIMS RETRIEVED: None found for this query."

    # ── Block 4: Output format rules ──────────────────────────────────────
    block4 = """Output format rules:
- If the answer contains 3 or more items, use a markdown table with headers.
- If the answer is a single number, bold it with **£X,XXX** or **N**.
- If the answer is a list of claims, use bullet points with Claim ID first.
- For comparisons, use a side-by-side table."""

    prompt = f"""{block1}

{block2}

{summary_block}

{context_block}

{block4}

USER QUESTION: {question}

ANSWER:"""

    return prompt
```

- [ ] **Step 4: Run tests — all should pass**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
python -m pytest tests/test_llm.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/llm.py tests/test_llm.py
git commit -m "feat: rewrite build_prompt with 4-block structure, chain-of-thought, and format rules"
```

---

## Task 5: RAG Pipeline Overhaul

**Files:**
- Rewrite: `ai/rag_pipeline.py`
- Create: `tests/test_rag_pipeline.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_rag_pipeline.py`:

```python
# tests/test_rag_pipeline.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from ai.rag_pipeline import RAGPipeline


def make_loader(df=None):
    loader = MagicMock()
    loader.col = {
        "claim_id": "ClaimID", "status": "Status", "claim_type": "ClaimType",
        "submitted_date": "SubmittedDate", "closed_date": "ClosedDate",
        "region": "Region", "claimant_name": "ClaimantName",
        "claim_amount": "ClaimAmount", "paid_amount": "PaidAmount",
        "reserve_amount": "ReserveAmount", "days_open": "DaysOpen",
    }
    loader.summary = {
        "total_claims": 100, "total_claim_amount": 500000.0,
        "total_paid_amount": 200000.0, "total_reserve_amount": 150000.0,
        "avg_claim_amount": 5000.0, "avg_days_open": 60.0,
        "status_counts": {"Open": 40, "Closed": 60},
        "region_counts": {"London": 30}, "type_counts": {"Medical": 50},
        "data_loaded_at": "2026-04-10", "date_range_start": "2025-04-10",
        "date_range_end": "2026-04-10",
    }
    if df is None:
        df = pd.DataFrame([{
            "ClaimID": "CLM0000001", "Status": "Open", "ClaimType": "Medical",
            "SubmittedDate": "2024-03-21", "ClosedDate": None,
            "Region": "London", "ClaimantName": "Sarah Jones",
            "ClaimAmount": 45000.0, "PaidAmount": 0.0,
            "ReserveAmount": 32000.0, "DaysOpen": 387,
        }])
    loader.df = df
    loader.config = {"data": {"chunk_size": 500}}
    return loader


def make_engine(ready=True):
    engine = MagicMock()
    type(engine).is_ready = PropertyMock(return_value=ready)
    engine.search.return_value = [
        {"chunk_id": 0, "df_index": 0, "claim_id": "CLM0000001",
         "text": "Claim CLM0000001...", "score": 0.85}
    ]
    engine.search_with_filter.return_value = [
        {"chunk_id": 0, "df_index": 0, "claim_id": "CLM0000001",
         "text": "Claim CLM0000001...", "score": 0.85}
    ]
    return engine


def make_llm(answer="Test answer"):
    llm = MagicMock()
    llm.answer.return_value = answer
    return llm


def make_pipeline(df=None, engine_ready=True, llm_answer="Test answer"):
    loader = make_loader(df)
    engine = make_engine(engine_ready)
    llm = make_llm(llm_answer)
    pipeline = RAGPipeline(loader, engine, llm)
    return pipeline, loader, engine, llm


# ── Empty question ─────────────────────────────────────────────────────────

def test_empty_question_returns_prompt():
    pipeline, *_ = make_pipeline()
    result = pipeline.ask("")
    assert "question" in result["answer"].lower()
    assert result["question_type"] == "none"


# ── Aggregation routing ────────────────────────────────────────────────────

def test_aggregation_question_does_not_call_llm():
    pipeline, loader, engine, llm = make_pipeline()
    with patch.object(pipeline.analyzer, "analyze", return_value={
        "intent": "aggregation", "claim_id": None, "status": None,
        "region": None, "claim_type": None, "date_from": None,
        "date_to": None, "high_value": False,
    }):
        result = pipeline.ask("How many open claims?")
    llm.answer.assert_not_called()
    assert result["question_type"] == "aggregation"


def test_aggregation_returns_answer_from_summary():
    pipeline, *_ = make_pipeline()
    with patch.object(pipeline.analyzer, "analyze", return_value={
        "intent": "aggregation", "claim_id": None, "status": "Open",
        "region": None, "claim_type": None, "date_from": None,
        "date_to": None, "high_value": False,
    }):
        result = pipeline.ask("How many open claims?")
    assert "40" in result["answer"] or "Open" in result["answer"]


# ── Lookup routing ─────────────────────────────────────────────────────────

def test_lookup_does_not_call_llm():
    pipeline, loader, engine, llm = make_pipeline()
    with patch.object(pipeline.analyzer, "analyze", return_value={
        "intent": "lookup", "claim_id": "CLM0000001", "status": None,
        "region": None, "claim_type": None, "date_from": None,
        "date_to": None, "high_value": False,
    }):
        result = pipeline.ask("Tell me about CLM0000001")
    llm.answer.assert_not_called()
    assert result["question_type"] == "lookup"


def test_lookup_found_claim_returns_details():
    pipeline, *_ = make_pipeline()
    with patch.object(pipeline.analyzer, "analyze", return_value={
        "intent": "lookup", "claim_id": "CLM0000001", "status": None,
        "region": None, "claim_type": None, "date_from": None,
        "date_to": None, "high_value": False,
    }):
        result = pipeline.ask("Tell me about CLM0000001")
    assert "CLM0000001" in result["answer"]


def test_lookup_missing_claim_returns_not_found():
    pipeline, *_ = make_pipeline()
    with patch.object(pipeline.analyzer, "analyze", return_value={
        "intent": "lookup", "claim_id": "CLM9999999", "status": None,
        "region": None, "claim_type": None, "date_from": None,
        "date_to": None, "high_value": False,
    }):
        result = pipeline.ask("Tell me about CLM9999999")
    assert "not found" in result["answer"].lower()


# ── Search routing ─────────────────────────────────────────────────────────

def test_search_calls_llm():
    pipeline, loader, engine, llm = make_pipeline()
    with patch.object(pipeline.analyzer, "analyze", return_value={
        "intent": "search", "claim_id": None, "status": None,
        "region": None, "claim_type": None, "date_from": None,
        "date_to": None, "high_value": False,
    }):
        result = pipeline.ask("Show me high value claims")
    llm.answer.assert_called_once()
    assert result["question_type"] == "search"


def test_search_engine_not_ready_returns_warning():
    pipeline, loader, engine, llm = make_pipeline(engine_ready=False)
    with patch.object(pipeline.analyzer, "analyze", return_value={
        "intent": "search", "claim_id": None, "status": None,
        "region": None, "claim_type": None, "date_from": None,
        "date_to": None, "high_value": False,
    }):
        result = pipeline.ask("Show me claims")
    assert "not ready" in result["answer"].lower()


# ── LLM retry + fallback ───────────────────────────────────────────────────

def test_llm_failure_triggers_fallback_answer():
    pipeline, loader, engine, llm = make_pipeline()
    llm.answer.side_effect = Exception("Ollama timeout")
    with patch.object(pipeline.analyzer, "analyze", return_value={
        "intent": "search", "claim_id": None, "status": None,
        "region": None, "claim_type": None, "date_from": None,
        "date_to": None, "high_value": False,
    }):
        result = pipeline.ask("Show me claims")
    # Should not raise — should return fallback
    assert result["answer"] is not None
    assert "error" not in result["answer"].lower() or "unavailable" in result["answer"].lower()
```

- [ ] **Step 2: Run tests — verify failures**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
python -m pytest tests/test_rag_pipeline.py -v 2>&1 | head -40
```

Expected: Several FAIL (pipeline doesn't use QueryAnalyzer yet, no retry logic).

- [ ] **Step 3: Rewrite ai/rag_pipeline.py**

Replace the entire file with:

```python
# =============================================================================
# ai/rag_pipeline.py
# Phase 2 Overhaul: Full RAG Orchestration Pipeline
# =============================================================================
# Flow:
#   question → QueryAnalyzer (intent + entities)
#            → aggregation handler (summary stats, instant)
#            → lookup handler (direct DataFrame lookup, instant)
#            → filtered FAISS search → score threshold → LLM with retry → answer
# =============================================================================

import logging
import re
import time
from typing import Dict, Any

import pandas as pd

from ai.query_analyzer import QueryAnalyzer

logger = logging.getLogger("claims.rag")


# ---------------------------------------------------------------------------
# Aggregation handler
# ---------------------------------------------------------------------------

def handle_aggregation(question: str, summary: dict, df=None, col=None,
                        entities: dict = None) -> str:
    """
    Answer aggregation questions from pre-computed summary stats or DataFrame.

    Handles: counts, totals, averages, breakdowns by region/type/status.
    Entities from QueryAnalyzer allow narrowing (e.g. count of Open only).

    Args:
        question: User's question.
        summary:  Pre-computed summary dict from ClaimsDataLoader.
        df:       Full DataFrame for group-by calculations.
        col:      Column name mapping from config.
        entities: Extracted entity dict from QueryAnalyzer (optional).

    Returns:
        Formatted answer string (markdown).
    """
    q = question.lower()
    entities = entities or {}

    # --- Group-by breakdowns -----------------------------------------------
    if df is not None and col is not None:

        if ("how many" in q or "count" in q) and "region" in q:
            result = df.groupby(col["region"])[col["claim_id"]].count().sort_values(ascending=False)
            lines = [f"- {r}: {c:,}" for r, c in result.items()]
            return "**Claims Count by Region:**\n" + "\n".join(lines)

        if ("how many" in q or "count" in q) and "type" in q:
            result = df.groupby(col["claim_type"])[col["claim_id"]].count().sort_values(ascending=False)
            lines = [f"- {t}: {c:,}" for t, c in result.items()]
            return "**Claims Count by Claim Type:**\n" + "\n".join(lines)

        if ("average" in q or "avg" in q) and "type" in q:
            result = df.groupby(col["claim_type"])[col["claim_amount"]].mean().sort_values(ascending=False)
            lines = [f"- {t}: £{v:,.2f}" for t, v in result.items()]
            return "**Average Claim Value by Claim Type:**\n" + "\n".join(lines)

        if ("average" in q or "avg" in q) and "region" in q:
            result = df.groupby(col["region"])[col["claim_amount"]].mean().sort_values(ascending=False)
            lines = [f"- {r}: £{v:,.2f}" for r, v in result.items()]
            return "**Average Claim Value by Region:**\n" + "\n".join(lines)

        if "by region" in q or "per region" in q or (
            "region" in q and ("total" in q or "value" in q or "amount" in q)
        ):
            result = df.groupby(col["region"])[col["claim_amount"]].sum().sort_values(ascending=False)
            lines = [f"- {r}: £{v:,.2f}" for r, v in result.items()]
            return "**Total Claim Value by Region:**\n" + "\n".join(lines)

        if "by claimtype" in q or "by claim type" in q or "per type" in q or (
            "type" in q and ("total" in q or "value" in q or "amount" in q)
        ):
            result = df.groupby(col["claim_type"])[col["claim_amount"]].sum().sort_values(ascending=False)
            lines = [f"- {t}: £{v:,.2f}" for t, v in result.items()]
            return "**Total Claim Value by Claim Type:**\n" + "\n".join(lines)

        if "by status" in q or "per status" in q or (
            "status" in q and ("total" in q or "value" in q or "amount" in q)
        ):
            result = df.groupby(col["status"])[col["claim_amount"]].sum().sort_values(ascending=False)
            lines = [f"- {s}: £{v:,.2f}" for s, v in result.items()]
            return "**Total Claim Value by Status:**\n" + "\n".join(lines)

    # --- Entity-aware count (e.g. "how many Open claims?") -----------------
    if "how many" in q or "count" in q:
        status_filter = entities.get("status")
        if status_filter:
            count = summary["status_counts"].get(status_filter, 0)
            return f"There are **{count:,}** {status_filter} claims in the current dataset."
        if "claim" in q:
            return f"There are **{summary['total_claims']:,}** claims in the current dataset."

    # --- Total value --------------------------------------------------------
    if "total" in q and ("value" in q or "amount" in q or "claim" in q):
        return (
            f"The total claim value across all {summary['total_claims']:,} claims is "
            f"**£{summary['total_claim_amount']:,.2f}**.\n\n"
            f"- Total paid: £{summary['total_paid_amount']:,.2f}\n"
            f"- Total reserves: £{summary['total_reserve_amount']:,.2f}"
        )

    # --- Averages -----------------------------------------------------------
    if "average" in q or "avg" in q:
        if "day" in q or "open" in q:
            return f"The average number of days a claim is open is **{summary['avg_days_open']}** days."
        return f"The average claim value is **£{summary['avg_claim_amount']:,.2f}**."

    # --- Breakdowns ---------------------------------------------------------
    if "region" in q and "breakdown" in q:
        lines = [f"- {r}: {c:,}" for r, c in summary["region_counts"].items()]
        return "**Claims by Region:**\n" + "\n".join(lines)

    if "status" in q or "breakdown" in q:
        lines = [f"- {s}: {c:,}" for s, c in summary["status_counts"].items()]
        return "**Claims by Status:**\n" + "\n".join(lines)

    if "type" in q:
        lines = [f"- {t}: {c:,}" for t, c in summary["type_counts"].items()]
        return "**Claims by Type:**\n" + "\n".join(lines)

    # --- Full summary fallback ----------------------------------------------
    return (
        f"**Claims Summary** (as of {summary.get('data_loaded_at', 'unknown')}):\n\n"
        f"- Total claims: {summary['total_claims']:,}\n"
        f"- Total value: £{summary['total_claim_amount']:,.2f}\n"
        f"- Total paid: £{summary['total_paid_amount']:,.2f}\n"
        f"- Total reserves: £{summary['total_reserve_amount']:,.2f}\n"
        f"- Average claim: £{summary['avg_claim_amount']:,.2f}\n"
        f"- Average days open: {summary['avg_days_open']} days\n"
        f"- Date range: {summary['date_range_start']} → {summary['date_range_end']}"
    )


# ---------------------------------------------------------------------------
# Lookup handler
# ---------------------------------------------------------------------------

def handle_lookup(claim_id: str, df: pd.DataFrame, col: dict) -> str:
    """
    Look up a specific claim by ID directly in the DataFrame.

    Args:
        claim_id: Claim ID string (e.g. "CLM0000042") already extracted by QueryAnalyzer.
        df:       The full claims DataFrame.
        col:      Column name mapping from config.

    Returns:
        Formatted claim detail string, or not-found message.
    """
    if not claim_id:
        return "I couldn't identify a Claim ID in your question. Please include the claim ID (e.g. CLM0000042)."

    row = df[df[col["claim_id"]] == claim_id.upper()]

    if row.empty:
        return f"Claim **{claim_id.upper()}** was not found in the current dataset."

    r = row.iloc[0]

    def s(field):
        val = r.get(col.get(field, ""), "N/A")
        return "N/A" if pd.isna(val) else str(val)

    def c(field):
        try:
            return f"£{float(r.get(col.get(field, ''), 0)):,.2f}"
        except Exception:
            return "N/A"

    submitted = s("submitted_date")[:10] if s("submitted_date") != "N/A" else "N/A"
    closed = s("closed_date")[:10] if s("closed_date") != "N/A" else "Still open"

    return (
        f"**Claim {claim_id.upper()}**\n\n"
        f"| Field | Value |\n"
        f"|---|---|\n"
        f"| Status | {s('status')} |\n"
        f"| Type | {s('claim_type')} |\n"
        f"| Claimant | {s('claimant_name')} |\n"
        f"| Region | {s('region')} |\n"
        f"| Submitted | {submitted} |\n"
        f"| Closed | {closed} |\n"
        f"| Claim Amount | {c('claim_amount')} |\n"
        f"| Paid Amount | {c('paid_amount')} |\n"
        f"| Reserve | {c('reserve_amount')} |\n"
        f"| Days Open | {s('days_open')} |"
    )


# ---------------------------------------------------------------------------
# Main RAG Pipeline
# ---------------------------------------------------------------------------

class RAGPipeline:
    """
    Orchestrates the full question-answering pipeline.

    Flow:
        question
          → QueryAnalyzer  (intent + entity extraction)
          → aggregation    (summary stats, instant) if intent == "aggregation"
          → lookup         (DataFrame, instant)     if intent == "lookup"
          → FAISS search   (pre-filtered by entities)
          → score filter   (drop low-confidence results)
          → LLM with retry (2 attempts → fallback to summary)

    Usage:
        pipeline = RAGPipeline(loader, search_engine, llm)
        response = pipeline.ask("How many open claims are in London?")
        print(response["answer"])
    """

    def __init__(self, loader, search_engine, llm):
        """
        Args:
            loader:        ClaimsDataLoader instance (already loaded).
            search_engine: ClaimsSearchEngine instance (already built).
            llm:           ClaimsLLM instance.
        """
        self.loader        = loader
        self.search_engine = search_engine
        self.llm           = llm
        self.analyzer      = QueryAnalyzer(loader.config)
        self._score_thresh = loader.config["ai"].get("faiss_score_threshold", 0.35)
        self._retry_count  = loader.config["ai"].get("llm_retry_count", 2)
        self._llm_timeout  = loader.config["ai"].get("llm_timeout", 30)

    # ------------------------------------------------------------------
    def ask(self, question: str) -> Dict[str, Any]:
        """
        Answer a natural language question about claims data.

        Args:
            question: Plain English question from the user.

        Returns:
            Dict with keys:
              - "answer"        : the answer string (always present)
              - "question_type" : "aggregation" | "lookup" | "search" | "none"
              - "sources"       : list of matched claim IDs (for search)
              - "entities"      : the QueryAnalyzer output dict
        """
        if not question or not question.strip():
            return {
                "answer": "Please ask a question about your claims data.",
                "question_type": "none",
                "sources": [],
                "entities": {},
            }

        question = question.strip()
        logger.info(f"Question received: '{question}'")

        # ── 1. Classify intent + extract entities ──────────────────────────
        entities = self.analyzer.analyze(question)
        intent   = entities["intent"]
        logger.info(f"Intent: {intent} | Entities: {entities}")

        # ── 2. Route by intent ─────────────────────────────────────────────

        if intent == "aggregation":
            answer = handle_aggregation(
                question, self.loader.summary,
                self.loader.df, self.loader.col,
                entities=entities,
            )
            return {
                "answer": answer, "question_type": "aggregation",
                "sources": [], "entities": entities,
            }

        if intent == "lookup":
            answer = handle_lookup(
                entities.get("claim_id"), self.loader.df, self.loader.col
            )
            return {
                "answer": answer, "question_type": "lookup",
                "sources": [], "entities": entities,
            }

        # ── 3. Search path: FAISS + LLM ────────────────────────────────────

        if not self.search_engine.is_ready:
            return {
                "answer": "⚠️ Search engine is not ready. Please wait for the index to build.",
                "question_type": "search",
                "sources": [],
                "entities": entities,
            }

        # Pre-filter DataFrame by extracted entities
        allowed_indices = self._get_allowed_indices(entities)

        # FAISS search — filtered if entities narrow the scope, full search otherwise
        if allowed_indices is not None:
            matched_chunks = self.search_engine.search_with_filter(question, allowed_indices)
        else:
            matched_chunks = self.search_engine.search(question)

        # Apply score threshold — drop low-confidence results
        matched_chunks = [
            c for c in matched_chunks if c.get("score", 0) >= self._score_thresh
        ]

        # If threshold wipes everything out, widen with lower threshold
        if not matched_chunks:
            if allowed_indices is not None:
                matched_chunks = self.search_engine.search_with_filter(question, allowed_indices)
            else:
                matched_chunks = self.search_engine.search(question)
            matched_chunks = [c for c in matched_chunks if c.get("score", 0) >= 0.20]

        if not matched_chunks:
            return {
                "answer": "I couldn't find any relevant claims for that question.",
                "question_type": "search",
                "sources": [],
                "entities": entities,
            }

        # Retrieve full rows from DataFrame
        from data.text_chunker import retrieve_rows_from_chunks
        context_rows = retrieve_rows_from_chunks(self.loader.df, matched_chunks)

        # LLM with retry + fallback
        answer = self._ask_llm_with_retry(question, context_rows)
        sources = [c["claim_id"] for c in matched_chunks]

        return {
            "answer": answer,
            "question_type": "search",
            "sources": sources,
            "entities": entities,
        }

    # ------------------------------------------------------------------
    def _get_allowed_indices(self, entities: dict):
        """
        Filter loader.df by extracted entities and return the set of df_index
        values. Returns None if no entity filters apply (meaning: search all).

        Args:
            entities: QueryAnalyzer output dict.

        Returns:
            Set of int df_index values, or None if no filters active.
        """
        df  = self.loader.df
        col = self.loader.col

        mask = pd.Series([True] * len(df), index=df.index)
        filtered = False

        if entities.get("status"):
            mask &= df[col["status"]].str.lower() == entities["status"].lower()
            filtered = True

        if entities.get("region"):
            mask &= df[col["region"]].str.lower() == entities["region"].lower()
            filtered = True

        if entities.get("claim_type"):
            mask &= df[col["claim_type"]].str.lower() == entities["claim_type"].lower()
            filtered = True

        if entities.get("high_value"):
            threshold = self.loader.config.get("notifications", {}).get(
                "high_value_claim_threshold", 100000
            )
            mask &= df[col["claim_amount"]] >= threshold
            filtered = True

        if not filtered:
            return None

        return set(df[mask].index.tolist())

    # ------------------------------------------------------------------
    def _ask_llm_with_retry(self, question: str, context_rows: pd.DataFrame) -> str:
        """
        Call the LLM with retry logic. On repeated failure, return a
        summary-stats fallback answer so the user always gets something useful.

        Attempt 1: Full prompt (chain-of-thought + format rules).
        Attempt 2: Simplified prompt (no chain-of-thought block).
        Fallback:  Answer from summary stats with a note that AI is unavailable.

        Args:
            question:     User's question.
            context_rows: Retrieved DataFrame rows.

        Returns:
            Answer string.
        """
        for attempt in range(self._retry_count):
            try:
                answer = self.llm.answer(
                    question     = question,
                    context_rows = context_rows,
                    col          = self.loader.col,
                    summary      = self.loader.summary,
                )
                if answer and not answer.startswith("⚠️"):
                    return answer
                logger.warning(f"LLM attempt {attempt + 1} returned error response — retrying")
            except Exception as e:
                logger.warning(f"LLM attempt {attempt + 1} failed: {e}")

        # Fallback: return summary stats with a note
        logger.error("All LLM attempts failed — returning summary stats fallback")
        s = self.loader.summary
        return (
            f"⚠️ AI engine is currently unavailable. Here is the summary data:\n\n"
            f"- Total claims: {s['total_claims']:,}\n"
            f"- Total value: £{s['total_claim_amount']:,.2f}\n"
            f"- Status breakdown: {s['status_counts']}\n\n"
            f"_Try again in a moment, or ask an aggregation question for instant results._"
        )

    # ------------------------------------------------------------------
    def rebuild(self):
        """
        Reload data and rebuild the search index.
        Called on manual or scheduled refresh.
        """
        logger.info("RAG pipeline rebuild triggered")
        self.loader.reload()

        from data.text_chunker import dataframe_to_chunks
        chunks = dataframe_to_chunks(
            self.loader.df,
            self.loader.col,
            chunk_size=self.loader.config["data"]["chunk_size"],
        )
        self.search_engine.rebuild(chunks)
        logger.info("RAG pipeline rebuild complete ✓")
```

- [ ] **Step 4: Run tests — all should pass**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
python -m pytest tests/test_rag_pipeline.py -v
```

Expected: 11 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/rag_pipeline.py tests/test_rag_pipeline.py
git commit -m "feat: overhaul RAG pipeline with QueryAnalyzer routing, entity pre-filtering, score threshold, and LLM retry chain"
```

---

## Task 6: Streamlit UI — Professional Dark Rebuild

**Files:**
- Rewrite: `ui/streamlit_app.py`

- [ ] **Step 1: Install plotly**

```bash
pip install plotly>=5.0.0
```

- [ ] **Step 2: Rewrite ui/streamlit_app.py**

Replace the entire file with:

```python
# =============================================================================
# ui/streamlit_app.py
# Phase 3 Overhaul: Professional Dark Chat UI with Plotly Charts
# =============================================================================
# Run with:  streamlit run ui/streamlit_app.py
# =============================================================================

import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.qvd_loader import ClaimsDataLoader, load_config
from data.text_chunker import dataframe_to_chunks
from ai.embeddings import ClaimsSearchEngine
from ai.llm import ClaimsLLM
from ai.rag_pipeline import RAGPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("claims.ui")

# ── Page config ───────────────────────────────────────────────────────────────
config  = load_config("config/config.yaml")
st_cfg  = config.get("streamlit", {})

st.set_page_config(
    page_title = st_cfg.get("page_title", "Claims Assistant"),
    page_icon  = "📋",
    layout     = "wide",
)

# ── Professional Dark CSS ─────────────────────────────────────────────────────
st.markdown("""
<style>
  /* ── Reset & base ── */
  .stApp { background-color: #0d1117 !important; color: #e6edf3; }
  section[data-testid="stSidebar"] { background-color: #161b22 !important; border-right: 1px solid #30363d; }
  .block-container { padding-top: 1rem !important; }

  /* ── Sidebar elements ── */
  .sidebar-logo {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 0 16px 0;
    border-bottom: 1px solid #30363d;
    margin-bottom: 16px;
  }
  .sidebar-icon {
    width: 36px; height: 36px;
    background: linear-gradient(135deg, #0078d4, #005a9e);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
  }

  /* ── KPI tiles ── */
  .kpi-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }
  .kpi {
    background: #1c2128; border: 1px solid #30363d;
    border-radius: 8px; padding: 10px;
  }
  .kpi-val { font-size: 17px; font-weight: 700; }
  .kpi-lbl { font-size: 10px; color: #8b949e; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.5px; }
  .kpi-blue .kpi-val  { color: #58a6ff; }
  .kpi-green .kpi-val { color: #3fb950; }
  .kpi-amber .kpi-val { color: #d29922; }
  .kpi-red .kpi-val   { color: #f85149; }

  /* ── Chat bubbles ── */
  .user-bubble {
    background: #0d419d; border: 1px solid #1f6feb;
    border-radius: 16px 16px 4px 16px;
    padding: 10px 14px; max-width: 65%;
    margin-left: auto; font-size: 14px; color: #e6edf3;
    margin-bottom: 4px;
  }
  .bot-bubble {
    background: #1c2128; border: 1px solid #30363d;
    border-radius: 4px 16px 16px 16px;
    padding: 12px 16px; max-width: 82%;
    font-size: 14px; color: #c9d1d9;
    margin-bottom: 4px;
  }

  /* ── Response type badges ── */
  .badge {
    display: inline-block; font-size: 10px;
    padding: 2px 8px; border-radius: 10px;
    margin-bottom: 8px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
  }
  .badge-agg    { background: #0d2137; color: #58a6ff; border: 1px solid #1f6feb; }
  .badge-lookup { background: #2d1f0d; color: #d29922; border: 1px solid #9e6a03; }
  .badge-search { background: #1a2e1a; color: #3fb950; border: 1px solid #238636; }
  .badge-error  { background: #2d0f0f; color: #f85149; border: 1px solid #da3633; }

  /* ── Source pills ── */
  .source-pill {
    display: inline-block; background: #1c2128;
    border: 1px solid #30363d; color: #8b949e;
    padding: 2px 8px; border-radius: 10px; font-size: 11px; margin: 2px;
  }

  /* ── Status bars ── */
  .sbar-wrap { margin-bottom: 8px; }
  .sbar-row  { display: flex; justify-content: space-between; font-size: 11px; color: #c9d1d9; margin-bottom: 3px; }
  .sbar-bg   { height: 4px; background: #30363d; border-radius: 2px; }
  .sbar-fill { height: 4px; border-radius: 2px; }

  /* ── Input ── */
  .stTextInput > div > div > input {
    background: #0d1117 !important; border: 1px solid #30363d !important;
    border-radius: 24px !important; color: #e6edf3 !important;
    padding: 10px 18px !important; font-size: 14px !important;
  }
  .stTextInput > div > div > input:focus {
    border-color: #0078d4 !important; box-shadow: none !important;
  }

  /* ── Buttons ── */
  .stButton > button {
    background: #1c2128 !important; border: 1px solid #30363d !important;
    color: #8b949e !important; border-radius: 6px !important; font-size: 12px !important;
  }
  .stButton > button:hover {
    border-color: #0078d4 !important; color: #58a6ff !important;
  }

  /* ── Dividers, metrics ── */
  hr { border-color: #30363d !important; }
  [data-testid="stMetricValue"] { color: #58a6ff; font-size: 18px; }
  [data-testid="stMetricLabel"] { color: #8b949e; font-size: 11px; }

  /* ── Hide Streamlit chrome ── */
  #MainMenu { visibility: hidden; }
  footer    { visibility: hidden; }
  header    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Pipeline init (cached) ────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def initialise_pipeline():
    """Load data, build FAISS index, wire RAG pipeline. Runs once per session."""
    cfg    = load_config("config/config.yaml")
    loader = ClaimsDataLoader(config_path="config/config.yaml")
    loader.load()

    chunks = dataframe_to_chunks(loader.df, loader.col, chunk_size=cfg["data"]["chunk_size"])
    engine = ClaimsSearchEngine(cfg)
    engine.build(chunks)

    llm      = ClaimsLLM(cfg)
    pipeline = RAGPipeline(loader, engine, llm)
    return pipeline, loader


def refresh_pipeline():
    st.cache_resource.clear()
    st.rerun()


# ── Chart builders ────────────────────────────────────────────────────────────

def build_bar_chart(labels: list, values: list, title: str = "") -> go.Figure:
    """Build a horizontal bar chart in the Professional Dark theme."""
    fig = go.Figure(go.Bar(
        x=values, y=labels,
        orientation="h",
        marker=dict(
            color=values,
            colorscale=[[0, "#1f6feb"], [1, "#58a6ff"]],
            showscale=False,
        ),
        text=[f"£{v:,.0f}" if max(values) > 1000 else f"{v:,}" for v in values],
        textposition="outside",
        textfont=dict(color="#8b949e", size=11),
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=60, t=30, b=0),
        height=max(200, len(labels) * 36),
        title=dict(text=title, font=dict(size=12, color="#8b949e")),
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(gridcolor="#21262d", tickfont=dict(color="#c9d1d9", size=11)),
    )
    return fig


def extract_chart_data(answer: str):
    """
    Try to parse a breakdown answer into (labels, values) for charting.
    Supports markdown lines like "- London: 2,100" or "- London: £14.1M".

    Returns (labels, values) or (None, None) if not parseable.
    """
    import re
    lines = [l.strip() for l in answer.split("\n") if l.strip().startswith("- ")]
    if len(lines) < 2:
        return None, None

    labels, values = [], []
    for line in lines:
        # Match "- Label: £1,234.56" or "- Label: 1,234"
        m = re.match(r"- (.+?):\s*£?([\d,\.]+)([kKmM]?)", line)
        if not m:
            return None, None
        label = m.group(1).strip()
        num_str = m.group(2).replace(",", "")
        multiplier = {"k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6}.get(m.group(3), 1)
        try:
            val = float(num_str) * multiplier
        except ValueError:
            return None, None
        labels.append(label)
        values.append(val)

    return list(reversed(labels)), list(reversed(values))  # ascending for horizontal bar


# ── Response renderers ────────────────────────────────────────────────────────

def render_user_msg(content: str):
    st.markdown(f'<div class="user-bubble">🧑 {content}</div>', unsafe_allow_html=True)


def render_bot_msg(response: dict, elapsed: float = None):
    """
    Render a bot response bubble with the correct badge, content, and chart.

    Args:
        response: Dict from RAGPipeline.ask() with keys: answer, question_type, sources.
        elapsed:  Response time in seconds.
    """
    q_type  = response.get("question_type", "search")
    answer  = response.get("answer", "")
    sources = response.get("sources", [])

    badge_map = {
        "aggregation": ('<span class="badge badge-agg">⚡ Aggregation</span>', True),
        "lookup":      ('<span class="badge badge-lookup">🎯 Lookup</span>', False),
        "search":      ('<span class="badge badge-search">🔍 AI Search</span>', False),
    }
    badge_html, try_chart = badge_map.get(q_type, ('<span class="badge badge-error">⚠️ Error</span>', False))

    st.markdown(f'<div class="bot-bubble">{badge_html}</div>', unsafe_allow_html=True)

    # Render answer as markdown (handles tables, bold, bullets)
    st.markdown(answer)

    # Inline chart for aggregation breakdowns
    if try_chart:
        # Find the breakdown header line to use as chart title
        title = ""
        for line in answer.split("\n"):
            if line.startswith("**") and line.endswith("**"):
                title = line.strip("*")
                break
        labels, values = extract_chart_data(answer)
        if labels and values:
            fig = build_bar_chart(labels, values, title)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Source tags for search
    if sources:
        pills = "".join(f'<span class="source-pill">{s}</span>' for s in sources[:6])
        st.markdown(f'<div style="margin-top:8px">🔍 {pills}</div>', unsafe_allow_html=True)

    # Timing
    if elapsed is not None:
        label = "⚡ instant" if elapsed < 1 else f"⏱ {elapsed:.1f}s · gemma3:4b"
        st.caption(label)


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar(loader):
    with st.sidebar:
        st.markdown("""
        <div class="sidebar-logo">
          <div class="sidebar-icon">📋</div>
          <div>
            <div style="font-size:14px;font-weight:700;color:#e6edf3">Claims Assistant</div>
            <div style="font-size:11px;color:#8b949e">AI-Powered · Local</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # KPI tiles
        s = loader.summary
        total_m = s["total_claim_amount"] / 1_000_000
        st.markdown(f"""
        <div class="kpi-grid">
          <div class="kpi kpi-blue"><div class="kpi-val">{s['total_claims']:,}</div><div class="kpi-lbl">Total</div></div>
          <div class="kpi kpi-green"><div class="kpi-val">£{total_m:.1f}M</div><div class="kpi-lbl">Value</div></div>
          <div class="kpi kpi-amber"><div class="kpi-val">£{s['avg_claim_amount']:,.0f}</div><div class="kpi-lbl">Avg Claim</div></div>
          <div class="kpi kpi-red"><div class="kpi-val">{s['avg_days_open']:.0f}d</div><div class="kpi-lbl">Avg Open</div></div>
        </div>
        """, unsafe_allow_html=True)

        # Status bars
        st.markdown('<div style="font-size:10px;color:#8b949e;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px">By Status</div>', unsafe_allow_html=True)
        total = s["total_claims"] or 1
        colour_map = {"Open": "#58a6ff", "Closed": "#3fb950", "Pending": "#d29922",
                      "Rejected": "#f85149", "Under Review": "#a371f7"}
        bars_html = ""
        for status, count in s["status_counts"].items():
            pct = count / total * 100
            col_clr = colour_map.get(status, "#58a6ff")
            bars_html += f"""
            <div class="sbar-wrap">
              <div class="sbar-row"><span>{status}</span><span>{count:,} ({pct:.0f}%)</span></div>
              <div class="sbar-bg"><div class="sbar-fill" style="width:{pct}%;background:{col_clr}"></div></div>
            </div>"""
        st.markdown(bars_html, unsafe_allow_html=True)

        st.divider()

        if st.button("🔄 Refresh Data", use_container_width=True):
            with st.spinner("Reloading..."):
                refresh_pipeline()

        st.divider()

        # Example questions
        st.markdown('<div style="font-size:10px;color:#8b949e;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px">Try asking</div>', unsafe_allow_html=True)
        examples = [
            "How many open claims are there?",
            "What is the total claim value?",
            "Show me breakdown by region",
            "Tell me about claim CLM0000003",
            "Show me high value medical claims",
            "Average claim value by type",
            "What is the average days open?",
        ]
        for ex in examples:
            if st.button(ex, use_container_width=True, key=f"ex_{ex[:25]}"):
                st.session_state.pending_question = ex

        st.divider()
        st.caption(f"🕐 Loaded: {loader.last_loaded}")
        st.caption(f"📅 {s['date_range_start']} → {s['date_range_end']}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Header
    st.markdown("""
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
      <div style="width:8px;height:8px;background:#3fb950;border-radius:50%"></div>
      <h2 style="margin:0;color:#e6edf3;font-size:18px">Claims Chat</h2>
      <span style="font-size:12px;color:#8b949e;margin-left:auto">gemma3:4b · FAISS · Local</span>
    </div>
    """, unsafe_allow_html=True)

    # Init pipeline
    with st.spinner("⚙️ Loading data and building search index..."):
        try:
            pipeline, loader = initialise_pipeline()
        except Exception as e:
            st.error(f"❌ Failed to initialise: {e}")
            st.stop()

    render_sidebar(loader)

    # LLM health warning
    if not pipeline.llm.check():
        st.warning(
            "⚠️ Ollama not running — aggregation and lookup questions work instantly. "
            "For AI search, run: `ollama serve` in a terminal.",
            icon="⚠️",
        )

    # Session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_question" not in st.session_state:
        st.session_state.pending_question = None
    if "last_question" not in st.session_state:
        st.session_state.last_question = ""

    # Chat history
    if not st.session_state.messages:
        st.markdown("""
        <div style="text-align:center;padding:60px 20px;color:#8b949e">
          <div style="font-size:32px;margin-bottom:12px">📋</div>
          <h3 style="color:#c9d1d9;margin:0 0 8px 0">Claims Assistant</h3>
          <p style="margin:0">Ask anything about your claims data in plain English.<br>
          Try the examples in the sidebar or type your own question below.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                render_user_msg(msg["content"])
            else:
                render_bot_msg(
                    response={"answer": msg["content"], "question_type": msg.get("question_type"),
                               "sources": msg.get("sources", [])},
                    elapsed=msg.get("elapsed"),
                )

    # Input area
    st.divider()
    col_input, col_clear = st.columns([6, 1])

    with col_input:
        default_val = st.session_state.pop("pending_question", None) or ""
        question = st.text_input(
            label="Ask a question",
            value=default_val,
            placeholder="e.g. How many open claims are there in London?",
            label_visibility="collapsed",
            key="question_input",
        )

    with col_clear:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_question = ""
            st.rerun()

    # Process question
    if question and question.strip() and question != st.session_state.last_question:
        st.session_state.last_question = question
        st.session_state.messages.append({"role": "user", "content": question})

        with st.spinner("🤔 Thinking..."):
            start    = time.time()
            response = pipeline.ask(question)
            elapsed  = round(time.time() - start, 1)

        st.session_state.messages.append({
            "role":          "assistant",
            "content":       response["answer"],
            "sources":       response.get("sources", []),
            "question_type": response.get("question_type"),
            "elapsed":       elapsed,
        })

        max_hist = st_cfg.get("max_chat_history", 50)
        if len(st.session_state.messages) > max_hist:
            st.session_state.messages = st.session_state.messages[-max_hist:]

        st.rerun()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Test the Streamlit UI manually**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
streamlit run ui/streamlit_app.py
```

Verify:
- Dark background loads correctly
- Sidebar shows KPI tiles and status bars
- Chat area shows empty welcome state
- Example question buttons work
- Aggregation questions show bar charts
- Lookup questions show formatted table

- [ ] **Step 4: Commit**

```bash
git add ui/streamlit_app.py
git commit -m "feat: rebuild Streamlit UI in Professional Dark theme with Plotly inline charts and response badges"
```

---

## Task 7: Teams Adaptive Cards + Bot Update

**Files:**
- Create: `bot/adaptive_cards.py`
- Modify: `bot/teams_bot.py`

- [ ] **Step 1: Create bot/adaptive_cards.py**

```python
# =============================================================================
# bot/adaptive_cards.py
# Adaptive Card templates for Microsoft Teams responses
# =============================================================================
# Each function returns a dict that the Teams bot sends as an Adaptive Card.
# Cards match response types: aggregation, lookup, search, error, notification.
# =============================================================================

import logging
from typing import List

logger = logging.getLogger("claims.cards")

# Colour tokens (Teams Adaptive Card colour names)
COLOUR_BLUE  = "Accent"
COLOUR_GREEN = "Good"
COLOUR_AMBER = "Warning"
COLOUR_RED   = "Attention"


def _card(body: list, actions: list = None) -> dict:
    """Wrap body + actions in a standard Adaptive Card v1.3 envelope."""
    card = {
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": body,
    }
    if actions:
        card["actions"] = actions
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card,
        }]
    }


def aggregation_card(question: str, answer: str, elapsed: float) -> dict:
    """
    Card for aggregation answers (counts, totals, averages, breakdowns).

    Layout:
      - Question in small grey text
      - ⚡ Aggregation badge
      - Answer text (markdown rendered)
      - Response time footer

    Args:
        question: Original question string.
        answer:   Formatted markdown answer from RAG pipeline.
        elapsed:  Response time in seconds.

    Returns:
        Teams message dict with Adaptive Card attachment.
    """
    timing = "⚡ instant" if elapsed < 1 else f"⏱ {elapsed:.1f}s"
    body = [
        {"type": "TextBlock", "text": question,
         "size": "Small", "color": "Default", "isSubtle": True, "wrap": True},
        {"type": "TextBlock", "text": "⚡ AGGREGATION",
         "size": "ExtraSmall", "color": COLOUR_BLUE, "weight": "Bolder",
         "spacing": "Small"},
        {"type": "TextBlock", "text": answer,
         "wrap": True, "spacing": "Small"},
        {"type": "TextBlock", "text": timing,
         "size": "ExtraSmall", "color": "Default", "isSubtle": True,
         "horizontalAlignment": "Right"},
    ]
    return _card(body)


def lookup_card(question: str, answer: str, claim_id: str, elapsed: float) -> dict:
    """
    Card for claim lookup responses (specific claim by ID).

    Layout:
      - 🎯 Lookup badge
      - Claim ID as header
      - Answer as formatted text
      - Response time footer

    Args:
        question: Original question string.
        answer:   Markdown answer with claim details table.
        claim_id: The claim ID that was looked up.
        elapsed:  Response time in seconds.

    Returns:
        Teams message dict with Adaptive Card attachment.
    """
    timing = "⚡ instant" if elapsed < 1 else f"⏱ {elapsed:.1f}s"
    body = [
        {"type": "TextBlock", "text": "🎯 LOOKUP",
         "size": "ExtraSmall", "color": COLOUR_AMBER, "weight": "Bolder"},
        {"type": "TextBlock", "text": claim_id,
         "size": "Large", "weight": "Bolder", "spacing": "Small"},
        {"type": "TextBlock", "text": answer,
         "wrap": True, "spacing": "Small"},
        {"type": "TextBlock", "text": timing,
         "size": "ExtraSmall", "isSubtle": True, "horizontalAlignment": "Right"},
    ]
    return _card(body)


def search_card(question: str, answer: str, sources: List[str], elapsed: float) -> dict:
    """
    Card for AI search responses (FAISS + LLM answers).

    Layout:
      - Question
      - 🔍 AI Search badge
      - Answer text
      - Source claim IDs as FactSet
      - Response time footer

    Args:
        question: Original question string.
        answer:   LLM-generated answer.
        sources:  List of source claim IDs matched by FAISS.
        elapsed:  Response time in seconds.

    Returns:
        Teams message dict with Adaptive Card attachment.
    """
    timing = f"⏱ {elapsed:.1f}s · gemma3:4b" if elapsed >= 1 else "⚡ instant"
    body = [
        {"type": "TextBlock", "text": question,
         "size": "Small", "isSubtle": True, "wrap": True},
        {"type": "TextBlock", "text": "🔍 AI SEARCH",
         "size": "ExtraSmall", "color": COLOUR_GREEN, "weight": "Bolder",
         "spacing": "Small"},
        {"type": "TextBlock", "text": answer,
         "wrap": True, "spacing": "Small"},
    ]

    if sources:
        source_text = "  ·  ".join(sources[:6])
        body.append({
            "type": "TextBlock",
            "text": f"Sources: {source_text}",
            "size": "ExtraSmall", "isSubtle": True, "spacing": "Small",
        })

    body.append({
        "type": "TextBlock", "text": timing,
        "size": "ExtraSmall", "isSubtle": True, "horizontalAlignment": "Right",
    })

    return _card(body)


def error_card(question: str, error_message: str) -> dict:
    """
    Card for error responses (LLM unavailable, data not found, etc.).

    Args:
        question:      Original question string.
        error_message: Descriptive error message to show.

    Returns:
        Teams message dict with Adaptive Card attachment.
    """
    body = [
        {"type": "TextBlock", "text": "⚠️ ERROR",
         "size": "ExtraSmall", "color": COLOUR_RED, "weight": "Bolder"},
        {"type": "TextBlock", "text": error_message, "wrap": True, "spacing": "Small"},
        {"type": "TextBlock", "text": f'Your question: "{question}"',
         "size": "Small", "isSubtle": True, "spacing": "Small"},
    ]
    actions = [
        {"type": "Action.Submit", "title": "Try Again", "data": {"question": question}},
    ]
    return _card(body, actions)


def help_card() -> dict:
    """
    Help card shown when user types 'help' or '@bot help'.

    Returns:
        Teams message dict with Adaptive Card attachment.
    """
    body = [
        {"type": "TextBlock", "text": "📋 Claims Assistant",
         "size": "Large", "weight": "Bolder"},
        {"type": "TextBlock",
         "text": "Ask me anything about your claims data in plain English.",
         "isSubtle": True, "wrap": True},
        {"type": "TextBlock", "text": "Example questions:", "weight": "Bolder",
         "spacing": "Medium"},
        {"type": "FactSet", "facts": [
            {"title": "Counts", "value": "How many open claims are there?"},
            {"title": "Totals", "value": "What is the total claim value?"},
            {"title": "Breakdown", "value": "Show me breakdown by region"},
            {"title": "Lookup", "value": "Tell me about claim CLM0000003"},
            {"title": "Search", "value": "Show me high value medical claims"},
            {"title": "Compare", "value": "Average claim value by type"},
        ]},
        {"type": "TextBlock", "text": "Commands: @bot help · @bot refresh · @bot status",
         "size": "Small", "isSubtle": True, "spacing": "Medium"},
    ]
    return _card(body)


def status_card(loader_info: dict, llm_ok: bool) -> dict:
    """
    System status card shown when user types '@bot status'.

    Args:
        loader_info: Dict with keys: total_claims, last_loaded, date_range_start, date_range_end.
        llm_ok:      True if Ollama is reachable.

    Returns:
        Teams message dict with Adaptive Card attachment.
    """
    llm_status = "✅ Online" if llm_ok else "❌ Offline (run: ollama serve)"
    body = [
        {"type": "TextBlock", "text": "📊 System Status", "size": "Large", "weight": "Bolder"},
        {"type": "FactSet", "facts": [
            {"title": "Claims loaded", "value": f"{loader_info.get('total_claims', 0):,}"},
            {"title": "Last refresh",  "value": loader_info.get("last_loaded", "Unknown")},
            {"title": "Date range",    "value": f"{loader_info.get('date_range_start', '')} → {loader_info.get('date_range_end', '')}"},
            {"title": "LLM (Ollama)",  "value": llm_status},
        ]},
    ]
    return _card(body)


def notification_card(claim_id: str, amount: float, status: str,
                      alert_type: str, timestamp: str) -> dict:
    """
    Alert card for proactive notifications pushed to Teams channel.

    Args:
        claim_id:   The claim triggering the alert (e.g. "CLM0009999").
        amount:     Claim amount in £.
        status:     Claim status string.
        alert_type: Short description (e.g. "High Value Claim").
        timestamp:  ISO timestamp string.

    Returns:
        Teams message dict with Adaptive Card attachment.
    """
    body = [
        {"type": "TextBlock", "text": "🔔 CLAIMS ALERT",
         "size": "ExtraSmall", "color": COLOUR_RED, "weight": "Bolder"},
        {"type": "TextBlock", "text": f"⚠️ {alert_type}",
         "size": "Large", "weight": "Bolder", "spacing": "Small"},
        {"type": "FactSet", "facts": [
            {"title": "Claim ID", "value": claim_id},
            {"title": "Amount",   "value": f"£{amount:,.2f}"},
            {"title": "Status",   "value": status},
            {"title": "Time",     "value": timestamp},
        ], "spacing": "Small"},
    ]
    actions = [
        {"type": "Action.Submit", "title": "View Details",
         "data": {"question": f"Tell me about claim {claim_id}"}},
        {"type": "Action.Submit", "title": "Dismiss", "data": {"action": "dismiss"}},
    ]
    return _card(body, actions)
```

- [ ] **Step 2: Update bot/teams_bot.py**

Replace the entire file with:

```python
# =============================================================================
# bot/teams_bot.py
# Teams Bot — routes questions through RAG pipeline, replies with Adaptive Cards
# =============================================================================

import logging
import re
import time

from botbuilder.core import ActivityHandler, TurnContext, MessageFactory
from botbuilder.schema import Activity

from bot.adaptive_cards import (
    aggregation_card, lookup_card, search_card,
    error_card, help_card, status_card,
)

logger = logging.getLogger("claims.bot")

COMMANDS = {"help", "@help", "hi", "hello", "refresh", "status"}


class ClaimsBot(ActivityHandler):
    """
    Microsoft Teams bot that routes messages through the RAG pipeline
    and replies with typed Adaptive Cards.
    """

    def __init__(self, pipeline):
        """
        Args:
            pipeline: Initialised RAGPipeline instance.
                      loader is accessed as pipeline.loader — no separate arg needed.
        """
        super().__init__()
        self.pipeline = pipeline
        self.loader   = pipeline.loader   # avoids breaking bot_server.py

    async def on_message_activity(self, turn_context: TurnContext):
        """Handle incoming messages. Route to command or RAG pipeline."""
        question = (turn_context.activity.text or "").strip()

        # Strip bot @mention tags
        if "<at>" in question:
            question = re.sub(r"<at>.*?</at>", "", question).strip()

        if not question:
            await self._send_card(turn_context, help_card())
            return

        q_lower = question.lower().strip()

        # ── Commands ──────────────────────────────────────────────────────
        if q_lower in {"help", "hi", "hello", "@help"}:
            await self._send_card(turn_context, help_card())
            return

        if q_lower in {"status", "@bot status"}:
            llm_ok = self.pipeline.llm.check()
            info = {
                "total_claims":     self.loader.summary.get("total_claims", 0),
                "last_loaded":      self.loader.last_loaded,
                "date_range_start": self.loader.summary.get("date_range_start", ""),
                "date_range_end":   self.loader.summary.get("date_range_end", ""),
            }
            await self._send_card(turn_context, status_card(info, llm_ok))
            return

        if q_lower in {"refresh", "@bot refresh"}:
            await turn_context.send_activity(MessageFactory.text("🔄 Refreshing data..."))
            try:
                self.pipeline.rebuild()
                await turn_context.send_activity(
                    MessageFactory.text(f"✅ Data refreshed. {self.loader.summary['total_claims']:,} claims loaded.")
                )
            except Exception as e:
                logger.error(f"Refresh failed: {e}")
                await turn_context.send_activity(MessageFactory.text(f"❌ Refresh failed: {e}"))
            return

        # ── RAG pipeline ──────────────────────────────────────────────────
        await turn_context.send_activity(MessageFactory.text("🤔 Thinking..."))

        try:
            start    = time.time()
            response = self.pipeline.ask(question)
            elapsed  = round(time.time() - start, 1)

            q_type  = response.get("question_type", "search")
            answer  = response.get("answer", "")
            sources = response.get("sources", [])
            entities = response.get("entities", {})

            if q_type == "aggregation":
                card = aggregation_card(question, answer, elapsed)
            elif q_type == "lookup":
                claim_id = entities.get("claim_id", "")
                card = lookup_card(question, answer, claim_id, elapsed)
            else:
                card = search_card(question, answer, sources, elapsed)

            await self._send_card(turn_context, card)

        except Exception as e:
            logger.error(f"Bot pipeline error: {e}")
            await self._send_card(
                turn_context,
                error_card(question, f"Something went wrong: {str(e)[:120]}")
            )

    async def on_members_added_activity(self, members_added, turn_context: TurnContext):
        """Greet new members with the help card."""
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await self._send_card(turn_context, help_card())

    @staticmethod
    async def _send_card(turn_context: TurnContext, card: dict):
        """Send an Adaptive Card as a Teams message."""
        activity = Activity.deserialize(card)
        await turn_context.send_activity(activity)
```

- [ ] **Step 3: Verify bot imports cleanly**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
python -c "from bot.adaptive_cards import help_card; print(help_card()['type'])"
```

Expected: `message`

- [ ] **Step 4: Commit**

```bash
git add bot/adaptive_cards.py bot/teams_bot.py
git commit -m "feat: add Adaptive Card templates for all response types and update Teams bot routing"
```

---

## Task 8: Notifications + Scheduler

**Files:**
- Create: `notifications/__init__.py`
- Create: `notifications/teams_notify.py`
- Create: `notifications/rules_engine.py`
- Create: `scheduler/__init__.py`
- Create: `scheduler/refresh_scheduler.py`

- [ ] **Step 1: Create notifications package**

```bash
mkdir -p /Users/meghnumnirwal/chatgpt-claims/notifications
mkdir -p /Users/meghnumnirwal/chatgpt-claims/scheduler
touch /Users/meghnumnirwal/chatgpt-claims/notifications/__init__.py
touch /Users/meghnumnirwal/chatgpt-claims/scheduler/__init__.py
```

- [ ] **Step 2: Create notifications/teams_notify.py**

```python
# =============================================================================
# notifications/teams_notify.py
# Teams webhook alert sender
# =============================================================================

import logging
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger("claims.notify.teams")


def send_teams_alert(
    webhook_url: str,
    title: str,
    message: str,
    colour: str = "FF0000",
    claim_id: Optional[str] = None,
    amount: Optional[float] = None,
) -> bool:
    """
    Send an alert card to a Microsoft Teams channel via webhook.

    Args:
        webhook_url: Teams incoming webhook URL from config.
        title:       Alert title (e.g. "High Value Claim").
        message:     Alert body text.
        colour:      Hex colour for the card side bar (default: red).
        claim_id:    Optional claim ID to include in the card.
        amount:      Optional claim amount in £.

    Returns:
        True if sent successfully, False otherwise.
    """
    if not webhook_url:
        logger.warning("Teams webhook URL not configured — skipping notification")
        return False

    facts = [{"name": "Time", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]
    if claim_id:
        facts.append({"name": "Claim ID", "value": claim_id})
    if amount is not None:
        facts.append({"name": "Amount", "value": f"£{amount:,.2f}"})

    payload = {
        "@type":      "MessageCard",
        "@context":   "http://schema.org/extensions",
        "themeColor": colour,
        "summary":    title,
        "sections": [{
            "activityTitle":    f"🔔 {title}",
            "activitySubtitle": message,
            "facts":            facts,
        }],
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info(f"Teams alert sent: {title}")
        return True
    except Exception as e:
        logger.error(f"Failed to send Teams alert: {e}")
        return False


def send_daily_summary(webhook_url: str, summary: dict) -> bool:
    """
    Push the daily claims summary card to a Teams channel.

    Args:
        webhook_url: Teams incoming webhook URL from config.
        summary:     Pre-computed summary dict from ClaimsDataLoader.

    Returns:
        True if sent successfully, False otherwise.
    """
    if not webhook_url:
        logger.warning("Teams webhook URL not configured — skipping daily summary")
        return False

    s = summary
    message = (
        f"Total: {s.get('total_claims', 0):,} claims · "
        f"£{s.get('total_claim_amount', 0):,.0f} value\n"
        f"Open: {s.get('status_counts', {}).get('Open', 0):,} · "
        f"Avg days: {s.get('avg_days_open', 0):.0f}"
    )

    return send_teams_alert(
        webhook_url = webhook_url,
        title       = "📊 Daily Claims Summary",
        message     = message,
        colour      = "0078d4",
    )
```

- [ ] **Step 3: Create notifications/rules_engine.py**

```python
# =============================================================================
# notifications/rules_engine.py
# Threshold-based trigger logic for automated alerts
# =============================================================================

import logging
from datetime import datetime, timedelta
from typing import List, Dict

import pandas as pd

from notifications.teams_notify import send_teams_alert

logger = logging.getLogger("claims.rules")


def check_high_value_claims(
    df: pd.DataFrame,
    col: dict,
    threshold: float,
    webhook_url: str,
    already_alerted: set,
) -> set:
    """
    Find claims above the high-value threshold that haven't been alerted yet.
    Sends a Teams alert for each new high-value claim found.

    Args:
        df:              Claims DataFrame.
        col:             Column name mapping from config.
        threshold:       £ amount threshold (e.g. 100000).
        webhook_url:     Teams webhook URL.
        already_alerted: Set of claim IDs already notified this session.

    Returns:
        Updated set of alerted claim IDs.
    """
    high_value = df[df[col["claim_amount"]] >= threshold]

    for _, row in high_value.iterrows():
        cid = str(row[col["claim_id"]])
        if cid in already_alerted:
            continue

        send_teams_alert(
            webhook_url = webhook_url,
            title       = "High Value Claim",
            message     = f"Claim {cid} is {row[col['status']]} with value £{row[col['claim_amount']]:,.2f}",
            colour      = "FF6B00",
            claim_id    = cid,
            amount      = float(row[col["claim_amount"]]),
        )
        already_alerted.add(cid)

    return already_alerted


def check_open_claims_threshold(
    df: pd.DataFrame,
    col: dict,
    threshold: int,
    webhook_url: str,
) -> bool:
    """
    Alert if the count of Open claims exceeds the configured threshold.

    Args:
        df:          Claims DataFrame.
        col:         Column name mapping from config.
        threshold:   Count threshold (e.g. 500).
        webhook_url: Teams webhook URL.

    Returns:
        True if alert was triggered, False otherwise.
    """
    open_count = len(df[df[col["status"]] == "Open"])
    if open_count > threshold:
        send_teams_alert(
            webhook_url = webhook_url,
            title       = "Open Claims Threshold Exceeded",
            message     = f"There are {open_count:,} open claims, exceeding the threshold of {threshold:,}.",
            colour      = "FF0000",
        )
        return True
    return False


def check_pending_days(
    df: pd.DataFrame,
    col: dict,
    threshold_days: int,
    webhook_url: str,
) -> int:
    """
    Alert for claims that have been pending beyond threshold_days.

    Args:
        df:             Claims DataFrame.
        col:            Column name mapping from config.
        threshold_days: Number of days (e.g. 90).
        webhook_url:    Teams webhook URL.

    Returns:
        Number of overdue claims found.
    """
    pending = df[
        (df[col["status"]] == "Pending") &
        (df[col["days_open"]] > threshold_days)
    ]
    count = len(pending)

    if count > 0:
        send_teams_alert(
            webhook_url = webhook_url,
            title       = f"Pending Claims Overdue (>{threshold_days} days)",
            message     = f"{count:,} claims have been Pending for more than {threshold_days} days.",
            colour      = "FF6B00",
        )

    return count


def run_all_checks(df: pd.DataFrame, col: dict, config: dict, already_alerted: set) -> set:
    """
    Run all notification checks in one call. Used by the scheduler.

    Args:
        df:              Claims DataFrame.
        col:             Column name mapping from config.
        config:          Full config dict (reads notifications section).
        already_alerted: Set of claim IDs already notified this session.

    Returns:
        Updated already_alerted set.
    """
    n_cfg       = config.get("notifications", {})
    webhook_url = n_cfg.get("teams_webhook_url", "")

    already_alerted = check_high_value_claims(
        df, col,
        threshold    = n_cfg.get("high_value_claim_threshold", 100000),
        webhook_url  = webhook_url,
        already_alerted = already_alerted,
    )

    check_open_claims_threshold(
        df, col,
        threshold   = n_cfg.get("open_claims_count_threshold", 500),
        webhook_url = webhook_url,
    )

    check_pending_days(
        df, col,
        threshold_days = n_cfg.get("pending_days_threshold", 90),
        webhook_url    = webhook_url,
    )

    return already_alerted
```

- [ ] **Step 4: Create scheduler/refresh_scheduler.py**

```python
# =============================================================================
# scheduler/refresh_scheduler.py
# Scheduled data refresh and daily summary push
# =============================================================================

import logging
import threading
import time as time_mod
from datetime import datetime

import schedule

from notifications.teams_notify import send_daily_summary
from notifications.rules_engine import run_all_checks

logger = logging.getLogger("claims.scheduler")


class ClaimsScheduler:
    """
    Background scheduler that handles:
    - Nightly data refresh (configurable time)
    - Daily summary push to Teams (configurable time)
    - Notification rule checks after each refresh

    Usage:
        scheduler = ClaimsScheduler(pipeline, config)
        scheduler.start()   # non-blocking, runs in background thread
        scheduler.stop()    # call on shutdown
    """

    def __init__(self, pipeline, config: dict):
        """
        Args:
            pipeline: Initialised RAGPipeline instance.
            config:   Full config dict from config.yaml.
        """
        self.pipeline       = pipeline
        self.config         = config
        self._stop_event    = threading.Event()
        self._thread        = None
        self._alerted_ids   = set()

        sched_cfg = config.get("scheduler", {})
        self.refresh_time = sched_cfg.get("refresh_time", "06:45")
        self.summary_time = sched_cfg.get("daily_summary_time", "07:00")

    def start(self):
        """Start the scheduler in a background daemon thread."""
        schedule.every().day.at(self.refresh_time).do(self._run_refresh)
        schedule.every().day.at(self.summary_time).do(self._run_daily_summary)

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(
            f"Scheduler started — refresh at {self.refresh_time}, "
            f"summary at {self.summary_time}"
        )

    def stop(self):
        """Signal the scheduler loop to stop."""
        self._stop_event.set()
        schedule.clear()
        logger.info("Scheduler stopped")

    def _loop(self):
        """Background loop — runs pending jobs every 30 seconds."""
        while not self._stop_event.is_set():
            schedule.run_pending()
            time_mod.sleep(30)

    def _run_refresh(self):
        """Reload data, rebuild FAISS index, run notification checks."""
        logger.info("Scheduled refresh starting...")
        try:
            self.pipeline.rebuild()
            loader = self.pipeline.loader
            logger.info(
                f"Scheduled refresh complete — "
                f"{loader.summary['total_claims']:,} claims loaded"
            )

            # Run notification checks after fresh data
            self._alerted_ids = run_all_checks(
                loader.df, loader.col, self.config, self._alerted_ids
            )

        except Exception as e:
            logger.error(f"Scheduled refresh failed: {e}")

    def _run_daily_summary(self):
        """Push daily summary card to Teams."""
        try:
            webhook_url = self.config.get("notifications", {}).get("teams_webhook_url", "")
            summary     = self.pipeline.loader.summary
            sent        = send_daily_summary(webhook_url, summary)
            if sent:
                logger.info("Daily summary pushed to Teams")
        except Exception as e:
            logger.error(f"Daily summary push failed: {e}")
```

- [ ] **Step 5: Verify imports cleanly**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
python -c "
from notifications.teams_notify import send_teams_alert
from notifications.rules_engine import run_all_checks
from scheduler.refresh_scheduler import ClaimsScheduler
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 6: Commit**

```bash
git add notifications/ scheduler/
git commit -m "feat: add Teams notification system, rules engine, and scheduled refresh/summary"
```

---

## Task 9: Final Integration Check

**Files:** `main.py` (update to verify all components)

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/meghnumnirwal/chatgpt-claims
python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Run the RAG pipeline end-to-end**

```bash
python main.py
```

Expected: Data loads, FAISS builds, test questions answered with correct types (aggregation/lookup/search), no exceptions.

- [ ] **Step 3: Verify Streamlit starts**

```bash
streamlit run ui/streamlit_app.py
```

Open http://localhost:8501. Verify:
- Dark theme renders correctly
- Sidebar KPI tiles show real numbers
- Aggregation question returns a bar chart
- Lookup question returns a formatted table

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "chore: full overhaul complete — QueryAnalyzer, improved RAG, Professional Dark UI, Adaptive Cards, notifications, scheduler"
```
