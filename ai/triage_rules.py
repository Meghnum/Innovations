# ai/triage_rules.py
# Config-driven deterministic triage rules engine.
# Reads thresholds from config/triage_config.json.
# Accepts optional config override for testing and dynamic updates.

import json
import logging
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional

import pandas as pd

logger = logging.getLogger("claims.triage")

CONFIG_PATH = Path(__file__).parent.parent / "config" / "triage_config.json"


def load_triage_config(path: Path = CONFIG_PATH) -> dict:
    """Load triage config from JSON. Falls back to hardcoded defaults."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Config load failed ({e}), using defaults")
        return _default_config()


def save_triage_config(cfg: dict, path: Path = CONFIG_PATH) -> None:
    """Write updated config to JSON (used by optimizer apply button)."""
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    logger.info(f"Triage config saved to {path}")


def _default_config() -> dict:
    return {
        "version": 1,
        "rules": {
            "reserve_limit": {"enabled": True, "max_value": 3000},
            "reporting_lag": {"enabled": True, "max_days": 14},
            "injury_keywords": {"enabled": True, "blocked_keywords": ["severe", "fatality", "bi", "bodily"]},
            "lob_exclusions": {"enabled": True, "blocked_lobs": ["casualty"]},
        },
        "semantic_guardrail": {"red_flag_keywords": [], "min_description_length": 10},
        "pending_proposals": {"rule_changes": [], "keyword_additions": []},
    }


def evaluate_deterministic_rules(
    row: pd.Series,
    config: Optional[dict] = None,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Evaluate one claim row against configurable fast-track limits.
    If config is None, loads from triage_config.json.
    """
    if config is None:
        config = load_triage_config()

    rules = config.get("rules", {})
    results: List[Dict[str, Any]] = []

    # 1. Reserve Limit
    rcfg = rules.get("reserve_limit", {})
    if rcfg.get("enabled", True):
        max_reserve = rcfg.get("max_value", 3000)
        reserve = pd.to_numeric(
            row.get("Nominal Reserve", row.get("outstanding_reserve_usd", 0)),
            errors="coerce",
        )
        if pd.isna(reserve) or reserve > max_reserve:
            results.append({"name": "Reserve Limit", "passed": False,
                            "detail": f"Reserve (${reserve:,.2f}) exceeds the ${max_reserve:,.0f} limit."})
        else:
            results.append({"name": "Reserve Limit", "passed": True,
                            "detail": f"Reserve (${reserve:,.2f}) is within the ${max_reserve:,.0f} limit."})
    else:
        results.append({"name": "Reserve Limit", "passed": True, "detail": "Rule disabled by configuration."})

    # 2. Reporting Lag
    lcfg = rules.get("reporting_lag", {})
    if lcfg.get("enabled", True):
        max_days = lcfg.get("max_days", 14)
        try:
            event_date = pd.to_datetime(row.get("Event Date", row.get("event_date")))
            reported_date = pd.to_datetime(row.get("Reported Date", row.get("reported_date")))
            lag = (reported_date - event_date).days
            if lag < 0:
                results.append({"name": "Reporting Lag", "passed": False,
                                "detail": f"Invalid dates: reported before event ({lag} days). Requires manual review."})
            elif lag > max_days:
                results.append({"name": "Reporting Lag", "passed": False,
                                "detail": f"Reporting lag ({lag} days) exceeds {max_days}-day limit."})
            else:
                results.append({"name": "Reporting Lag", "passed": True,
                                "detail": f"Reporting lag ({lag} days) is within {max_days}-day limit."})
        except Exception:
            results.append({"name": "Reporting Lag", "passed": False,
                            "detail": "Invalid or missing Event/Reported dates."})
    else:
        results.append({"name": "Reporting Lag", "passed": True, "detail": "Rule disabled by configuration."})

    # 3. Injury Keywords
    icfg = rules.get("injury_keywords", {})
    if icfg.get("enabled", True):
        blocked = icfg.get("blocked_keywords", ["severe", "fatality", "bi", "bodily"])
        injury_type = str(row.get("Injury Type", row.get("Condition Injury Damage Name", ""))).lower()
        matched = [kw for kw in blocked if kw in injury_type]
        if matched:
            results.append({"name": "Injury Type", "passed": False,
                            "detail": f"High-risk injury: {injury_type.title()} (matched: {', '.join(matched)})"})
        else:
            results.append({"name": "Injury Type", "passed": True,
                            "detail": "No blocked injury keywords detected."})
    else:
        results.append({"name": "Injury Type", "passed": True, "detail": "Rule disabled by configuration."})

    # 4. LOB Exclusions
    ecfg = rules.get("lob_exclusions", {})
    if ecfg.get("enabled", True):
        blocked_lobs = ecfg.get("blocked_lobs", ["casualty"])
        lob = str(row.get("Major LOB", row.get("major_lob", ""))).lower()
        if any(b in lob for b in blocked_lobs):
            results.append({"name": "Line of Business", "passed": False,
                            "detail": f"LOB '{lob.title()}' is excluded from fast-track."})
        else:
            results.append({"name": "Line of Business", "passed": True,
                            "detail": f"LOB '{lob.title()}' is eligible."})
    else:
        results.append({"name": "Line of Business", "passed": True, "detail": "Rule disabled by configuration."})

    passed_all = all(r["passed"] for r in results)
    return passed_all, results
