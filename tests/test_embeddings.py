import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

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
    allowed = {0, 3}
    results = engine.search_with_filter("medical claims London", allowed)
    returned_indices = {r["df_index"] for r in results}
    assert returned_indices.issubset(allowed)

def test_search_with_filter_empty_allowed_set(engine):
    results = engine.search_with_filter("anything", set())
    assert results == []

def test_search_with_filter_returns_scores(engine):
    allowed = {0, 1, 2, 3, 4}
    results = engine.search_with_filter("open medical claim", allowed)
    assert all("score" in r for r in results)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
