# tests/test_triage_brain.py
import pandas as pd
import numpy as np
import pytest
from ai.triage_brain import TriageBrain


@pytest.fixture
def sample_claims():
    return pd.DataFrame({
        "Claim Number": [f"C{i:03d}" for i in range(20)],
        "Nominal Reserve": [1000 + i * 500 for i in range(20)],
        "Major LOB": ["Property Damage"] * 10 + ["Auto Liability"] * 10,
        "Event Date": pd.to_datetime("2024-01-01"),
        "Reported Date": pd.to_datetime("2024-01-05"),
        "Condition Injury Damage Name": ["Minor"] * 15 + ["Severe"] * 5,
        "Loss Description": [
            "Water damage from burst pipe in residential property.",
            "Rear-end collision at intersection. Minor vehicle damage.",
            "Slip and fall at grocery store. Bruised knee.",
            "Hail damage to roof shingles after spring storm.",
            "Fender bender in parking lot. Cosmetic damage only.",
            "Kitchen fire from unattended stove. Smoke damage.",
            "Vandalism to parked vehicle. Broken window.",
            "Tree fell on fence during windstorm.",
            "Minor flooding in basement after heavy rain.",
            "Shopping cart hit parked car. Small dent.",
            "Multi-vehicle pile-up on highway. Attorney retained.",
            "Workplace injury. Worker fell from scaffold. Neck pain.",
            "Suspicious warehouse fire. Police investigation ongoing.",
            "Claimant alleging whiplash from low-speed collision.",
            "Roof leak caused mold growth over several months.",
            "Severe burns from chemical spill at factory.",
            "Dog bite requiring surgery. Litigation threatened.",
            "Fraudulent claim suspected. Multiple inconsistencies.",
            "Back injury from lifting heavy equipment at work.",
            "Total loss vehicle. Driver hospitalized.",
        ],
        "MAR Fast Track Flag": ["Y"] * 10 + ["N"] * 10,
    })


@pytest.fixture
def brain():
    return TriageBrain()


def test_brain_build_index(brain, sample_claims):
    brain.build_index(sample_claims)
    assert brain.is_built
    assert brain.index.ntotal == 20


def test_brain_find_precedents(brain, sample_claims):
    brain.build_index(sample_claims)
    new_claim = sample_claims.iloc[0]
    precedents = brain.find_precedents(new_claim, top_k=5)
    assert len(precedents) == 5
    assert "claim_number" in precedents[0]
    assert "similarity" in precedents[0]
    assert "ft_outcome" in precedents[0]
    assert "loss_description" in precedents[0]


def test_brain_find_precedents_similarity_order(brain, sample_claims):
    brain.build_index(sample_claims)
    new_claim = sample_claims.iloc[0]
    precedents = brain.find_precedents(new_claim, top_k=5)
    sims = [p["similarity"] for p in precedents]
    assert sims == sorted(sims, reverse=True)


def test_brain_embed_feedback(brain, sample_claims):
    brain.build_index(sample_claims)
    initial_count = brain.index.ntotal
    brain.embed_feedback(
        claim_number="NEW-001",
        loss_description="New claim: minor water damage from leaking pipe.",
        ft_outcome="Y",
        human_decision="Approve",
    )
    assert brain.index.ntotal == initial_count + 1


def test_brain_feedback_is_searchable(brain, sample_claims):
    brain.build_index(sample_claims)
    brain.embed_feedback(
        claim_number="NEW-001",
        loss_description="Extremely unique scenario involving a meteorite impact on vehicle.",
        ft_outcome="N",
        human_decision="Disagree",
    )
    test_row = pd.Series({
        "Loss Description": "Meteorite hit my car. Very unusual.",
        "Claim Number": "TEST",
    })
    precedents = brain.find_precedents(test_row, top_k=3)
    found_ids = [p["claim_number"] for p in precedents]
    assert "NEW-001" in found_ids


def test_brain_precedent_summary(brain, sample_claims):
    brain.build_index(sample_claims)
    new_claim = sample_claims.iloc[0]
    precedents = brain.find_precedents(new_claim, top_k=5)
    summary = brain.summarize_precedents(precedents)
    assert "approved" in summary or "denied" in summary or "fast" in summary.lower()
