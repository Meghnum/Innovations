"""Direct Pandas Agent test for the 4 Tier-2 prompts.

Bypasses RAGPipeline to avoid FAISS build on fallback.
Requires Ollama running locally with gemma3:4b.
"""
import sys
import time
sys.path.insert(0, ".")

from data.qvd_loader import ClaimsDataLoader
from ai.pandas_agent import pandas_query
from ai.query_analyzer import assess_query_complexity

print("Loading data...")
loader = ClaimsDataLoader(config_path="config/config.yaml")
loader.load()
df, col = loader.df, loader.col

TIER2_PROMPTS = [
    ("avg reporting lag A&H", "What is the average reporting lag for A&H claims?"),
    ("% from Germany",        "What percentage of our total incurred value comes from claims located in Germany?"),
    ("lag > 30 days",         "Show me claims where it took more than 30 days between the event date and the reported date."),
    ("triple filter",         "Only show me pending claims where the outstanding reserve is greater than $50,000 but no indemnity has been paid yet."),
]

for label, q in TIER2_PROMPTS:
    print("=" * 90, flush=True)
    print(f"[{label}]", flush=True)
    print(f"Q: {q}", flush=True)

    should, reason = assess_query_complexity(q)
    print(f"  guardrail: should_escalate={should}  reason={reason!r}", flush=True)

    if not should:
        print("  ❌ guardrail failed to escalate", flush=True)
        continue

    t0 = time.time()
    try:
        ans = pandas_query(q, df, col, ollama_model="gemma3:4b")
        dur = round(time.time() - t0, 1)
        if ans is None:
            print(f"  ❌ pandas_query returned None ({dur}s)", flush=True)
        else:
            print(f"  ✅ pandas_query OK ({dur}s)", flush=True)
            print(f"  A: {ans[:400]}", flush=True)
    except Exception as e:
        print(f"  💥 {type(e).__name__}: {e}", flush=True)
    print("", flush=True)
