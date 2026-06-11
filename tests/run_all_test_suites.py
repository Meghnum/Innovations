"""Run every test case in:
    - Claims_Assistant_Query_Test_Suite.xlsx  (15 cases)
    - Claims_Bot_Test_Cases.xlsx              (1000 cases)
through the live RAG pipeline against Industry_Standard_Claims_50K.csv, and
write a single results workbook to tests/test_results.xlsx.

Columns in the output:
    Source_File, Test_ID, Category/Difficulty, Prompt, Expected, Answer,
    Question_Type, Escalation_Reason, Elapsed_s, Status, Error

Status is heuristic:
    - CLARIFY if question_type == 'clarification'
    - ERROR   if an exception occurred
    - OK      otherwise (human must still judge correctness)
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.qvd_loader import ClaimsDataLoader
from ai.embeddings import ClaimsSearchEngine
from ai.llm import ClaimsLLM
from ai.rag_pipeline import RAGPipeline


SUITE_A = "Claims_Assistant_Query_Test_Suite.xlsx"          # 15 cases
SUITE_B = "Claims_Bot_Test_Cases.xlsx"                       # 1000 cases
OUT_PATH = Path("tests/test_results.xlsx")


def _load_suite_a() -> pd.DataFrame:
    df = pd.read_excel(SUITE_A, sheet_name=0)
    return pd.DataFrame({
        "Source_File":   SUITE_A,
        "Test_ID":       df["Test_ID"],
        "Category":      df["Category"],
        "Prompt":        df["Prompt_to_Test"],
        "Expected":      df["Pass_Criteria"],
    })


def _load_suite_b() -> pd.DataFrame:
    df = pd.read_excel(SUITE_B, sheet_name="Test Cases (1000)")
    return pd.DataFrame({
        "Source_File":   SUITE_B,
        "Test_ID":       df["Test Case ID"],
        "Category":      df["Difficulty"] + " / " + df["Intent Category"].astype(str),
        "Prompt":        df["User Prompt"],
        "Expected":      df["Expected Bot Action / Logic"],
    })


def _build_pipeline() -> RAGPipeline:
    loader = ClaimsDataLoader(config_path="config/config.yaml")
    loader.load()
    cfg = loader.config
    search = ClaimsSearchEngine(cfg)
    llm = ClaimsLLM(cfg)
    return RAGPipeline(loader, search, llm)


def _run_one(pipe: RAGPipeline, prompt: str) -> dict:
    t0 = time.time()
    try:
        resp = pipe.ask(prompt)
        answer = resp.get("answer", "")
        qtype = resp.get("question_type", "")
        reason = resp.get("escalation_reason", "")
        err = ""
        # --- Strict QA assertions ---
        # A plausible-looking answer is NOT a pass when:
        #   1. Pandas Agent failed and heuristic gave an approximate answer
        #      (detected by the ⚠️ banner)
        #   2. Pipeline returned an explicit agent_error (QA mode)
        #   3. Clarification requested (already flagged CLARIFY)
        ans_str = answer if isinstance(answer, str) else str(answer)
        if qtype == "clarification":
            status = "CLARIFY"
        elif qtype == "agent_error" or ans_str.startswith("AGENT_ERROR:"):
            status = "FAIL"
            err = ans_str[:500]
        elif "⚠️" in ans_str or "approximate" in ans_str.lower():
            status = "FAIL"
            err = "heuristic fallback: Pandas Agent failed, approximate answer returned"
        else:
            status = "OK"
    except Exception as e:  # noqa: BLE001
        answer = ""
        qtype = ""
        reason = ""
        status = "ERROR"
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}"
    elapsed = round(time.time() - t0, 2)
    return {
        "Answer": answer[:2000] if isinstance(answer, str) else str(answer)[:2000],
        "Question_Type": qtype,
        "Escalation_Reason": reason,
        "Elapsed_s": elapsed,
        "Status": status,
        "Error": err,
    }


def _save(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        # Full results
        df.to_excel(xl, sheet_name="All Results", index=False)
        # Summary counts
        summary = (
            df.groupby(["Source_File", "Status"])
              .size().unstack(fill_value=0).reset_index()
        )
        summary.to_excel(xl, sheet_name="Summary", index=False)
        # Slow / errored cases for quick triage
        slow = df.nlargest(25, "Elapsed_s")[
            ["Source_File", "Test_ID", "Prompt", "Elapsed_s", "Status"]
        ]
        slow.to_excel(xl, sheet_name="Slowest 25", index=False)
        errs = df[df["Status"].isin(["ERROR", "FAIL"])][
            ["Source_File", "Test_ID", "Prompt", "Status", "Question_Type",
             "Escalation_Reason", "Answer", "Error"]
        ]
        if len(errs):
            errs.to_excel(xl, sheet_name="Failures", index=False)


def main() -> None:
    print("Loading dataset + pipeline…", flush=True)
    pipe = _build_pipeline()
    print(f"Ready. Dataset rows: {len(pipe.loader.df):,}", flush=True)

    cases = pd.concat([_load_suite_a(), _load_suite_b()], ignore_index=True)
    print(f"Running {len(cases):,} test cases…", flush=True)

    rows: list[dict] = []
    t_start = time.time()
    for i, row in cases.iterrows():
        prompt = str(row["Prompt"]).strip()
        if not prompt or prompt.lower() == "nan":
            continue
        r = _run_one(pipe, prompt)
        rows.append({
            "Source_File": row["Source_File"],
            "Test_ID": row["Test_ID"],
            "Category": row["Category"],
            "Prompt": prompt,
            "Expected": row["Expected"],
            **r,
        })
        if (i + 1) % 25 == 0 or (i + 1) == len(cases):
            elapsed = time.time() - t_start
            rate = (i + 1) / elapsed if elapsed else 0
            eta = (len(cases) - (i + 1)) / rate if rate else 0
            print(
                f"  {i+1:>4}/{len(cases)}  ({rate:.2f} q/s, ETA {eta/60:.1f} min)  "
                f"last: {r['Status']} {r['Elapsed_s']}s",
                flush=True,
            )
            # Incremental checkpoint every 100 rows — survives crashes.
            if (i + 1) % 100 == 0:
                _save(pd.DataFrame(rows), OUT_PATH)

    out_df = pd.DataFrame(rows)
    _save(out_df, OUT_PATH)
    elapsed = time.time() - t_start
    print(f"\nDone in {elapsed/60:.1f} min → {OUT_PATH}", flush=True)
    print(out_df["Status"].value_counts().to_string())


if __name__ == "__main__":
    main()
