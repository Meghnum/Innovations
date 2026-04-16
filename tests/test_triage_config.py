# tests/test_triage_config.py
import json
import os
import pytest
import pandas as pd

CONFIG_PATH = "config/triage_config.json"


def test_config_file_exists():
    assert os.path.isfile(CONFIG_PATH)


def test_config_valid_json():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    assert "rules" in cfg
    assert "semantic_guardrail" in cfg
    assert "pending_proposals" in cfg


def test_config_has_all_rule_keys():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    for key in ["reserve_limit", "reporting_lag", "injury_keywords", "lob_exclusions"]:
        assert key in cfg["rules"]


def test_config_reserve_is_positive_number():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    assert isinstance(cfg["rules"]["reserve_limit"]["max_value"], (int, float))
    assert cfg["rules"]["reserve_limit"]["max_value"] > 0


def test_config_lag_is_positive_number():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    assert isinstance(cfg["rules"]["reporting_lag"]["max_days"], (int, float))
    assert cfg["rules"]["reporting_lag"]["max_days"] > 0


def test_config_blocked_keywords_is_list():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    assert isinstance(cfg["rules"]["injury_keywords"]["blocked_keywords"], list)
    assert len(cfg["rules"]["injury_keywords"]["blocked_keywords"]) > 0


def test_config_red_flags_is_list():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    assert isinstance(cfg["semantic_guardrail"]["red_flag_keywords"], list)


from ai.triage_rules import evaluate_deterministic_rules, load_triage_config


def test_load_triage_config_returns_dict():
    cfg = load_triage_config()
    assert isinstance(cfg, dict)
    assert "rules" in cfg


def test_evaluate_uses_config_reserve_pass():
    """$3000 should pass with default $3000 limit."""
    row = pd.Series({
        "Nominal Reserve": 3000,
        "Event Date": "2024-01-01",
        "Reported Date": "2024-01-05",
        "Condition Injury Damage Name": "Minor scratch",
        "Major LOB": "Property Damage",
    })
    passed, results = evaluate_deterministic_rules(row)
    reserve_r = [r for r in results if r["name"] == "Reserve Limit"][0]
    assert reserve_r["passed"] is True


def test_evaluate_uses_config_reserve_fail():
    """$3001 should fail with default $3000 limit."""
    row = pd.Series({
        "Nominal Reserve": 3001,
        "Event Date": "2024-01-01",
        "Reported Date": "2024-01-05",
        "Condition Injury Damage Name": "Minor scratch",
        "Major LOB": "Property Damage",
    })
    passed, results = evaluate_deterministic_rules(row)
    reserve_r = [r for r in results if r["name"] == "Reserve Limit"][0]
    assert reserve_r["passed"] is False


def test_evaluate_with_custom_config():
    """Custom config with $5000 limit — $4500 should pass."""
    custom = {
        "rules": {
            "reserve_limit": {"enabled": True, "max_value": 5000},
            "reporting_lag": {"enabled": True, "max_days": 14},
            "injury_keywords": {"enabled": True, "blocked_keywords": ["severe", "fatality"]},
            "lob_exclusions": {"enabled": True, "blocked_lobs": ["casualty"]},
        }
    }
    row = pd.Series({
        "Nominal Reserve": 4500,
        "Event Date": "2024-01-01",
        "Reported Date": "2024-01-05",
        "Condition Injury Damage Name": "Minor scratch",
        "Major LOB": "Property Damage",
    })
    passed, results = evaluate_deterministic_rules(row, config=custom)
    reserve_r = [r for r in results if r["name"] == "Reserve Limit"][0]
    assert reserve_r["passed"] is True


def test_disabled_rule_always_passes():
    """Disabled reserve rule should auto-pass even for huge amount."""
    custom = {
        "rules": {
            "reserve_limit": {"enabled": False, "max_value": 3000},
            "reporting_lag": {"enabled": True, "max_days": 14},
            "injury_keywords": {"enabled": True, "blocked_keywords": ["severe"]},
            "lob_exclusions": {"enabled": True, "blocked_lobs": ["casualty"]},
        }
    }
    row = pd.Series({
        "Nominal Reserve": 999999,
        "Event Date": "2024-01-01",
        "Reported Date": "2024-01-05",
        "Condition Injury Damage Name": "Minor scratch",
        "Major LOB": "Property Damage",
    })
    passed, results = evaluate_deterministic_rules(row, config=custom)
    reserve_r = [r for r in results if r["name"] == "Reserve Limit"][0]
    assert reserve_r["passed"] is True
