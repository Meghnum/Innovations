"""Text-to-Pandas Agent — LLM generates Pandas code for arbitrary queries.

Fallback for queries that no hardcoded handler can answer.
The LLM writes Pandas code, which is executed in a sandboxed environment.

Safety:
  - Restricted builtins (no file I/O, no imports, no exec/eval)
  - Timeout via signal alarm
  - DataFrame is read-only (copy passed)
  - Only pandas and numpy available
"""

from __future__ import annotations

import logging
import re
import signal
import traceback
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("claims.pandas_agent")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_EXEC_TIMEOUT = 10  # seconds

# Banned patterns in generated code (safety)
_BANNED_PATTERNS = [
    r"\bimport\b",
    r"\b__\w+__\b",       # dunder access
    r"\bexec\b",
    r"\beval\b",
    r"\bopen\b",
    r"\bos\.\b",
    r"\bsys\.\b",
    r"\bsubprocess\b",
    r"\bshutil\b",
    r"\bglobals\b",
    r"\blocals\b",
    r"\bcompile\b",
    r"\b\.to_csv\b",
    r"\b\.to_excel\b",
    r"\b\.to_parquet\b",
    r"\b\.to_sql\b",
    r"\b\.to_json\b",
    r"\bdf\s*=\s*",       # reassigning df
    r"\bdel\b",
    r"\b_apply_filters\b",
]

# ---------------------------------------------------------------------------
# Prompt for code generation
# ---------------------------------------------------------------------------
def _build_codegen_prompt(
    question: str,
    columns: list,
    dtypes: dict,
    sample_values: dict,
    row_count: int,
) -> str:
    """Build prompt that instructs LLM to write Pandas code."""

    col_info = "\n".join(
        f"  - {c} ({dtypes.get(c, 'object')})"
        + (f"  # sample: {sample_values.get(c, '')}" if c in sample_values else "")
        for c in columns
    )

    return f"""You are an Elite Pandas Data Analyst for insurance claims.

DATAFRAME INFO:
- Variable name: `df` (already loaded, {row_count:,} rows)
- Columns and types:
{col_info}

RULES:
1. Write ONLY Python code using pandas (as `pd`) and numpy (as `np`). They are ALREADY imported. DO NOT write any import statements.
2. The DataFrame `df` is ALREADY loaded. DO NOT reassign df.
3. Store the final answer in a variable called `result`.
4. `result` must be one of: a string, a number, a pandas Series, or a small DataFrame.
5. Do NOT modify the original `df`. Use `.copy()` if needed for filtering.
6. Do NOT use print(), import, exec, eval, open, or os.
7. For currency formatting, use f-strings like f"${{val:,.2f}}".
8. Keep code concise — 1 to 10 lines max.
9. If you cannot answer the question from the available columns, set result = "I cannot answer this question with the available data columns."

CRITICAL INSURANCE DOMAIN RULES:
A. Reporting Lag (days) = (pd.to_datetime(df['Reported Date']) - pd.to_datetime(df['Event Date'])).dt.days
B. Cycle Time / Days Open = (pd.to_datetime(df['Claim Closed Date']) - pd.to_datetime(df['Reported Date'])).dt.days
C. YTD means current calendar year — use pd.Timestamp.today().year
D. Percentage / ratio → compute (numerator_sum / total_sum) * 100 and format as a string with '%'. Example:
     pct = df.loc[mask, 'Incurred USD'].sum() / df['Incurred USD'].sum() * 100
     result = f"{{pct:.2f}}%"
E. "LOB" = Major LOB column unless specified otherwise.
F. Always filter BEFORE aggregating (e.g., df[mask].groupby(...)).
G. When the user asks for an average of a derived metric (like reporting lag),
   compute the metric first, then .mean() — don't .mean() raw columns.

EXAMPLES:

Question: "What is the average reporting lag for A&H claims?"
Code:
lag = (pd.to_datetime(df['Reported Date']) - pd.to_datetime(df['Event Date'])).dt.days
sub = df[df['Major LOB'] == 'A&H']
avg = lag.loc[sub.index].mean()
result = f"Average reporting lag for A&H claims: {{avg:.1f}} days ({{len(sub):,}} claims)"

Question: "What percent of total incurred comes from Germany?"
Code:
total = df['Incurred USD'].sum()
de = df.loc[df['Country'] == 'Germany', 'Incurred USD'].sum()
pct = de / total * 100 if total else 0
result = f"Germany: ${{de:,.2f}} of ${{total:,.2f}} = {{pct:.2f}}%"

Question: "Only show me pending claims where the outstanding reserve > 50000 but no indemnity has been paid yet"
Code:
sub = df[(df['Claim Status Derived'] == 'Pending') & (df['Outstanding Reserve USD'] > 50000) & (df['Indemnity Paid USD'] == 0)]
result = f"{{len(sub):,}} matching claims. Total outstanding reserve: ${{sub['Outstanding Reserve USD'].sum():,.2f}}"

USER QUESTION: {question}

Write ONLY the Python code (no markdown, no explanation, no code fences):
"""


# ---------------------------------------------------------------------------
# Sandbox execution
# ---------------------------------------------------------------------------
class _TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise _TimeoutError("Code execution timed out")


def _validate_code(code: str) -> Optional[str]:
    """Check generated code for banned patterns. Returns error msg or None."""
    for pattern in _BANNED_PATTERNS:
        match = re.search(pattern, code)
        if match:
            return f"Blocked unsafe pattern: {match.group()}"
    return None


def _execute_sandboxed(code: str, df: pd.DataFrame) -> Tuple[Any, Optional[str]]:
    """Execute code in a restricted environment.

    Returns (result, error_msg). error_msg is None on success.
    """
    # Validate first
    err = _validate_code(code)
    if err:
        return None, err

    # Restricted globals — only pandas, numpy, and the DataFrame
    safe_globals = {
        "__builtins__": {
            "len": len,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sorted": sorted,
            "reversed": reversed,
            "min": min,
            "max": max,
            "sum": sum,
            "abs": abs,
            "round": round,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "isinstance": isinstance,
            "type": type,
            "True": True,
            "False": False,
            "None": None,
        },
        "pd": pd,
        "np": np,
        "df": df.copy(),  # read-only copy
    }

    local_ns: Dict[str, Any] = {}

    # Set timeout (Unix only)
    old_handler = None
    try:
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(_EXEC_TIMEOUT)
    except (AttributeError, ValueError):
        pass  # Windows or threading — skip timeout

    try:
        exec(code, safe_globals, local_ns)
        result = local_ns.get("result", None)
        if result is None:
            return None, "Code did not produce a `result` variable."

        # --- Tier 3 result validator ---
        # Reject outputs that are plausible but useless: NaN scalars, empty
        # Series/DataFrames, or strings that look like stack traces.
        try:
            if isinstance(result, (int, float, np.integer, np.floating)):
                if result != result:  # NaN check
                    return None, "Result was NaN — code likely had a divide-by-zero or bad filter."
            if isinstance(result, pd.Series) and len(result) == 0:
                return None, "Result Series was empty — filter matched 0 rows."
            if isinstance(result, pd.DataFrame) and len(result) == 0:
                return None, "Result DataFrame was empty — filter matched 0 rows."
            if isinstance(result, str):
                rl = result.strip().lower()
                if rl.startswith("traceback") or "error" in rl[:40] or rl in ("nan", "none"):
                    return None, f"Result looked like an error string: {result[:80]}"
        except Exception:
            pass  # Validator must never itself raise
        return result, None
    except _TimeoutError:
        return None, f"Code execution timed out ({_EXEC_TIMEOUT}s limit)."
    except Exception as e:
        return None, f"Execution error: {type(e).__name__}: {e}"
    finally:
        try:
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
        except (AttributeError, ValueError):
            pass


# ---------------------------------------------------------------------------
# Format result for display
# ---------------------------------------------------------------------------
def _format_result(result: Any) -> str:
    """Convert execution result to a display-friendly string."""
    if isinstance(result, str):
        return result

    if isinstance(result, (int, float, np.integer, np.floating)):
        if abs(result) >= 100:
            return f"**${result:,.2f}**" if abs(result) > 1 else f"**{result:,.4f}**"
        return f"**{result:,.4f}**"

    if isinstance(result, pd.Series):
        if len(result) > 20:
            result = result.head(20)
        lines = []
        for idx, val in result.items():
            if isinstance(val, (int, float, np.integer, np.floating)):
                if abs(val) >= 100:
                    lines.append(f"- {idx}: ${val:,.2f}")
                else:
                    lines.append(f"- {idx}: {val:,.4f}")
            else:
                lines.append(f"- {idx}: {val}")
        return "\n".join(lines)

    if isinstance(result, pd.DataFrame):
        if len(result) > 20:
            result = result.head(20)
        return result.to_markdown(index=True)

    return str(result)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def pandas_query(
    question: str,
    df: pd.DataFrame,
    col: dict,
    ollama_model: str = "gemma3:4b",
    ollama_host: str = "http://localhost:11434",
) -> Optional[str]:
    """Use LLM to generate and execute Pandas code for a question.

    Returns formatted answer string, or None if it fails.
    """
    try:
        import ollama as _ollama
    except ImportError:
        logger.warning("ollama not installed — pandas agent unavailable")
        return None

    # Build column info for the prompt
    columns = sorted(df.columns.tolist())
    dtypes = {c: str(df[c].dtype) for c in columns}

    # Sample values for categorical columns (helps LLM write correct filters)
    sample_values = {}
    for c in columns:
        if df[c].dtype == object:
            unique = df[c].dropna().unique()
            if len(unique) <= 10:
                sample_values[c] = ", ".join(str(v) for v in sorted(unique)[:8])

    prompt = _build_codegen_prompt(question, columns, dtypes, sample_values, len(df))

    # Ask LLM to generate code
    try:
        response = _ollama.chat(
            model=ollama_model,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_code = response["message"]["content"].strip()
    except Exception as e:
        logger.error(f"LLM code generation failed: {e}")
        return None

    # Strip markdown code fences if present
    if raw_code.startswith("```"):
        raw_code = re.sub(r"^```(?:python)?\s*\n?", "", raw_code)
        raw_code = re.sub(r"\n?```\s*$", "", raw_code)
    raw_code = raw_code.strip()

    # Auto-strip import lines — pd/np are already in the sandbox
    raw_code = "\n".join(
        line for line in raw_code.splitlines()
        if not re.match(r"^\s*import\s+", line) and not re.match(r"^\s*from\s+\S+\s+import\s+", line)
    ).strip()

    logger.info(f"Generated Pandas code:\n{raw_code}")

    # Execute in sandbox
    result, error = _execute_sandboxed(raw_code, df)

    if error:
        logger.warning(f"Pandas agent execution failed: {error}")
        # Retry once with error context
        retry_prompt = (
            f"{prompt}\n\n"
            f"Your previous code failed with: {error}\n"
            f"Fix the code and try again. Write ONLY the corrected Python code:"
        )
        try:
            response2 = _ollama.chat(
                model=ollama_model,
                messages=[{"role": "user", "content": retry_prompt}],
            )
            retry_code = response2["message"]["content"].strip()
            if retry_code.startswith("```"):
                retry_code = re.sub(r"^```(?:python)?\s*\n?", "", retry_code)
                retry_code = re.sub(r"\n?```\s*$", "", retry_code)
            retry_code = retry_code.strip()
            # Auto-strip import lines
            retry_code = "\n".join(
                line for line in retry_code.splitlines()
                if not re.match(r"^\s*import\s+", line) and not re.match(r"^\s*from\s+\S+\s+import\s+", line)
            ).strip()
            logger.info(f"Retry Pandas code:\n{retry_code}")
            result, error2 = _execute_sandboxed(retry_code, df)
            if error2:
                logger.warning(f"Retry also failed: {error2}")
                return None
        except Exception:
            return None

    if result is None:
        return None

    # Format and return
    formatted = _format_result(result)
    return (
        f"{formatted}\n\n"
        f"_Generated via Pandas Agent_"
    )
