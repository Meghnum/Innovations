"""Unit tests for the Tier 2 complexity guardrail.

Verifies which queries get escalated to the Pandas Agent vs kept on the
heuristic path. These tests don't invoke Ollama — they only check the
classifier logic.
"""
import sys
sys.path.insert(0, ".")

from ai.query_analyzer import assess_query_complexity


# -- Queries that SHOULD escalate -----------------------------------------
ESCALATE_CASES = [
    "What is the average reporting lag for A&H claims?",
    "Average reporting delay for open claims.",
    "What is the cycle time for Cyber claims?",
    "Days to close for closed claims in 2023.",
    "What percentage of our total incurred value comes from claims located in Germany?",
    "What percent of total reserves sits in the US?",
    "What % of claims are in Pending status?",
    "Share of indemnity paid for Marine LOB.",
    "Show me claims where it took more than 30 days between the event date and the reported date.",
    "Claims where it took over 60 days between event and reported dates.",
    "Only show me pending claims where the outstanding reserve is greater than $50,000 but no indemnity has been paid yet.",
    # set-exclusion / NOT-IN
    "What is the total nominal reserve for Open claims, excluding the Casualty and Auto LOBs?",
    "Show closed claims except for Marine and Cyber.",
    # disjunction / OR logic
    "Find claims that are either Closed with no Paid Indemnity OR Open with over 100k in Nominal Reserve.",
    "Either Pending or Reopened claims with reserve over 10k.",
]


# -- Queries that should STAY on heuristic (Tier 1 handles these) -------
KEEP_HEURISTIC_CASES = [
    "Give me the top 5 responsible adjusters with the highest total outstanding reserves.",
    "Which Major LOB has the least amount of open claims?",
    "Show me the bottom 10 claims by incurred value.",
    "Which country has the most claims?",
    "Give me a breakdown of the total number of claims by Major LOB and by Claim Status.",
    "What is the split of Indemnity Paid vs Expense Paid for the Cyber LOB?",
    "Show me the distribution of Catastrophe Codes.",
    "How many unique policy numbers have filed more than one claim?",
    "How many distinct accident years are there?",
    "Total expense paid for claims with event dates between Jan 1, 2020 and December 31, 2021.",
    "How many claims were closed YTD?",
    "Breakdown of claims by region.",
    "Top 3 LOBs by total reserve.",
    "How many claims were reported in 2024?",
]


def test_all_escalation_cases_fire():
    for q in ESCALATE_CASES:
        should, reason = assess_query_complexity(q)
        assert should, f"Expected escalation for: {q!r} — got should_escalate=False"
        assert reason, f"Empty reason for escalated query: {q!r}"


def test_all_heuristic_cases_stay():
    for q in KEEP_HEURISTIC_CASES:
        should, reason = assess_query_complexity(q)
        assert not should, (
            f"Expected HEURISTIC for: {q!r} — got escalated with reason={reason!r}"
        )


def test_empty_query_does_not_escalate():
    assert assess_query_complexity("") == (False, "")
    assert assess_query_complexity(None) == (False, "")


def test_reasons_are_specific():
    _, r1 = assess_query_complexity("Average reporting lag?")
    assert "derived-metric" in r1

    _, r2 = assess_query_complexity("What percent of reserves are open?")
    assert "ratio" in r2

    _, r3 = assess_query_complexity("Claims where it took more than 30 days between event and report.")
    assert "relative-time" in r3

    _, r4 = assess_query_complexity(
        "Show claims where status is pending and reserve > 50k and indemnity = 0"
    )
    assert "predicate" in r4

    _, r5 = assess_query_complexity(
        "Total reserve for Open claims, excluding Casualty and Auto."
    )
    assert "exclusion" in r5

    _, r6 = assess_query_complexity(
        "Either Closed with no indemnity or Open with reserve > 100k."
    )
    assert "disjunction" in r6
