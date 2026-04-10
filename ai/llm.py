# =============================================================================
# ai/llm.py
# Phase 2 - Step 6: Ollama Llama3 Local LLM Integration
# =============================================================================
# Responsibilities:
#   - Connect to the local Ollama server
#   - Check Llama3 is available
#   - Send a prompt (question + context rows) to Llama3
#   - Return a clean plain-English answer
#   - Handle Ollama not running gracefully
# =============================================================================

import logging
import time
from typing import List, Dict, Any

import pandas as pd

logger = logging.getLogger("claims.llm")


# ---------------------------------------------------------------------------
# Ollama connection check
# ---------------------------------------------------------------------------

def check_ollama_running(host: str = "http://localhost:11434") -> bool:
    """
    Verify that the Ollama server is running and reachable.

    Args:
        host: Ollama server URL from config.

    Returns:
        True if Ollama is running, False otherwise.
    """
    try:
        import ollama
        client = ollama.Client(host=host)
        client.list()   # lightweight ping
        logger.info(f"Ollama is running at {host} ✓")
        return True
    except Exception as e:
        logger.warning(f"Ollama not reachable at {host}: {e}")
        return False


def check_model_available(model_name: str, host: str) -> bool:
    """
    Check if a specific model has been pulled in Ollama.

    Args:
        model_name: e.g. "llama3"
        host:       Ollama server URL.

    Returns:
        True if the model is available locally.
    """
    try:
        import ollama
        client = ollama.Client(host=host)
        models = client.list()
        available = [m.model for m in models.models]
        # Ollama appends :latest so check with startswith
        found = any(m.startswith(model_name) for m in available)
        if found:
            logger.info(f"Model '{model_name}' is available ✓")
        else:
            logger.warning(
                f"Model '{model_name}' not found. "
                f"Available: {available}. "
                f"Run: ollama pull {model_name}"
            )
        return found
    except Exception as e:
        logger.error(f"Could not check model availability: {e}")
        return False


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_prompt(
    question: str,
    context_rows: pd.DataFrame,
    col: dict,
    summary: dict,
) -> str:
    """
    Build the full prompt sent to Llama3.

    Structure:
      - System instruction: tells the LLM its role and rules
      - Summary stats: high-level numbers always available
      - Context rows: the specific claims retrieved by FAISS
      - User question

    The LLM never sees the whole DataFrame — only what FAISS
    deemed relevant, keeping the prompt small and fast.

    Args:
        question:     The user's plain English question.
        context_rows: DataFrame rows returned by FAISS search.
        col:          Column name mapping from config.
        summary:      Pre-computed summary stats dict.

    Returns:
        A formatted prompt string.
    """

    # --- System instruction ---
    system = """You are a Claims Data Assistant for an insurance company.
You answer questions about claims data clearly and concisely.
Rules:
- Only use the data provided below. Do not invent figures.
- If the answer is not in the data, say so honestly.
- Format currency as £ with comma separators.
- Keep answers brief and professional.
- If asked for a list or table, format it clearly.
"""

    # --- Summary block (always included) ---
    summary_block = f"""
OVERALL DATA SUMMARY (as of {summary.get('data_loaded_at', 'unknown')}):
- Total claims in dataset: {summary.get('total_claims', 'N/A'):,}
- Total claim value: £{summary.get('total_claim_amount', 0):,.2f}
- Total paid: £{summary.get('total_paid_amount', 0):,.2f}
- Total reserves: £{summary.get('total_reserve_amount', 0):,.2f}
- Average claim value: £{summary.get('avg_claim_amount', 0):,.2f}
- Average days open: {summary.get('avg_days_open', 'N/A')} days
- Status breakdown: {summary.get('status_counts', {})}
- Region breakdown: {summary.get('region_counts', {})}
- Claim type breakdown: {summary.get('type_counts', {})}
- Date range: {summary.get('date_range_start', '')} to {summary.get('date_range_end', '')}
"""

    # --- Context rows block ---
    if context_rows is not None and len(context_rows) > 0:
        context_lines = ["RELEVANT CLAIMS RETRIEVED:"]
        for _, row in context_rows.iterrows():
            def s(field):
                val = row.get(col.get(field, ""), "N/A")
                return "N/A" if pd.isna(val) else str(val)

            def c(field):
                try:
                    return f"£{float(row.get(col.get(field, ''), 0)):,.2f}"
                except Exception:
                    return "N/A"

            line = (
                f"- Claim {s('claim_id')}: {s('status')} {s('claim_type')} | "
                f"Claimant: {s('claimant_name')} | Region: {s('region')} | "
                f"Submitted: {s('submitted_date')[:10] if s('submitted_date') != 'N/A' else 'N/A'} | "
                f"Amount: {c('claim_amount')} | Paid: {c('paid_amount')} | "
                f"Reserve: {c('reserve_amount')} | Days open: {s('days_open')}"
            )
            context_lines.append(line)
        context_block = "\n".join(context_lines)
    else:
        context_block = "RELEVANT CLAIMS RETRIEVED: None found for this query."

    # --- Assemble full prompt ---
    prompt = f"""{system}
{summary_block}
{context_block}

USER QUESTION: {question}

ANSWER:"""

    return prompt


# ---------------------------------------------------------------------------
# LLM caller
# ---------------------------------------------------------------------------

def ask_llm(
    question: str,
    context_rows: pd.DataFrame,
    col: dict,
    summary: dict,
    model_name: str = "llama3",
    host: str = "http://localhost:11434",
) -> str:
    """
    Send a question + context to Llama3 via Ollama and return the answer.

    Args:
        question:     User's question.
        context_rows: Relevant DataFrame rows from FAISS search.
        col:          Column name mapping from config.
        summary:      Pre-computed summary stats.
        model_name:   Ollama model name from config.
        host:         Ollama server URL from config.

    Returns:
        Plain English answer string from Llama3.
        Falls back to a helpful error message if Ollama is unavailable.
    """
    try:
        import ollama
        client = ollama.Client(host=host)

        prompt = build_prompt(question, context_rows, col, summary)

        logger.info(f"Sending question to {model_name}: '{question[:60]}...'")
        start = time.time()

        response = client.generate(
            model  = model_name,
            prompt = prompt,
            options = {
                "temperature": 0.1,    # Low = more factual, less creative
                "num_predict": 512,    # Max tokens in response
            },
        )

        elapsed = round(time.time() - start, 1)
        answer  = response.response.strip()
        logger.info(f"LLM responded in {elapsed}s")

        return answer

    except ImportError:
        return "❌ ollama package not installed. Run: pip install ollama"
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return (
            f"⚠️ Could not reach Ollama. Make sure it is running.\n\n"
            f"Start it with: ollama serve\n"
            f"Then check: ollama list\n\n"
            f"Error detail: {str(e)}"
        )


# ---------------------------------------------------------------------------
# ClaimsLLM — thin wrapper for clean integration with RAG pipeline
# ---------------------------------------------------------------------------

class ClaimsLLM:
    """
    Wrapper around the Ollama Llama3 integration.

    Usage:
        llm = ClaimsLLM(config)
        ok  = llm.check()
        ans = llm.answer(question, context_rows, col, summary)
    """

    def __init__(self, config: dict):
        self.ai_cfg     = config["ai"]
        self.model_name = self.ai_cfg["ollama_model"]
        self.host       = self.ai_cfg["ollama_host"]

    def check(self) -> bool:
        """
        Check Ollama is running and the model is available.

        Returns:
            True if everything is ready.
        """
        if not check_ollama_running(self.host):
            return False
        return check_model_available(self.model_name, self.host)

    def answer(
        self,
        question: str,
        context_rows: pd.DataFrame,
        col: dict,
        summary: dict,
    ) -> str:
        """
        Generate an answer to a question using retrieved context rows.

        Args:
            question:     User's plain English question.
            context_rows: Relevant rows from FAISS search.
            col:          Column name mapping from config.
            summary:      Pre-computed summary stats dict.

        Returns:
            Plain English answer from Llama3.
        """
        return ask_llm(
            question     = question,
            context_rows = context_rows,
            col          = col,
            summary      = summary,
            model_name   = self.model_name,
            host         = self.host,
        )
