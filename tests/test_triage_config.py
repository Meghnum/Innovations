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
