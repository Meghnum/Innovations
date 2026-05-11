"""Run the 14 user-supplied category tests + a dozen adjacent ones end-to-end
and print full answers for human review.

Uses keyword-fallback analyzer + direct handlers (no Ollama dependency).
"""
import sys
import re
import time
sys.path.insert(0, ".")

import pandas as pd
from ai.query_analyzer import QueryAnalyzer
from ai.rag_pipeline import handle_aggregation, handle_lookup, handle_fuzzy_lookup
from data.qvd_loader import ClaimsDataLoader

print("Loading data...")
loader = ClaimsDataLoader(config_path="config/config.yaml")
loader.load()
df = loader.df
col = loader.col
summary = loader.summary
qa = QueryAnalyzer()
print(f"Loaded {len(df):,} claims.\n")

# Extended prompt set = 14 from user + adjacent variants
PROMPTS = [
    # ── Rankings & Sorting ──
    ("Rankings", "Give me the top 5 responsible adjusters with the highest total outstanding reserves."),
    ("Rankings", "Which Major LOB has the least amount of open claims?"),
    ("Rankings", "Show me the bottom 10 claims by incurred value."),
    ("Rankings", "Which country has the most claims?"),
    ("Rankings", "Top 3 LOBs by total reserve."),

    # ── Distributions & Groupings ──
    ("Distributions", "Give me a breakdown of the total number of claims by Major LOB and by Claim Status."),
    ("Distributions", "What is the split of Indemnity Paid vs Expense Paid for the Cyber LOB?"),
    ("Distributions", "Show me the distribution of Catastrophe Codes."),
    ("Distributions", "Breakdown of claims by region."),

    # ── Aggregations & Ratios ──
    ("Aggregations", "How many unique policy numbers have filed more than one claim?"),
    ("Aggregations", "What is the average reporting lag for A&H claims?"),
    ("Aggregations", "What percentage of our total incurred value comes from claims located in Germany?"),
    ("Aggregations", "How many distinct accident years are there?"),
    ("Aggregations", "What is the total paid across all claims?"),

    # ── Temporal / Time-Series ──
    ("Temporal", "Total expense paid for claims with event dates between Jan 1, 2020 and December 31, 2021."),
    ("Temporal", "How many claims were closed YTD (Year-to-Date)?"),
    ("Temporal", "Show me claims where it took more than 30 days between the event date and the reported date."),
    ("Temporal", "How many claims were reported in 2024?"),

    # ── Complex Exclusions & Intersections ──
    ("Exclusions", "What is the total nominal reserve for Open claims, excluding the Casualty and Auto LOBs?"),
    ("Exclusions", "Only show me pending claims where the outstanding reserve is greater than $50,000 but no indemnity has been paid yet."),
    ("Exclusions", "Show me all open claims except those in the US."),
    ("Exclusions", "Show me claims from 2023 excluding property LOB."),
]


def run_one(prompt: str) -> tuple:
    t0 = time.time()
    analysis = qa._keyword_fallback(prompt)
    intent = analysis["intent"]
    entities = {
        "status": analysis.get("status"),
        "region": analysis.get("region"),
        "claim_type": analysis.get("claim_type"),
        "high_value": analysis.get("high_value", False),
    }
    try:
        if intent == "aggregation":
            answer = handle_aggregation(prompt, summary, df, col, entities)
        elif intent == "lookup":
            cid = analysis.get("claim_id")
            pid = analysis.get("policy_id")
            if not cid and not pid:
                fuzzy = handle_fuzzy_lookup(prompt, df, col)
                answer = fuzzy if fuzzy else handle_lookup(cid, df, col, policy_id=pid)
            else:
                answer = handle_lookup(cid, df, col, policy_id=pid)
        else:
            fuzzy = handle_fuzzy_lookup(prompt, df, col)
            answer = fuzzy if fuzzy else "[search path — FAISS/LLM not invoked in test]"
    except Exception as e:
        answer = f"ERROR: {e}"
    return intent, answer, round(time.time() - t0, 2)


results = []
for category, prompt in PROMPTS:
    intent, answer, dur = run_one(prompt)
    is_fb = any(x in answer.lower() for x in [
        "don't have", "not found", "couldn't find",
        "claims summary", "would route", "[search path"
    ])
    is_zero = bool(re.search(r'\(0 matching claims\)|0 total\)|: \$0\.00\b', answer))
    is_error = answer.startswith("ERROR")
    status = "ERROR" if is_error else ("FALLBACK" if is_fb else ("ZERO" if is_zero else "OK"))
    results.append({"category": category, "prompt": prompt, "intent": intent,
                    "status": status, "dur_s": dur, "answer": answer})

# Print results
for r in results:
    icon = {"OK": "✅", "ZERO": "⚠️", "FALLBACK": "❌", "ERROR": "💥"}[r["status"]]
    print("=" * 90)
    print(f"{icon} [{r['category']:13s}] intent={r['intent']:11s} {r['status']:8s} ({r['dur_s']}s)")
    print(f"Q: {r['prompt']}")
    print(f"A: {r['answer'][:900]}")
    if len(r['answer']) > 900:
        print(f"   ... [truncated, {len(r['answer'])} chars total]")
    print()

# Summary
print("=" * 90)
print("SUMMARY")
print("=" * 90)
from collections import Counter
status_counts = Counter(r["status"] for r in results)
cat_status = {}
for r in results:
    cat_status.setdefault(r["category"], Counter())[r["status"]] += 1

print(f"Total: {len(results)} prompts")
for s in ["OK", "ZERO", "FALLBACK", "ERROR"]:
    print(f"  {s:10s}: {status_counts.get(s, 0)}")
print()
print("By category:")
for cat, cnt in cat_status.items():
    parts = " | ".join(f"{k}={v}" for k, v in cnt.items())
    print(f"  {cat:15s}: {parts}")

# Save
pd.DataFrame(results).to_csv("tests/category_test_results.csv", index=False)
print("\nSaved: tests/category_test_results.csv")
