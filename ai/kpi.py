"""Shadow-mode KPIs from ai_feedback_log.csv.

Three metrics, per the Phase 4 spec:

  Agreement Rate  (target > 90%) — how often the adjuster clicked "Approve"
  False Positive  (target   0%) — "leakage": AI said FAST TRACK, human
                                  Disagreed (AI wanted to pay something it
                                  shouldn't have).
  False Negative  (target < 10%) — "friction": AI said MANUAL REVIEW, human
                                  Disagreed (AI was over-cautious; adjuster
                                  thinks this should have been fast-tracked).

Schema of data/ai_feedback_log.csv, written by ui/streamlit_app.log_triage_decision():
  timestamp, claim_id, ai_decision, human_decision, final_status

  ai_decision    : "FAST TRACK" | "MANUAL REVIEW"  (what the AI recommended)
  human_decision : "Approve"    | "Disagree"        (agreement with the AI)
  final_status   : derived — "FAST TRACKED" if Approve else "MANUAL REVIEW"
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd


DEFAULT_LOG_PATH = Path("data/ai_feedback_log.csv")

# Thresholds for the "status" column — tweak as policy evolves.
AGREEMENT_TARGET = 0.90
LEAKAGE_TARGET   = 0.00
FRICTION_TARGET  = 0.10


@dataclass
class KPIResult:
    total_decisions:       int
    agree_count:           int
    disagree_count:        int
    agreement_rate:        float  # 0..1

    fast_track_total:      int
    fast_track_disagree:   int
    leakage_rate:          float  # 0..1 — False Positive

    manual_review_total:   int
    manual_review_disagree: int
    friction_rate:         float  # 0..1 — False Negative

    # Pass/warn/fail vs targets for quick rendering:
    agreement_status: str
    leakage_status:   str
    friction_status:  str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _safe_div(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def _status(rate: float, target: float, direction: str) -> str:
    """direction='above' means higher is better; 'below' means lower is better."""
    if direction == "above":
        if rate >= target:            return "PASS"
        if rate >= target * 0.9:      return "WARN"
        return "FAIL"
    else:  # below
        if rate <= target:            return "PASS"
        if rate <= max(target, 0.01) * 3:  return "WARN"
        return "FAIL"


def compute_kpis(df: Optional[pd.DataFrame] = None,
                 path: Path = DEFAULT_LOG_PATH) -> KPIResult:
    """Compute shadow-mode KPIs.

    Pass a DataFrame to analyse in memory, or leave None to read from `path`.
    Empty or missing log → all zeros and FAIL statuses (no evidence of safety).
    """
    if df is None:
        if not Path(path).is_file():
            return _empty_result()
        df = pd.read_csv(path)

    if df is None or len(df) == 0:
        return _empty_result()

    # Normalise string columns — log is adjuster-typed, keep it forgiving.
    ai   = df["ai_decision"].astype(str).str.strip().str.upper()
    hum  = df["human_decision"].astype(str).str.strip().str.lower()

    total    = len(df)
    agree    = int((hum == "approve").sum())
    disagree = int((hum == "disagree").sum())

    # Agreement
    agreement_rate = _safe_div(agree, total)

    # FPR / Leakage — AI said FAST TRACK, human Disagreed
    ft_mask = ai.isin(["FAST TRACK", "FAST TRACKED", "FT", "APPROVE"])
    ft_total    = int(ft_mask.sum())
    ft_disagree = int((ft_mask & (hum == "disagree")).sum())
    leakage_rate = _safe_div(ft_disagree, ft_total)

    # FNR / Friction — AI said MANUAL REVIEW, human Disagreed
    mr_mask = ai.isin(["MANUAL REVIEW", "MANUAL", "MR", "REVIEW"])
    mr_total    = int(mr_mask.sum())
    mr_disagree = int((mr_mask & (hum == "disagree")).sum())
    friction_rate = _safe_div(mr_disagree, mr_total)

    return KPIResult(
        total_decisions=total,
        agree_count=agree,
        disagree_count=disagree,
        agreement_rate=agreement_rate,
        fast_track_total=ft_total,
        fast_track_disagree=ft_disagree,
        leakage_rate=leakage_rate,
        manual_review_total=mr_total,
        manual_review_disagree=mr_disagree,
        friction_rate=friction_rate,
        agreement_status=_status(agreement_rate, AGREEMENT_TARGET, "above"),
        leakage_status=_status(leakage_rate,    LEAKAGE_TARGET,    "below"),
        friction_status=_status(friction_rate,  FRICTION_TARGET,   "below"),
    )


def _empty_result() -> KPIResult:
    return KPIResult(
        total_decisions=0, agree_count=0, disagree_count=0, agreement_rate=0.0,
        fast_track_total=0, fast_track_disagree=0, leakage_rate=0.0,
        manual_review_total=0, manual_review_disagree=0, friction_rate=0.0,
        agreement_status="FAIL", leakage_status="FAIL", friction_status="FAIL",
    )


def time_series(df: Optional[pd.DataFrame] = None,
                path: Path = DEFAULT_LOG_PATH,
                freq: str = "D") -> pd.DataFrame:
    """Per-period KPI trend (default daily). Empty DF if no log."""
    if df is None:
        if not Path(path).is_file():
            return pd.DataFrame(columns=["period", "total", "agreement_rate",
                                         "leakage_rate", "friction_rate"])
        df = pd.read_csv(path)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["period", "total", "agreement_rate",
                                     "leakage_rate", "friction_rate"])

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["period"] = df["timestamp"].dt.to_period(freq).dt.to_timestamp()

    rows = []
    for period, grp in df.groupby("period"):
        r = compute_kpis(df=grp)
        rows.append({
            "period":         period,
            "total":          r.total_decisions,
            "agreement_rate": r.agreement_rate,
            "leakage_rate":   r.leakage_rate,
            "friction_rate":  r.friction_rate,
        })
    return pd.DataFrame(rows).sort_values("period").reset_index(drop=True)
