"""Phase 3 — FAISS Vector Memory verification for TriageBrain.

P3.1 The 180-Degree Flip
    Embed an adjuster "Disagree" decision on an approved claim, reload the
    identical claim, and verify the precedent consensus shifts toward MANUAL
    REVIEW.

P3.2 The Irrelevant Context Test
    Query with a CYBER-worded description and a BENIGN reserve amount, then
    query with an AUTO-worded description at the SAME reserve. Verify the
    returned precedents cluster by TEXT (LOB), not by reserve. This proves
    the vector weights language more heavily than numbers.
"""
import sys
sys.path.insert(0, ".")

import pandas as pd
from ai.triage_brain import TriageBrain
from data.qvd_loader import ClaimsDataLoader


SAMPLE_N = 2000   # sub-sample for a fast FAISS build


def load_sample():
    loader = ClaimsDataLoader(config_path="config/config.yaml")
    loader.load()
    # stratify on Major LOB so every LOB appears
    df = loader.df
    try:
        sample = (
            df.groupby("Major LOB", group_keys=False)
              .apply(lambda g: g.sample(min(len(g), SAMPLE_N // df["Major LOB"].nunique()), random_state=42))
              .reset_index(drop=True)
        )
    except Exception:
        sample = df.sample(SAMPLE_N, random_state=42).reset_index(drop=True)
    print(f"Sample rows: {len(sample)}  LOB dist: {sample['Major LOB'].value_counts().to_dict()}", flush=True)
    return sample


def build_brain(sample: pd.DataFrame) -> TriageBrain:
    brain = TriageBrain()
    brain.build_index(sample)
    return brain


# ── P3.1 180-Degree Flip ────────────────────────────────────────────────
def test_180_flip(brain: TriageBrain, sample: pd.DataFrame):
    print("=" * 90, flush=True)
    print("P3.1 180-Degree Flip", flush=True)

    # Dataset only has ~1.3% Y-flagged claims, so random precedents rarely
    # skew approved. Create a controlled scenario: inject 6 synthetic
    # APPROVED precedents with a distinctive text, then verify find_precedents
    # returns a Y-majority ("before" state). Then inject 6 Disagrees on the
    # same text — the top-5 must flip to Disagree-majority.
    unique_desc = (
        "SYNTHETIC_TEST ZEBRA ORCHID HELIX claim — minor property damage to "
        "workshop roof from hailstorm; no injuries; policyholder filed promptly."
    )
    target = pd.Series({
        "Loss Description": unique_desc,
        "Major LOB": "Property",
        "Condition Injury Damage Name": "Roof damage",
        "Nominal Reserve": 1500.00,
        "Claim Number": "SYNTHETIC-TARGET",
    })
    # Seed 6 approved precedents
    for i in range(6):
        brain.embed_feedback(
            claim_number=f"APPROVED-{i}",
            loss_description=unique_desc,
            ft_outcome="Y",
            human_decision="Approve",
            major_lob="Property",
            reserve=1500.00,
            injury="Roof damage",
        )
    before = brain.find_precedents(target, top_k=5, exclude_self=False)
    before_approved = sum(1 for p in before if p["ft_outcome"] == "Y")
    print(f"  Target claim={target.get('Claim Number')}  LOB={target.get('Major LOB')}", flush=True)
    print(f"  BEFORE feedback: {before_approved}/5 approved", flush=True)
    before_summary = brain.summarize_precedents(before)
    print(f"  BEFORE summary tail: ...{before_summary.splitlines()[-1]}", flush=True)

    # Inject 6 "Disagree" feedbacks with identical text — once embedded later,
    # these sit just as close as the approved ones (all have cosine=1.0).
    # Top-5 should fill up with the newest Disagree insertions (FAISS returns
    # all ties; recent adds win when there are 12 identical-vector entries).
    for i in range(6):
        brain.embed_feedback(
            claim_number=f"DISAGREE-{i}",
            loss_description=unique_desc,
            ft_outcome="N",
            human_decision="Disagree",
            major_lob="Property",
            reserve=1500.00,
            injury="Roof damage",
        )

    after = brain.find_precedents(target, top_k=5, exclude_self=False)
    after_approved = sum(1 for p in after if p["ft_outcome"] == "Y")
    disagrees = sum(1 for p in after if p.get("human_decision") == "Disagree")
    print(f"  AFTER feedback:  {after_approved}/5 approved  ({disagrees}/5 have human Disagree)", flush=True)
    after_summary = brain.summarize_precedents(after)
    print(f"  AFTER summary tail: ...{after_summary.splitlines()[-1]}", flush=True)

    # PASS = the rendered recommendation flipped from FAST TRACK to MANUAL
    # REVIEW after Disagree feedback was embedded. We also require the top-5
    # to contain at least one human-Disagree entry (otherwise no flip signal
    # was visible to the summariser).
    before_is_ft = "FAST TRACK" in before_summary
    after_is_mr  = "MANUAL REVIEW" in after_summary
    verdict = "PASS" if (before_is_ft and after_is_mr and disagrees >= 1) else "FAIL"
    print(f"  P3.1 verdict: {verdict}", flush=True)
    return verdict


# ── P3.2 Irrelevant Context Test ───────────────────────────────────────
def test_irrelevant_context(brain: TriageBrain):
    print("=" * 90, flush=True)
    print("P3.2 Irrelevant Context", flush=True)

    # Two queries: same reserve, very different text
    cyber_query = pd.Series({
        "Loss Description": "Cyber ransomware attack — threat actor encrypted servers and demanded bitcoin; sensitive customer data was exfiltrated.",
        "Major LOB": "Cyber",
        "Condition Injury Damage Name": "Data breach",
        "Nominal Reserve": 50000.00,
    })
    auto_query = pd.Series({
        "Loss Description": "Rear-end collision at a red light. Bumper and trunk dented; no injuries reported; vehicle drivable.",
        "Major LOB": "Auto",
        "Condition Injury Damage Name": "Vehicle damage",
        "Nominal Reserve": 50000.00,
    })

    cyber_prec = brain.find_precedents(cyber_query, top_k=5)
    auto_prec  = brain.find_precedents(auto_query,  top_k=5)

    def lob_dist(precs):
        from collections import Counter
        return Counter(p["major_lob"] for p in precs)

    cd = lob_dist(cyber_prec); ad = lob_dist(auto_prec)
    print(f"  Cyber-text top-5 LOB dist: {dict(cd)}", flush=True)
    print(f"  Auto-text top-5 LOB dist:  {dict(ad)}", flush=True)

    # Pass criterion: the LOB distributions of the two queries are DIFFERENT,
    # i.e. results are text-driven (not collapsed to the same set by matching
    # reserve). If same reserve yielded the same LOB dist, embedding is
    # weighted too heavily on numbers.
    different = dict(cd) != dict(ad)

    # Bonus: for Auto-worded query, Auto should be the top-frequency LOB
    auto_top = (ad.most_common(1)[0][0].lower() == "auto") if ad else False

    verdict = "PASS" if different and auto_top else "FAIL"
    print(f"  text-driven (distributions differ): {different}; auto-query → Auto dominant: {auto_top}", flush=True)
    print(f"  P3.2 verdict: {verdict}", flush=True)
    return verdict


if __name__ == "__main__":
    sample = load_sample()
    brain = build_brain(sample)
    v1 = test_180_flip(brain, sample)
    v2 = test_irrelevant_context(brain)
    print("=" * 90)
    print(f"P3.1: {v1}")
    print(f"P3.2: {v2}")
