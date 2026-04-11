# =============================================================================
# notifications/rules_engine.py
# Rule-based alert engine -- checks claim data against thresholds
# =============================================================================

import logging
from datetime import datetime

import pandas as pd

from notifications.teams_notify import send_teams_alert

logger = logging.getLogger("claims.rules")


def check_high_value_claims(df, col, threshold, webhook_url, already_alerted_set):
    """
    Find claims whose amount exceeds *threshold* and alert on new ones.

    Args:
        df: DataFrame with claims data.
        col: Column name containing the dollar amount.
        threshold: Dollar threshold for high-value alerts.
        webhook_url: Teams webhook URL.
        already_alerted_set: Set of claim IDs already alerted (mutated in place).

    Returns:
        Updated already_alerted set.
    """
    if col not in df.columns:
        logger.warning(f"Column '{col}' not found -- skipping high-value check.")
        return already_alerted_set

    high = df[df[col] > threshold]
    claim_id_col = _find_claim_id_col(df)

    for _, row in high.iterrows():
        cid = str(row.get(claim_id_col, "UNKNOWN"))
        if cid in already_alerted_set:
            continue
        amount = row[col]
        send_teams_alert(
            webhook_url,
            title=f"High-Value Claim: {cid}",
            message=f"Claim {cid} has an amount of ${amount:,.2f}, "
                    f"exceeding the ${threshold:,.2f} threshold.",
            colour="FFA500",
            claim_id=cid,
            amount=amount,
        )
        already_alerted_set.add(cid)

    return already_alerted_set


def check_open_claims_threshold(df, col, threshold, webhook_url):
    """
    Alert if the number of open claims exceeds *threshold*.

    Args:
        df: DataFrame with claims data.
        col: Column name containing claim status.
        threshold: Maximum open-claim count before alerting.
        webhook_url: Teams webhook URL.
    """
    if col not in df.columns:
        logger.warning(f"Column '{col}' not found -- skipping open-claims check.")
        return

    open_count = df[df[col].str.lower().str.contains("open", na=False)].shape[0]
    if open_count > threshold:
        send_teams_alert(
            webhook_url,
            title="Open Claims Threshold Exceeded",
            message=f"There are currently {open_count:,} open claims, "
                    f"exceeding the threshold of {threshold:,}.",
            colour="FF0000",
        )


def check_pending_days(df, col, threshold_days, webhook_url):
    """
    Alert for individual claims that have been open longer than *threshold_days*.

    Args:
        df: DataFrame with claims data.
        col: Column name containing days-open value.
        threshold_days: Number of days before triggering an alert.
        webhook_url: Teams webhook URL.
    """
    if col not in df.columns:
        logger.warning(f"Column '{col}' not found -- skipping pending-days check.")
        return

    claim_id_col = _find_claim_id_col(df)
    long_pending = df[pd.to_numeric(df[col], errors="coerce") > threshold_days]

    if long_pending.empty:
        return

    count = long_pending.shape[0]
    sample_ids = long_pending[claim_id_col].head(5).tolist() if claim_id_col in long_pending.columns else []
    sample_text = ", ".join(str(s) for s in sample_ids)

    send_teams_alert(
        webhook_url,
        title=f"{count} Claims Pending > {threshold_days} Days",
        message=f"{count} claims have been open for more than {threshold_days} days. "
                f"Sample IDs: {sample_text}",
        colour="FF4500",
    )


def run_all_checks(df, col_map, config, already_alerted):
    """
    Execute every rule check using config thresholds.

    Args:
        df: DataFrame with claims data.
        col_map: Dict mapping logical names to actual column names
                 (e.g. config["columns"]).
        config: Full config dict (needs config["notifications"]).
        already_alerted: Set of claim IDs already alerted.

    Returns:
        Updated already_alerted set.
    """
    notif = config.get("notifications", {})
    webhook = notif.get("teams_webhook_url", "")

    amount_col = col_map.get("claim_amount", col_map.get("incurred_usd", "Incurred USD"))
    status_col = col_map.get("status", col_map.get("claim_status_derived", "Claim Status Derived"))
    days_col = col_map.get("days_open", col_map.get("claim_life_days", "Claim Life Days"))

    # High-value claims
    hv_thresh = notif.get("high_value_claim_threshold", 100000)
    already_alerted = check_high_value_claims(
        df, amount_col, hv_thresh, webhook, already_alerted
    )

    # Open claims count
    oc_thresh = notif.get("open_claims_count_threshold", 500)
    check_open_claims_threshold(df, status_col, oc_thresh, webhook)

    # Pending days
    pd_thresh = notif.get("pending_days_threshold", 90)
    check_pending_days(df, days_col, pd_thresh, webhook)

    return already_alerted


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_claim_id_col(df):
    """Best-effort detection of the claim ID column."""
    for candidate in ("Claim Number", "claim_id", "ClaimID", "Claim_Number"):
        if candidate in df.columns:
            return candidate
    # Fallback to first column
    return df.columns[0] if len(df.columns) > 0 else "claim_id"
