import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from ai.llm import build_prompt

COL = {
    "claim_id": "Claim Number", "status": "Claim Status Derived",
    "claim_type": "Claim Type Description", "submitted_date": "Reported Date",
    "closed_date": "Claim Closed Date", "region": "Country",
    "claimant_name": "Policy Holder Name", "claim_amount": "Incurred USD",
    "paid_amount": "Indemnity Paid USD", "reserve_amount": "Outstanding Reserve USD",
    "days_open": "Claim Life Days",
}

SUMMARY = {
    "total_claims": 10000, "total_claim_amount": 48200000.0,
    "total_paid_amount": 19000000.0, "total_reserve_amount": 17000000.0,
    "avg_claim_amount": 4820.0, "avg_days_open": 87.3,
    "status_counts": {"Open": 3487, "Closed": 4012},
    "region_counts": {"US": 5000, "UK": 2500},
    "type_counts": {"General Liability": 3000},
    "data_loaded_at": "2026-04-10 07:00:00",
    "date_range_start": "2024-04-10", "date_range_end": "2026-04-10",
}

CONTEXT_ROW = pd.DataFrame([{
    "Claim Number": "CLM0000001", "Claim Status Derived": "Open",
    "Claim Type Description": "General Liability",
    "Reported Date": "2024-03-21", "Claim Closed Date": None,
    "Country": "US", "Policy Holder Name": "Acme Corp",
    "Incurred USD": 45000.0, "Indemnity Paid USD": 0.0,
    "Outstanding Reserve USD": 32000.0, "Claim Life Days": 387,
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

def test_prompt_includes_context_rows_when_provided():
    prompt = build_prompt("Tell me about CLM0000001", CONTEXT_ROW, COL, SUMMARY)
    assert "CLM0000001" in prompt
    assert "Acme Corp" in prompt

def test_prompt_says_no_data_when_context_empty():
    prompt = build_prompt("Find claims", pd.DataFrame(), COL, SUMMARY)
    assert "None found" in prompt or "no relevant" in prompt.lower()

def test_prompt_ends_with_answer_marker():
    prompt = build_prompt("Any question", pd.DataFrame(), COL, SUMMARY)
    assert prompt.strip().endswith("ANSWER:")
