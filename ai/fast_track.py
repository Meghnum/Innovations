"""Fast Track / STP Prediction Engine.

Two-layer system:
  1. Deterministic rules engine (strict gatekeeper — overrides ML)
  2. ML model (Random Forest) trained on historical MAR Fast Track Flag

Usage:
    predictor = FastTrackPredictor()
    predictor.train(df, col)                     # train on historical data
    result = predictor.predict(claim_row, col)    # predict single claim
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.preprocessing import LabelEncoder

logger = logging.getLogger("claims.fast_track")

# ---------------------------------------------------------------------------
# Deterministic Rules
# ---------------------------------------------------------------------------
RESERVE_THRESHOLD = 5_000.0          # USD
REPORTING_LAG_THRESHOLD = 14         # days
DENIED_LOBS = {"casualty"}           # always manual review
SEVERE_INJURIES = {"severe", "fatality"}

TEXT_RED_FLAGS = [
    "attorney", "lawyer", "legal", "litigation", "lawsuit",
    "police investigation", "police report", "fraud", "suspicious",
    "third-party fault", "third party", "subrogation dispute",
    "death", "fatality", "permanent disability", "amputation",
    "class action", "regulatory", "osha", "epa",
]


@dataclass
class RuleResult:
    """Result of a single deterministic rule check."""
    rule_name: str
    passed: bool
    detail: str


@dataclass
class FastTrackResult:
    """Full prediction result for a single claim."""
    claim_number: str
    fast_track_approved: bool
    rule_results: List[RuleResult] = field(default_factory=list)
    reasons_for_denial: List[str] = field(default_factory=list)
    ml_probability: Optional[float] = None
    ml_recommendation: Optional[bool] = None
    semantic_analysis: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_number": self.claim_number,
            "fast_track_approved": self.fast_track_approved,
            "reasons_for_denial": self.reasons_for_denial,
            "rule_results": [
                {"rule": r.rule_name, "passed": r.passed, "detail": r.detail}
                for r in self.rule_results
            ],
            "ml_probability": round(self.ml_probability, 3) if self.ml_probability is not None else None,
            "ml_recommendation": self.ml_recommendation,
            "semantic_analysis": self.semantic_analysis,
        }


# ---------------------------------------------------------------------------
# Rules Engine
# ---------------------------------------------------------------------------
def check_rules(
    claim: Dict[str, Any],
    reserve_threshold: float = RESERVE_THRESHOLD,
    lag_threshold: int = REPORTING_LAG_THRESHOLD,
) -> Tuple[bool, List[RuleResult], List[str]]:
    """Run all deterministic rules against a claim dict.

    Returns (all_passed, rule_results, denial_reasons).
    """
    results: List[RuleResult] = []
    denials: List[str] = []

    # 1. Financial: Nominal Reserve > threshold
    reserve = _to_float(claim.get("nominal_reserve", 0))
    if reserve > reserve_threshold:
        results.append(RuleResult(
            "FINANCIAL",
            False,
            f"Nominal Reserve ${reserve:,.2f} > ${reserve_threshold:,.2f} threshold",
        ))
        denials.append(f"Reserve ${reserve:,.2f} exceeds ${reserve_threshold:,.2f}")
    else:
        results.append(RuleResult(
            "FINANCIAL",
            True,
            f"Nominal Reserve ${reserve:,.2f} within threshold",
        ))

    # 2. Time Lag: Event → Reported > threshold days
    lag_days = _calc_lag(claim.get("event_date"), claim.get("reported_date"))
    if lag_days is not None and lag_days > lag_threshold:
        results.append(RuleResult(
            "TIME_LAG",
            False,
            f"Reporting lag {lag_days} days > {lag_threshold}-day threshold",
        ))
        denials.append(f"Reporting lag {lag_days} days exceeds {lag_threshold}")
    else:
        lag_str = f"{lag_days} days" if lag_days is not None else "N/A"
        results.append(RuleResult(
            "TIME_LAG",
            True,
            f"Reporting lag {lag_str} within threshold",
        ))

    # 3. Injury Severity
    injury = str(claim.get("injury_type", "") or "").strip().lower()
    if injury in SEVERE_INJURIES:
        results.append(RuleResult(
            "INJURY_SEVERITY",
            False,
            f"Injury type '{injury.title()}' requires manual review",
        ))
        denials.append(f"Injury type: {injury.title()}")
    else:
        results.append(RuleResult(
            "INJURY_SEVERITY",
            True,
            f"Injury type '{injury.title() if injury else 'None'}' acceptable",
        ))

    # 4. Line of Business
    lob = str(claim.get("major_lob", "") or "").strip().lower()
    if lob in DENIED_LOBS:
        results.append(RuleResult(
            "LINE_OF_BUSINESS",
            False,
            f"Major LOB '{lob.title()}' never eligible for fast-track",
        ))
        denials.append(f"LOB: {lob.title()} (litigation risk)")
    else:
        results.append(RuleResult(
            "LINE_OF_BUSINESS",
            True,
            f"Major LOB '{lob.title() if lob else 'N/A'}' eligible",
        ))

    # 5. Textual Red Flags
    desc = str(claim.get("loss_description", "") or "").lower()
    event_desc = str(claim.get("claim_event_desc", "") or "").lower()
    combined_text = f"{desc} {event_desc}"
    found_flags = [f for f in TEXT_RED_FLAGS if f in combined_text]
    if found_flags:
        results.append(RuleResult(
            "TEXT_RED_FLAGS",
            False,
            f"Red flags detected: {', '.join(found_flags)}",
        ))
        denials.append(f"Text red flags: {', '.join(found_flags)}")
    else:
        results.append(RuleResult(
            "TEXT_RED_FLAGS",
            True,
            "No textual red flags detected",
        ))

    all_passed = len(denials) == 0
    return all_passed, results, denials


# ---------------------------------------------------------------------------
# ML Feature Engineering
# ---------------------------------------------------------------------------
# Columns used as ML features
NUMERIC_FEATURES = [
    "nominal_reserve", "incurred_usd", "indemnity_paid_usd",
    "expense_paid_usd", "expense_reserve_usd", "outstanding_reserve_usd",
    "recoveries_usd", "claim_life_days", "company_share",
]

CATEGORICAL_FEATURES = [
    "major_lob", "minor_lob", "executive_lob", "country",
    "claim_type_code", "coverage_code", "cause_of_loss_code",
    "catastrophe_code",
]

DERIVED_FEATURES = ["reporting_lag_days"]


def _build_feature_row(claim: Dict[str, Any], col: Dict[str, str], df_row: pd.Series = None) -> Dict[str, Any]:
    """Extract ML features from a claim dict or DataFrame row."""
    source = df_row if df_row is not None else claim

    def _get(key: str):
        """Get value from source, trying config col mapping first."""
        col_name = col.get(key, key) if col else key
        if df_row is not None:
            return df_row.get(col_name, df_row.get(key))
        return claim.get(key, claim.get(col_name))

    features = {}

    # Numeric
    for feat in NUMERIC_FEATURES:
        features[feat] = _to_float(_get(feat))

    # Categorical
    for feat in CATEGORICAL_FEATURES:
        val = _get(feat)
        features[feat] = str(val).strip() if val is not None and str(val).strip() else "Unknown"

    # Derived: reporting lag
    event_d = _get("event_date")
    report_d = _get("reported_date")
    features["reporting_lag_days"] = _calc_lag(event_d, report_d) or 0

    return features


def _build_feature_matrix(df: pd.DataFrame, col: Dict[str, str]) -> pd.DataFrame:
    """Build feature matrix from full DataFrame."""
    rows = []
    for _, row in df.iterrows():
        rows.append(_build_feature_row({}, col, df_row=row))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# FastTrackPredictor
# ---------------------------------------------------------------------------
class FastTrackPredictor:
    """Two-layer Fast Track prediction: rules + ML."""

    def __init__(self):
        self.model: Optional[RandomForestClassifier] = None
        self.label_encoders: Dict[str, LabelEncoder] = {}
        self.is_trained: bool = False
        self.metrics: Dict[str, float] = {}
        self.feature_importance: Dict[str, float] = {}
        self._train_size: int = 0
        self._ft_rate: float = 0.0

    # ── Training ─────────────────────────────────────────────────────────

    def train(self, df: pd.DataFrame, col: Dict[str, str]) -> Dict[str, Any]:
        """Train RF model on historical fast-track decisions.

        Returns metrics dict with accuracy, precision, recall, f1.
        """
        ft_col = col.get("mar_fast_track_flag", "MAR Fast Track Flag")
        if ft_col not in df.columns:
            logger.warning(f"Fast Track column '{ft_col}' not found. Cannot train.")
            return {"error": f"Column '{ft_col}' not found"}

        logger.info("Building feature matrix for Fast Track model...")
        feat_df = _build_feature_matrix(df, col)
        y = df[ft_col].astype(bool).astype(int)

        self._train_size = len(df)
        self._ft_rate = y.mean()

        # Encode categoricals
        self.label_encoders = {}
        for cat_col in CATEGORICAL_FEATURES:
            le = LabelEncoder()
            feat_df[cat_col] = le.fit_transform(feat_df[cat_col].astype(str))
            self.label_encoders[cat_col] = le

        # Fill NaN
        feat_df = feat_df.fillna(0)

        # Split
        X_train, X_test, y_train, y_test = train_test_split(
            feat_df, y, test_size=0.2, random_state=42, stratify=y,
        )

        # Train
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=12,
            min_samples_split=20,
            min_samples_leaf=10,
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(X_train, y_train)
        self.is_trained = True

        # Evaluate
        y_pred = self.model.predict(X_test)
        self.metrics = {
            "accuracy": round(accuracy_score(y_test, y_pred), 4),
            "precision": round(precision_score(y_test, y_pred, zero_division=0), 4),
            "recall": round(recall_score(y_test, y_pred, zero_division=0), 4),
            "f1": round(f1_score(y_test, y_pred, zero_division=0), 4),
            "train_size": len(X_train),
            "test_size": len(X_test),
            "ft_rate": round(self._ft_rate, 4),
        }

        # Feature importance
        all_features = NUMERIC_FEATURES + CATEGORICAL_FEATURES + DERIVED_FEATURES
        importances = self.model.feature_importances_
        self.feature_importance = {
            f: round(float(imp), 4)
            for f, imp in sorted(zip(all_features, importances), key=lambda x: -x[1])
        }

        logger.info(
            f"Fast Track model trained. Accuracy={self.metrics['accuracy']}, "
            f"F1={self.metrics['f1']}, FT rate={self._ft_rate:.1%}"
        )
        return self.metrics

    # ── Prediction ───────────────────────────────────────────────────────

    def predict(self, claim: Dict[str, Any], col: Dict[str, str]) -> FastTrackResult:
        """Predict fast-track eligibility for a single claim.

        Layer 1: Deterministic rules (strict gatekeeper).
        Layer 2: ML model probability (advisory).

        Rules OVERRIDE ML — if any rule fails, claim is denied regardless of ML.
        """
        claim_num = str(claim.get("claim_number", claim.get("claim_id", "UNKNOWN")))

        # Layer 1: Rules
        rules_passed, rule_results, denials = check_rules(claim)

        # Layer 2: ML
        ml_prob = None
        ml_rec = None
        if self.is_trained and self.model is not None:
            try:
                feat = _build_feature_row(claim, col)
                feat_df = pd.DataFrame([feat])
                for cat_col in CATEGORICAL_FEATURES:
                    le = self.label_encoders.get(cat_col)
                    if le is not None:
                        val = feat_df[cat_col].astype(str).iloc[0]
                        if val in le.classes_:
                            feat_df[cat_col] = le.transform([val])
                        else:
                            feat_df[cat_col] = -1  # unseen category
                feat_df = feat_df.fillna(0)
                ml_prob = float(self.model.predict_proba(feat_df)[0][1])
                ml_rec = ml_prob >= 0.5
            except Exception as e:
                logger.warning(f"ML prediction failed: {e}")

        # Final decision: rules are the gatekeeper
        approved = rules_passed
        if rules_passed and ml_prob is not None and ml_prob < 0.3:
            # ML strongly disagrees — flag but still allow (rules are primary)
            pass

        # Semantic analysis
        desc = str(claim.get("loss_description", "") or "")
        event_desc = str(claim.get("claim_event_desc", "") or "")
        semantic = _generate_semantic_summary(desc, event_desc, approved, denials)

        return FastTrackResult(
            claim_number=claim_num,
            fast_track_approved=approved,
            rule_results=rule_results,
            reasons_for_denial=denials,
            ml_probability=ml_prob,
            ml_recommendation=ml_rec,
            semantic_analysis=semantic,
        )

    def predict_from_row(self, row: pd.Series, col: Dict[str, str]) -> FastTrackResult:
        """Predict from a DataFrame row (existing claim)."""
        claim = {
            "claim_number": row.get(col.get("claim_number", "Claim Number"), ""),
            "major_lob": row.get(col.get("major_lob", "Major LOB"), ""),
            "minor_lob": row.get(col.get("minor_lob", "Minor LOB"), ""),
            "executive_lob": row.get(col.get("executive_lob", "Executive LOB"), ""),
            "nominal_reserve": row.get(col.get("nominal_reserve", "Nominal Reserve"), 0),
            "event_date": row.get(col.get("event_date", "Event Date"), ""),
            "reported_date": row.get(col.get("reported_date", "Reported Date"), ""),
            "loss_description": row.get(col.get("loss_description", "Loss Description"), ""),
            "claim_event_desc": row.get(col.get("claim_event_desc", "Claim Event Desc"), ""),
            "country": row.get(col.get("country", "Country"), ""),
            "incurred_usd": row.get(col.get("incurred_usd", "Incurred USD"), 0),
            "indemnity_paid_usd": row.get(col.get("indemnity_paid_usd", "Indemnity Paid USD"), 0),
            "expense_paid_usd": row.get(col.get("expense_paid_usd", "Expense Paid USD"), 0),
            "expense_reserve_usd": row.get(col.get("expense_reserve_usd", "Expense Reserve USD"), 0),
            "outstanding_reserve_usd": row.get(col.get("outstanding_reserve_usd", "Outstanding Reserve USD"), 0),
            "recoveries_usd": row.get(col.get("recoveries_usd", "Recoveries USD"), 0),
            "claim_life_days": row.get(col.get("claim_life_days", "Claim Life Days"), 0),
            "company_share": row.get(col.get("company_share", "Company Share"), 0),
            "claim_type_code": row.get(col.get("claim_type_code", "Claim Type Code"), ""),
            "coverage_code": row.get(col.get("coverage_code", "Coverage Code"), ""),
            "cause_of_loss_code": row.get(col.get("cause_of_loss_code", "Cause of Loss Code"), ""),
            "catastrophe_code": row.get(col.get("catastrophe_code", "Catastrophe Code"), ""),
            "injury_type": row.get(col.get("condition_injury_damage_name", "Condition Injury Damage Name"), ""),
        }
        return self.predict(claim, col)

    def batch_predict(self, df: pd.DataFrame, col: Dict[str, str]) -> pd.DataFrame:
        """Predict fast-track for all claims. Returns DataFrame with predictions."""
        results = []
        for idx, row in df.iterrows():
            res = self.predict_from_row(row, col)
            results.append({
                "claim_number": res.claim_number,
                "fast_track_approved": res.fast_track_approved,
                "ml_probability": res.ml_probability,
                "denial_reasons": "; ".join(res.reasons_for_denial) if res.reasons_for_denial else "",
                "rules_passed": all(r.passed for r in res.rule_results),
            })
        return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_float(val) -> float:
    """Safe float conversion."""
    if val is None:
        return 0.0
    try:
        if isinstance(val, str):
            val = val.replace(",", "").replace("$", "").replace("%", "")
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _calc_lag(event_date, reported_date) -> Optional[int]:
    """Calculate reporting lag in days."""
    if not event_date or not reported_date:
        return None
    try:
        if isinstance(event_date, str):
            ed = pd.to_datetime(event_date)
        else:
            ed = event_date
        if isinstance(reported_date, str):
            rd = pd.to_datetime(reported_date)
        else:
            rd = reported_date
        lag = (rd - ed).days
        return max(0, lag)
    except Exception:
        return None


def _generate_semantic_summary(
    loss_desc: str, event_desc: str, approved: bool, denials: List[str]
) -> str:
    """Generate a brief semantic analysis of the claim text."""
    combined = f"{loss_desc} {event_desc}".strip()
    if not combined or combined == " ":
        text_note = "No loss description provided for text analysis."
    else:
        # Check for complexity indicators
        complex_words = ["multiple", "several", "ongoing", "recurring", "dispute",
                         "investigation", "complex", "significant"]
        found_complex = [w for w in complex_words if w in combined.lower()]
        if found_complex:
            text_note = (f"Loss description contains complexity indicators "
                         f"({', '.join(found_complex)}), suggesting careful review.")
        else:
            text_note = "Loss description appears straightforward with no hidden complexity indicators."

    if approved:
        return f"Claim APPROVED for fast-track. {text_note}"
    else:
        return f"Claim DENIED fast-track ({len(denials)} rule(s) failed). {text_note}"
