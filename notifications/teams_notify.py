# =============================================================================
# notifications/teams_notify.py
# Send alert and summary cards to Microsoft Teams via incoming webhook
# =============================================================================

import logging
from datetime import datetime

import requests

logger = logging.getLogger("claims.notify")


def send_teams_alert(webhook_url, title, message, colour="FF0000",
                     claim_id=None, amount=None):
    """
    POST a MessageCard to the Teams webhook.

    Args:
        webhook_url: Incoming webhook URL for the Teams channel.
        title: Alert title.
        message: Alert body text.
        colour: Theme colour hex (no leading #).
        claim_id: Optional claim identifier.
        amount: Optional dollar amount.

    Returns:
        True on success, False on failure.
    """
    if not webhook_url:
        logger.warning("Teams webhook URL is empty -- skipping alert.")
        return False

    facts = []
    if claim_id:
        facts.append({"name": "Claim ID", "value": str(claim_id)})
    if amount is not None:
        facts.append({"name": "Amount", "value": f"${amount:,.2f}"
                       if isinstance(amount, (int, float)) else str(amount)})
    facts.append({"name": "Time", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": colour,
        "summary": title,
        "sections": [
            {
                "activityTitle": title,
                "facts": facts,
                "text": message,
                "markdown": True,
            }
        ],
    }

    try:
        resp = requests.post(webhook_url, json=card, timeout=10)
        if resp.status_code == 200:
            logger.info(f"Teams alert sent: {title}")
            return True
        else:
            logger.warning(f"Teams webhook returned {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Teams alert: {e}")
        return False


def send_daily_summary(webhook_url, summary_dict):
    """
    Send a daily summary card to Teams.

    Args:
        webhook_url: Incoming webhook URL.
        summary_dict: Dict with keys like total_claims, open_claims,
                      closed_today, high_value_count, total_incurred, etc.

    Returns:
        True on success, False on failure.
    """
    if not webhook_url:
        logger.warning("Teams webhook URL is empty -- skipping daily summary.")
        return False

    s = summary_dict or {}
    facts = [
        {"name": "Total Claims", "value": str(s.get("total_claims", "N/A"))},
        {"name": "Open Claims", "value": str(s.get("open_claims", "N/A"))},
        {"name": "Closed Today", "value": str(s.get("closed_today", "N/A"))},
        {"name": "High-Value Claims", "value": str(s.get("high_value_count", "N/A"))},
        {"name": "Total Incurred (USD)", "value": f"${s.get('total_incurred', 0):,.2f}"
         if isinstance(s.get("total_incurred"), (int, float)) else str(s.get("total_incurred", "N/A"))},
        {"name": "Report Date", "value": datetime.now().strftime("%Y-%m-%d")},
    ]

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0078D7",
        "summary": "Daily Claims Summary",
        "sections": [
            {
                "activityTitle": "Daily Claims Summary",
                "facts": facts,
                "markdown": True,
            }
        ],
    }

    try:
        resp = requests.post(webhook_url, json=card, timeout=10)
        if resp.status_code == 200:
            logger.info("Daily summary sent to Teams.")
            return True
        else:
            logger.warning(f"Teams webhook returned {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send daily summary: {e}")
        return False
