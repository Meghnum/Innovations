# =============================================================================
# bot/adaptive_cards.py
# Adaptive Card templates for Microsoft Teams bot responses
# =============================================================================

import logging
from datetime import datetime

logger = logging.getLogger("claims.cards")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _card(body, actions=None):
    """Wrap Adaptive Card body + optional actions in the standard envelope."""
    card_content = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.3",
        "body": body,
    }
    if actions:
        card_content["actions"] = actions

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card_content,
            }
        ],
    }


def _badge(text, colour):
    """Return a coloured badge TextBlock."""
    return {
        "type": "TextBlock",
        "text": text,
        "color": colour,
        "weight": "Bolder",
        "size": "Small",
    }


def _footer(elapsed):
    """Return a subtle footer showing elapsed time."""
    return {
        "type": "TextBlock",
        "text": f"Responded in {elapsed:.1f}s",
        "size": "Small",
        "isSubtle": True,
        "spacing": "Small",
    }


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------

def aggregation_card(question, answer, elapsed):
    """Card for aggregation answers (counts, sums, averages)."""
    body = [
        _badge("AGGREGATION", "Accent"),
        {
            "type": "TextBlock",
            "text": question,
            "weight": "Bolder",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": answer,
            "wrap": True,
        },
        _footer(elapsed),
    ]
    return _card(body)


def lookup_card(question, answer, claim_id, elapsed):
    """Card for single-claim lookup answers."""
    body = [
        _badge("CLAIM LOOKUP", "Warning"),
        {
            "type": "TextBlock",
            "text": question,
            "weight": "Bolder",
            "wrap": True,
        },
        {
            "type": "FactSet",
            "facts": [
                {"title": "Claim ID", "value": str(claim_id)},
            ],
        },
        {
            "type": "TextBlock",
            "text": answer,
            "wrap": True,
        },
        _footer(elapsed),
    ]
    return _card(body)


def search_card(question, answer, sources_list, elapsed):
    """Card for search/RAG answers with source references."""
    facts = [{"title": f"Source {i+1}", "value": str(s)}
             for i, s in enumerate(sources_list[:5])]

    body = [
        _badge("SEARCH", "Good"),
        {
            "type": "TextBlock",
            "text": question,
            "weight": "Bolder",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": answer,
            "wrap": True,
        },
    ]

    if facts:
        body.append({
            "type": "FactSet",
            "facts": facts,
        })

    body.append(_footer(elapsed))
    return _card(body)


def error_card(question, error_message):
    """Card shown when an error occurs."""
    body = [
        _badge("ERROR", "Attention"),
        {
            "type": "TextBlock",
            "text": question,
            "weight": "Bolder",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": error_message,
            "wrap": True,
            "color": "Attention",
        },
    ]
    actions = [
        {
            "type": "Action.Submit",
            "title": "Try Again",
            "data": {"action": "retry", "question": question},
        }
    ]
    return _card(body, actions)


def help_card():
    """Card with example questions and instructions."""
    body = [
        {
            "type": "TextBlock",
            "text": "Claims Assistant",
            "weight": "Bolder",
            "size": "Medium",
        },
        {
            "type": "TextBlock",
            "text": "Ask me anything about your claims data in plain English.",
            "wrap": True,
        },
        {
            "type": "FactSet",
            "facts": [
                {"title": "Aggregation", "value": "How many open claims are there?"},
                {"title": "Totals", "value": "What is the total incurred amount?"},
                {"title": "Breakdown", "value": "Show total value by Claim Type"},
                {"title": "Lookup", "value": "Tell me about claim CLM0000003"},
                {"title": "Search", "value": "Show me high value medical claims"},
                {"title": "Analysis", "value": "Which region has the most claims?"},
            ],
        },
        {
            "type": "TextBlock",
            "text": "Type **status** to check system health or **refresh** to reload data.",
            "wrap": True,
            "size": "Small",
            "isSubtle": True,
        },
    ]
    return _card(body)


def status_card(loader_info_dict, llm_ok_bool):
    """Card showing system status (data loader + LLM health)."""
    info = loader_info_dict or {}
    llm_status = "Connected" if llm_ok_bool else "Unavailable"
    llm_colour = "Good" if llm_ok_bool else "Attention"

    body = [
        {
            "type": "TextBlock",
            "text": "System Status",
            "weight": "Bolder",
            "size": "Medium",
        },
        {
            "type": "FactSet",
            "facts": [
                {"title": "Rows Loaded", "value": str(info.get("rows", "N/A"))},
                {"title": "Columns", "value": str(info.get("columns", "N/A"))},
                {"title": "Last Refresh", "value": str(info.get("last_refresh", "N/A"))},
                {"title": "Data Source", "value": str(info.get("source", "N/A"))},
            ],
        },
        {
            "type": "TextBlock",
            "text": f"LLM: {llm_status}",
            "color": llm_colour,
            "weight": "Bolder",
        },
    ]
    return _card(body)


def notification_card(claim_id, amount, status, alert_type, timestamp):
    """Card for proactive alerts pushed via webhook."""
    ts = timestamp if isinstance(timestamp, str) else timestamp.isoformat()

    body = [
        _badge(f"ALERT: {alert_type.upper()}", "Attention"),
        {
            "type": "FactSet",
            "facts": [
                {"title": "Claim", "value": str(claim_id)},
                {"title": "Amount", "value": f"${amount:,.2f}" if isinstance(amount, (int, float)) else str(amount)},
                {"title": "Status", "value": str(status)},
                {"title": "Time", "value": ts},
            ],
        },
    ]
    actions = [
        {
            "type": "Action.OpenUrl",
            "title": "View Details",
            "url": f"https://claims.example.com/claim/{claim_id}",
        }
    ]
    return _card(body, actions)
