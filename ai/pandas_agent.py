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
    # Match only as function calls, not bare words — the string literal 'Open'
    # (LOB status) and the word "open" appearing in f-string output used to
    # false-positive against `\bopen\b`.
    r"\bexec\s*\(",
    r"\beval\s*\(",
    r"\bopen\s*\(",
    r"\bcompile\s*\(",
    r"\bos\.\b",
    r"\bsys\.\b",
    r"\bsubprocess\b",
    r"\bshutil\b",
    r"\bglobals\b",
    r"\blocals\b",
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

    return f"""# ROLE & MISSION
You translate jargon-heavy P&C insurance questions from Claims Adjusters and
Claims Directors into precise, error-free Pandas code — OR, when the question
is ambiguous, you refuse to guess and ask ONE clarifying question instead.

# THE USERS
1. Claims Adjuster (tactical): queue, SLA breaches, aging, litigation risk.
   Asks: "What's in my queue?", "Which claims are aging past the 14-day window?"
2. Claims Director (strategic): financial exposure, leakage, CAT aggregation,
   cycle times, STP/fast-track rates. Asks: "YoY loss ratio?", "Reserve
   development on Auto?", "Subrogation we missed?"

DATAFRAME INFO:
- Variable name: `df` (already loaded, {row_count:,} rows)
- Columns and types:
{col_info}

=================================================================
STEP 0 — CLARIFY FIRST, CODE SECOND   (HARD RULE — READ FIRST)
=================================================================
If the question contains ANY of the traps below, DO NOT write code.
Instead, reply with exactly ONE line and nothing else:

    CLARIFY: <one short question for the user>

No code, no markdown, no explanation before or after.

THE TRAPS (intercept these):

1. The DATE trap — any year, quarter, or month without a date TYPE.
   Examples: "claims in 2023", "Q1 2020", "last month", "2024 losses".
   → CLARIFY: Are you referring to claims Reported in 2023, or claims with
     an Event Date (Date of Loss) in 2023?

2. The PAID trap — "paid" / "total paid" / "payout" without a bucket.
   → CLARIFY: Do you want Total Indemnity Paid, Total Expense Paid (ALAE),
     or the Combined Total Paid?

3. The VALUE trap — "total value" / "amount" / "exposure" without a basis.
   → CLARIFY: Do you mean Total Incurred (Paid + Reserve − Recoveries),
     Paid only, or Outstanding Reserve only?

4. The LOCATION trap — "by location" / "where".
   → CLARIFY: Do you want Location of Loss (where the event happened), or
     the Handling Claim Office?

5. The TYPE trap — "by type".
   → CLARIFY: Major LOB, Minor LOB, or Injury / Damage type?

6. The LIST trap — user asks for a "list" but the count is massive.
   Write `.head(10)` and state the total, e.g.
   "There are 5,000 total claims. Here is a sample of the top 10 by Reserve:".

=================================================================
THE P&C DATA DICTIONARY  (apply when writing code)
=================================================================

## 1. THE FINANCIAL ENGINE (Money rules — do not guess formulas)
Default to USD columns. Never invent columns.
- Indemnity Paid (Loss Paid)   — money to the claimant/insured for the loss.
- Expense Paid (ALAE)          — vendor costs: defense attorneys, IAs,
                                 forensics.  Synonyms: Legal Spend, Vendor Cost.
- Outstanding Reserve (O/S)    — money set aside for future payments.
- Recoveries (Subro/Salvage)   — money clawed back. CRITICAL: recoveries
                                 REDUCE total cost.
- Total Incurred (Ultimate Cost) = (Indemnity Paid + Expense Paid)
                                   + Outstanding Reserve - Recoveries
  "Total Claim Value" / "Exposure" / "Financial Hit" ≡ Incurred.

## 2. TEMPORAL & DATE MATH (Time rules)
- Event Date (Date of Loss, DOL)  — when the accident actually happened.
- Reported Date                   — when the carrier was notified.
                                    Synonyms: New Claims, Claims Received, Inflow, FNOL.
- Accident Year (AY) — group by year of Event Date.
- Report Year  (RY) — group by year of Reported Date.
- Underwriting Year (UWY) — year the policy was written.

Derived metrics:
- Reporting Lag (days) = (pd.to_datetime(df['Reported Date'])
                          - pd.to_datetime(df['Event Date'])).dt.days
  Business: late reporting → higher fraud/litigation risk.
- Cycle Time / Days Open = (pd.to_datetime(df['Claim Closed Date'])
                            - pd.to_datetime(df['Reported Date'])).dt.days

Quarter/month filtering — use datetime accessors. NEVER pass 'Q1' as a
resample freq (raises ValueError: Invalid frequency).
    rd = pd.to_datetime(df['Reported Date'], errors='coerce')
    q1_2020 = df[(rd.dt.year == 2020) & (rd.dt.quarter == 1)]

## 3. LIFECYCLE & STATUS
- "Active" / "Pending" workload → Claim Status Derived IN ['Open','Pending','Reopened']
- "Closed" claims → Claim Status Derived == 'Closed'
- "Reopened" claims → high reopen rate = poor initial handling (Director KPI).

## 4. CLASSIFICATIONS
- LOB (Line of Business): "LOB" ≡ Major LOB unless specified.
  Short-tail: Auto, Property (close fast, high volume).
  Long-tail:  Casualty, Liability, Workers Comp (open for years, heavy legal).
- Injury Types (Condition Injury Damage Name):
  BI = Bodily Injury (severe cost driver: Fatality, Severe, Neck/Back).
  PD = Property Damage (cheaper, faster).
- CAT (Catastrophe Code): aggregate hurricanes, wildfires, etc.
  "CAT exposure" → group by this code.

## 5. AUTOMATION / TRIAGE
- MAR Fast Track Flag:
    'Y' = Straight-Through Processing (STP) / fast-tracked.
    'N' = Manual adjuster review.
  STP Rate = count('Y') / total * 100.

## 6. COMPUTATION RULES
- Percentage / ratio → (numerator_sum / total_sum) * 100, formatted with '%'.
- Filter BEFORE aggregating: df[mask].groupby(...).
- Derived-metric averages: compute the metric first, then .mean().
- YTD = pd.Timestamp.today().year.

=================================================================
CODE-WRITING RULES  (only if no clarification needed)
=================================================================
1. Write ONLY Python using pandas (`pd`) and numpy (`np`). They are ALREADY
   imported. NO import statements.
2. `df` is ALREADY loaded. DO NOT reassign df.
3. Store the final answer in a variable called `result`.
4. `result` ∈ {{string, number, pandas Series, small DataFrame}}.
5. Do NOT mutate `df`. Use `.copy()` when needed.
6. Do NOT use print, import, exec, eval, open, os, sys.
7. Currency formatting: f"${{val:,.2f}}".
8. 1 to 10 lines.
9. If the available columns genuinely cannot answer the (unambiguous) question:
   result = "I cannot answer this question with the available data columns."
10. NEVER invent columns. Only reference columns listed above.

=================================================================
OUTPUT FORMAT RULES  (CRITICAL — prevents LeetCode-bleed bugs)
=================================================================
A. Write procedural, TOP-LEVEL Python. No indentation at the first line.
B. DO NOT wrap code in any class or function. NEVER write `class Solution:`,
   `public class`, `def solve(self):`, `if __name__ == '__main__':`.
   These are Java/LeetCode patterns — they are hallucinations. Stop.
C. DO NOT output markdown code fences (```python ... ```). Output ONLY the
   raw Python text.
D. Every f-string must have matched braces and quotes. The format spec goes
   INSIDE the braces: f"{{val:,}}"   not   f"{{val:,"}}"
E. The final statement MUST assign to a variable named exactly `result`.
F. Do not include explanatory comments or prose lines between code lines.

EXAMPLES:

Question: "What's the trend in new claims between Q1 2020 and Q1 2021?"
Response (single line, no code):
CLARIFY: "New claims" usually means claims reported (Reported Date) in that quarter — can you confirm you want claims REPORTED in Q1 2020 vs Q1 2021, and not claims whose accident occurred in those quarters?

Question: "How much did we pay in 2023?"
Response:
CLARIFY: Do you mean Indemnity Paid, Expense Paid, or combined (Indemnity + Expense) Paid in 2023? And by "in 2023" do you mean claims with an Event Date in 2023 or Reported in 2023?

Question: "Show me claims by location"
Response:
CLARIFY: Do you want to group by Location of Loss (where the event happened) or by Handling Claim Office?

Question: "New claims reported in Q1 2020 vs Q1 2021"  (unambiguous — has 'reported')
Code:
rd = pd.to_datetime(df['Reported Date'], errors='coerce')
q1_2020 = int(((rd.dt.year == 2020) & (rd.dt.quarter == 1)).sum())
q1_2021 = int(((rd.dt.year == 2021) & (rd.dt.quarter == 1)).sum())
delta = q1_2021 - q1_2020
direction = "up" if delta > 0 else ("down" if delta < 0 else "flat")
result = f"New claims reported: Q1 2020 = {{q1_2020:,}}, Q1 2021 = {{q1_2021:,}} ({{direction}} {{abs(delta):,}})"

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

Question: "Total nominal reserve for Open claims, excluding the Casualty and Auto LOBs"
Code:
# EXCLUSION = negate isin() on the excluded list. Do NOT compute without the filter.
excluded = ['Casualty', 'Auto']
sub = df[(df['Claim Status Derived'] == 'Open') & (~df['Major LOB'].isin(excluded))]
result = f"Total Nominal Reserve (Open, excl. {{excluded}}): ${{sub['Nominal Reserve'].sum():,.2f}} across {{len(sub):,}} claims"

Question: "Find claims that are either Closed with no Paid Indemnity OR Open with over 100k in Nominal Reserve"
Code:
# DISJUNCTION = use | (bitwise OR) with parenthesised branches, then combine.
branch1 = (df['Claim Status Derived'] == 'Closed') & (df['Indemnity Paid USD'] == 0)
branch2 = (df['Claim Status Derived'] == 'Open')   & (df['Nominal Reserve']   > 100000)
sub = df[branch1 | branch2]
result = f"{{len(sub):,}} matching claims ({{branch1.sum():,}} closed-unpaid + {{branch2.sum():,}} open-high-reserve)"

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


def clean_llm_code(raw_code: str) -> str:
    """Strip hallucinated wrappers from LLM output before execution.

    Handles three common failure modes observed in production logs:
      1. Markdown code fences — ```python ... ```
      2. LeetCode-bleed wrappers — `public class Solution:` / `class Solution:`
         / `def solve(self):` / `if __name__ == "__main__":` — the model wraps
         valid Pandas code inside Java-style boilerplate which is not valid
         Python and crashes `exec`.
      3. Stray non-ASCII / junk tokens before the first real line
         (e.g. `super()`, `загадка`, `大利`).
    """
    code = (raw_code or "").strip()
    if not code:
        return code

    # 1. Strip markdown fences (opening + closing)
    if code.startswith("```"):
        code = re.sub(r"^```(?:python|py)?\s*\n?", "", code, count=1)
        code = re.sub(r"\n?```\s*$", "", code, count=1).strip()

    # 2. If the model wrapped code in class/function boilerplate, unwrap it.
    #    Strategy: drop any line that is pure boilerplate, and dedent the body.
    _BOILERPLATE_RE = re.compile(
        r"^\s*(public\s+class|private\s+class|class\s+\w+\s*[:\(]|"
        r"def\s+(solve|solution|main|run)\s*\(|"
        r"if\s+__name__\s*==\s*['\"]__main__['\"]\s*:)",
        re.IGNORECASE,
    )
    lines = code.splitlines()
    if any(_BOILERPLATE_RE.match(ln) for ln in lines):
        kept = [ln for ln in lines if not _BOILERPLATE_RE.match(ln)]
        # Dedent: strip the minimum common leading whitespace across non-empty lines
        non_empty = [ln for ln in kept if ln.strip()]
        if non_empty:
            min_indent = min(len(ln) - len(ln.lstrip()) for ln in non_empty)
            kept = [ln[min_indent:] if len(ln) >= min_indent else ln for ln in kept]
        # Drop stray `self.`/`return` artefacts left by unwrapping a method.
        kept = [re.sub(r"^\s*return\s+", "", ln) for ln in kept]
        kept = [ln.replace("self.", "") for ln in kept]
        code = "\n".join(kept).strip()

    # 3. Drop leading junk lines that aren't valid Python identifiers/keywords.
    #    A valid Pandas-code line starts with a word char, `#`, or whitespace.
    #    Non-ASCII-only tokens (e.g. "загадка", "大利") are clearly model noise.
    out = []
    started = False
    for ln in code.splitlines():
        if not started:
            stripped = ln.strip()
            if not stripped:
                continue
            if not re.match(r"^[A-Za-z_#]", stripped):
                continue  # skip until the first plausibly-Python line
            started = True
        out.append(ln)
    return "\n".join(out).strip()


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
    ollama_model: str = "llama3.2:3b",
    ollama_host: str = "http://localhost:11434",
    llm_timeout: int = 90,
) -> Optional[str]:
    """Use LLM to generate and execute Pandas code for a question.

    Returns formatted answer string, or None if it fails.
    `llm_timeout` is a hard wall-clock cap (seconds) on each ollama call —
    prevents a stalled LLM from freezing the whole pipeline.
    """
    try:
        import ollama as _ollama
    except ImportError:
        logger.warning("ollama not installed — pandas agent unavailable")
        return None

    # Client with hard timeout. Without this, ollama.chat() can hang for
    # 30+ minutes on complex prompts.
    _client = _ollama.Client(host=ollama_host, timeout=llm_timeout)

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
        response = _client.chat(
            model=ollama_model,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_code = response["message"]["content"].strip()
    except Exception as e:
        logger.error(f"LLM code generation failed (timeout={llm_timeout}s): {e}")
        return None

    # Strip markdown fences + LeetCode-bleed wrappers + junk prefix tokens.
    raw_code = clean_llm_code(raw_code)

    # --- Clarification short-circuit ---
    # If the LLM decided the question is ambiguous and emitted a CLARIFY: line
    # ANYWHERE in its output, do NOT execute anything. The LLM sometimes
    # prefixes the CLARIFY line with stray tokens (super(), odd unicode, etc.)
    # so we search line-by-line rather than anchoring at start-of-string.
    for _ln in raw_code.splitlines():
        m = re.match(r"\s*CLARIFY\s*:\s*(.+)", _ln, re.IGNORECASE)
        if m:
            question_to_user = m.group(1).strip().strip('"').strip("'")
            logger.info(f"Pandas agent requested clarification: {question_to_user}")
            return f"__CLARIFY__:{question_to_user}"

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
        # Retry once with error context.
        # IMPORTANT: repeat the original question AND the failing code up
        # front so the LLM doesn't drift to an unrelated answer. Also pin
        # the contract (must assign `result`, no markdown, no wrappers).
        retry_prompt = (
            f"You are fixing Python/Pandas code for the question below.\n"
            f"Do NOT answer a different question. Do NOT invent new metrics.\n\n"
            f"ORIGINAL QUESTION:\n{question}\n\n"
            f"YOUR PREVIOUS CODE:\n{raw_code}\n\n"
            f"IT FAILED WITH:\n{error}\n\n"
            f"CONTRACT:\n"
            f"- Fix the same question — not a new one.\n"
            f"- The final line must assign to `result` "
            f"(e.g. `result = ...`).\n"
            f"- Return ONLY Python code. No markdown fences. "
            f"No class/function wrappers.\n\n"
            f"CORRECTED CODE:"
        )
        try:
            response2 = _client.chat(
                model=ollama_model,
                messages=[{"role": "user", "content": retry_prompt}],
            )
            retry_code = response2["message"]["content"]
            retry_code = clean_llm_code(retry_code)
            # Retry output can also be a CLARIFY — honour it.
            for _ln in retry_code.splitlines():
                m = re.match(r"\s*CLARIFY\s*:\s*(.+)", _ln, re.IGNORECASE)
                if m:
                    return f"__CLARIFY__:{m.group(1).strip().strip(chr(34)).strip(chr(39))}"
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
