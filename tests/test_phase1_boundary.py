"""Phase 1 — Boundary tests for deterministic triage_rules.py.

Goal: prove the hardcoded knockouts never slip on edge cases.
"""
import sys
sys.path.insert(0, ".")

import pandas as pd
import numpy as np

from ai.triage_rules import evaluate_deterministic_rules, _default_config


def _row(**overrides):
    """Build a default-passing row, override specific fields per test."""
    base = {
        "Nominal Reserve": 500.00,
        "Event Date":    "2024-01-01",
        "Reported Date": "2024-01-05",
        "Injury Type":   "Minor Scratch",
        "Major LOB":     "Property",
    }
    base.update(overrides)
    return pd.Series(base)


# ── P1.1 The "$1 Over" test ─────────────────────────────────────────────
def test_reserve_exactly_one_cent_over_limit_rejected():
    cfg = _default_config()  # max_value = 3000
    row = _row(**{"Nominal Reserve": 3000.01})
    passed, results = evaluate_deterministic_rules(row, cfg)
    rcheck = next(r for r in results if r["name"] == "Reserve Limit")
    assert not rcheck["passed"], f"Expected rejection for $3000.01, got passed=True: {rcheck}"
    assert not passed


def test_reserve_exactly_at_limit_passes():
    """Control: $3000.00 exact is within the limit (rule uses `>`)."""
    cfg = _default_config()
    row = _row(**{"Nominal Reserve": 3000.00})
    _, results = evaluate_deterministic_rules(row, cfg)
    rcheck = next(r for r in results if r["name"] == "Reserve Limit")
    assert rcheck["passed"], f"$3000.00 should be within $3000 limit: {rcheck}"


# ── P1.2 The "Midnight" Date test ───────────────────────────────────────
def test_midnight_boundary_reporting_lag():
    """Event 2024-01-01 23:59:59 → Reported 2024-01-15 00:00:01 is 13 days
    in Pandas (timedelta.days truncates). 13 <= 14 → passes."""
    cfg = _default_config()  # max_days = 14
    row = _row(
        **{
            "Event Date":    "2024-01-01 23:59:59",
            "Reported Date": "2024-01-15 00:00:01",
        }
    )
    passed_all, results = evaluate_deterministic_rules(row, cfg)
    lag_check = next(r for r in results if r["name"] == "Reporting Lag")
    assert lag_check["passed"], f"13 days should pass <=14: {lag_check}"
    # Verify the computed lag is exactly 13
    import pandas as pd
    lag = (pd.to_datetime("2024-01-15 00:00:01") - pd.to_datetime("2024-01-01 23:59:59")).days
    assert lag == 13, f"Expected 13-day lag, got {lag}"


def test_fifteen_day_reporting_lag_rejected():
    """Control: 15-day lag must fail (strict > 14)."""
    cfg = _default_config()
    row = _row(
        **{
            "Event Date":    "2024-01-01 00:00:00",
            "Reported Date": "2024-01-16 00:00:00",
        }
    )
    _, results = evaluate_deterministic_rules(row, cfg)
    lag_check = next(r for r in results if r["name"] == "Reporting Lag")
    assert not lag_check["passed"], f"15 days should fail: {lag_check}"


# ── P1.3 The "Substring" LOB test ───────────────────────────────────────
def test_casualty_minor_lob_rejected():
    cfg = _default_config()  # blocked_lobs = ["casualty"]
    row = _row(**{"Major LOB": "Casualty-Minor"})
    passed_all, results = evaluate_deterministic_rules(row, cfg)
    lob = next(r for r in results if r["name"] == "Line of Business")
    assert not lob["passed"], f"'Casualty-Minor' should be blocked: {lob}"
    assert not passed_all


def test_marine_slash_casualty_lob_rejected():
    cfg = _default_config()
    row = _row(**{"Major LOB": "Marine/Casualty"})
    _, results = evaluate_deterministic_rules(row, cfg)
    lob = next(r for r in results if r["name"] == "Line of Business")
    assert not lob["passed"], f"'Marine/Casualty' should be blocked: {lob}"


# ── P1.4 The Null Trap ─────────────────────────────────────────────────
def test_nan_reserve_routes_to_manual_review():
    cfg = _default_config()
    row = _row(**{"Nominal Reserve": np.nan})
    passed_all, results = evaluate_deterministic_rules(row, cfg)
    rcheck = next(r for r in results if r["name"] == "Reserve Limit")
    assert not rcheck["passed"], f"NaN reserve should fail (not assumed $0): {rcheck}"
    assert not passed_all


def test_none_reserve_routes_to_manual_review():
    cfg = _default_config()
    row = _row(**{"Nominal Reserve": None})
    passed_all, results = evaluate_deterministic_rules(row, cfg)
    rcheck = next(r for r in results if r["name"] == "Reserve Limit")
    assert not rcheck["passed"], f"None reserve should fail: {rcheck}"


def test_missing_reserve_column_routes_to_manual_review():
    cfg = _default_config()
    # Row has no 'Nominal Reserve' key at all
    row = pd.Series({
        "Event Date": "2024-01-01",
        "Reported Date": "2024-01-05",
        "Injury Type": "Minor",
        "Major LOB": "Property",
    })
    passed_all, results = evaluate_deterministic_rules(row, cfg)
    rcheck = next(r for r in results if r["name"] == "Reserve Limit")
    assert not rcheck["passed"], f"Missing reserve column should fail: {rcheck}"
