"""Unit tests for shadow-mode KPI computation (ai/kpi.py).

Uses synthetic DataFrames so tests run without a real feedback log.
"""
import sys
sys.path.insert(0, ".")

import pandas as pd
from ai.kpi import compute_kpis, time_series, KPIResult


def _log(*rows) -> pd.DataFrame:
    """rows are (ai_decision, human_decision) tuples — timestamps auto-filled."""
    ts = pd.date_range("2026-04-01", periods=len(rows), freq="H")
    return pd.DataFrame({
        "timestamp":      [t.isoformat() for t in ts],
        "claim_id":       [f"C{i:04d}" for i in range(len(rows))],
        "ai_decision":    [r[0] for r in rows],
        "human_decision": [r[1] for r in rows],
        "final_status":   ["FAST TRACKED" if r[1] == "Approve" else "MANUAL REVIEW"
                           for r in rows],
    })


def test_empty_log_returns_zeros_all_fail():
    r = compute_kpis(df=pd.DataFrame())
    assert r.total_decisions == 0
    assert r.agreement_rate == 0.0
    assert r.leakage_rate == 0.0
    assert r.friction_rate == 0.0
    assert r.agreement_status == "FAIL"


def test_perfect_agreement_all_pass():
    df = _log(
        ("FAST TRACK", "Approve"),
        ("FAST TRACK", "Approve"),
        ("MANUAL REVIEW", "Approve"),
        ("MANUAL REVIEW", "Approve"),
    )
    r = compute_kpis(df=df)
    assert r.total_decisions == 4
    assert r.agreement_rate == 1.0
    assert r.leakage_rate == 0.0
    assert r.friction_rate == 0.0
    assert r.agreement_status == "PASS"
    assert r.leakage_status == "PASS"
    assert r.friction_status == "PASS"


def test_leakage_detected_when_ai_ft_human_disagree():
    # 2 FT → 1 disagree, 2 MR → all approve
    df = _log(
        ("FAST TRACK", "Approve"),
        ("FAST TRACK", "Disagree"),    # LEAKAGE
        ("MANUAL REVIEW", "Approve"),
        ("MANUAL REVIEW", "Approve"),
    )
    r = compute_kpis(df=df)
    assert r.fast_track_total == 2
    assert r.fast_track_disagree == 1
    assert r.leakage_rate == 0.5
    assert r.leakage_status == "FAIL"   # 0% target, 50% actual
    assert r.friction_rate == 0.0


def test_friction_detected_when_ai_mr_human_disagree():
    df = _log(
        ("MANUAL REVIEW", "Approve"),
        ("MANUAL REVIEW", "Disagree"), # FRICTION
        ("MANUAL REVIEW", "Disagree"), # FRICTION
        ("FAST TRACK", "Approve"),
    )
    r = compute_kpis(df=df)
    assert r.manual_review_total == 3
    assert r.manual_review_disagree == 2
    assert abs(r.friction_rate - 2/3) < 1e-9
    assert r.friction_status == "FAIL"


def test_agreement_rate_below_90_warn_or_fail():
    # 8/10 approvals → 80% agreement, target is 90%
    pairs = [("FAST TRACK", "Approve")] * 8 + [("FAST TRACK", "Disagree")] * 2
    df = _log(*pairs)
    r = compute_kpis(df=df)
    assert r.agreement_rate == 0.8
    # 80% is below 90% but above 0.9*0.9=0.81? No — 0.8 < 0.81 → FAIL
    assert r.agreement_status == "FAIL"


def test_agreement_rate_boundary_warn():
    # 85% → between 0.81 (warn threshold) and 0.90 (pass)
    pairs = [("FAST TRACK", "Approve")] * 17 + [("FAST TRACK", "Disagree")] * 3
    df = _log(*pairs)
    r = compute_kpis(df=df)
    assert r.agreement_rate == 0.85
    assert r.agreement_status == "WARN"


def test_string_normalisation_is_forgiving():
    # Mixed case + whitespace + alt spellings
    df = _log(
        (" fast track ", "approve"),
        ("FAST TRACKED", "APPROVE"),
        ("manual review", "disagree"),
    )
    r = compute_kpis(df=df)
    assert r.fast_track_total == 2
    assert r.manual_review_total == 1
    assert r.manual_review_disagree == 1


def test_time_series_groups_by_day():
    df = pd.DataFrame({
        "timestamp": [
            "2026-04-01T09:00", "2026-04-01T10:00",
            "2026-04-02T09:00", "2026-04-02T10:00", "2026-04-02T11:00",
        ],
        "claim_id":       ["C1", "C2", "C3", "C4", "C5"],
        "ai_decision":    ["FAST TRACK"] * 5,
        "human_decision": ["Approve", "Approve", "Disagree", "Approve", "Approve"],
        "final_status":   ["FAST TRACKED"] * 5,
    })
    ts = time_series(df=df, freq="D")
    assert len(ts) == 2
    day2 = ts.iloc[1]
    assert day2["total"] == 3
    assert abs(day2["agreement_rate"] - 2/3) < 1e-9
    assert abs(day2["leakage_rate"]  - 1/3) < 1e-9
