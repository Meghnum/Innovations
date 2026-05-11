"""Run Claims_Assistant_Query_Test_Suite.xlsx end-to-end through RAGPipeline.

Exercises the full hybrid stack: heuristic handler + complexity guardrail +
Pandas Agent escalation. Requires Ollama with gemma3:4b for escalated prompts.
"""
import sys
import time
import pandas as pd
sys.path.insert(0, ".")

from ai.rag_pipeline import RAGPipeline
from ai.query_analyzer import assess_query_complexity
from ai.embeddings import ClaimsSearchEngine
from ai.llm import ClaimsLLM
from data.qvd_loader import ClaimsDataLoader, load_config

XLSX = "Claims_Assistant_Query_Test_Suite.xlsx"

print("Loading test suite...")
suite = pd.read_excel(XLSX)
print(f"{len(suite)} test cases loaded.\n")

print("Building RAGPipeline (lazy FAISS)...")
cfg = load_config("config/config.yaml")
loader = ClaimsDataLoader(config_path="config/config.yaml")
loader.load()
engine = ClaimsSearchEngine(cfg)   # NOT built; aggregation path doesn't need it
llm = ClaimsLLM(cfg)
pipe = RAGPipeline(loader, engine, llm)
print("Ready.\n")

results = []
for _, row in suite.iterrows():
    tc = row["Test_ID"]
    cat = row["Category"]
    q = row["Prompt_to_Test"]
    should, reason = assess_query_complexity(q)

    print("=" * 92, flush=True)
    print(f"[{tc}] {cat}", flush=True)
    print(f"Q: {q}", flush=True)
    print(f"  guardrail: escalate={should}  reason={reason!r}", flush=True)

    t0 = time.time()
    try:
        resp = pipe.ask(q)
        dur = round(time.time() - t0, 1)
        ans = resp.get("answer", "")
        qtype = resp.get("question_type", "?")
        esc = resp.get("escalation_reason")
        status = "OK"
        print(f"  qtype={qtype}  dur={dur}s  escalation={esc!r}", flush=True)
        print(f"  A: {ans[:600]}", flush=True)
        if len(ans) > 600:
            print(f"     ... [{len(ans)} chars total]", flush=True)
    except Exception as e:
        dur = round(time.time() - t0, 1)
        ans = f"ERROR: {type(e).__name__}: {e}"
        qtype = "error"
        esc = None
        status = "ERROR"
        print(f"  💥 {ans}", flush=True)
    print("", flush=True)

    results.append({
        "test_id": tc, "category": cat, "prompt": q,
        "escalate": should, "reason": reason,
        "qtype": qtype, "escalation_actual": esc,
        "dur_s": dur, "status": status, "answer": ans,
        "pass_criteria": row["Pass_Criteria"],
    })

pd.DataFrame(results).to_csv("tests/test_suite_xlsx_results.csv", index=False)
print("=" * 92)
print(f"Saved tests/test_suite_xlsx_results.csv — {len(results)} rows")
