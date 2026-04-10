# =============================================================================
# ai/rag_pipeline.py
# Phase 2 - Step 7: Full RAG Pipeline
# =============================================================================
# Responsibilities:
#   - Wire together: DataLoader → TextChunker → SearchEngine → LLM
#   - Detect question type (aggregation vs lookup vs trend)
#   - Route aggregation questions directly to summary stats
#     (faster + more accurate than embedding search for counts/totals)
#   - Route lookup/trend questions through FAISS → Llama3
#   - Return a structured response dict
# =============================================================================

import logging
import re
from typing import Dict, Any

import pandas as pd

logger = logging.getLogger("claims.rag")


# ---------------------------------------------------------------------------
# Question type detection
# ---------------------------------------------------------------------------

# Keywords that indicate the user wants aggregated numbers
AGGREGATION_KEYWORDS = [
    "how many", "total", "count", "sum", "average", "avg",
    "breakdown", "split", "percentage", "percent", "%",
    "overall", "across all", "in total",
]

# Keywords that indicate looking up a specific claim
LOOKUP_KEYWORDS = [
    "clm", "claim id", "claim number", "find claim",
    "tell me about claim", "show claim", "details of",
]


def detect_question_type(question: str) -> str:
    """
    Classify the user's question to route it to the right handler.

    Types:
      - "aggregation" : counts, totals, averages → answered from summary stats
      - "lookup"      : specific claim by ID → direct DataFrame lookup
      - "search"      : everything else → FAISS + LLM

    Args:
        question: User's plain English question.

    Returns:
        One of: "aggregation", "lookup", "search"
    """
    q_lower = question.lower()

    # Check for aggregation first (most common fast-path)
    if any(kw in q_lower for kw in AGGREGATION_KEYWORDS):
        return "aggregation"

    # Check for specific claim ID lookup (e.g. "CLM0000042")
    if re.search(r'\bclm\d+\b', q_lower) or any(kw in q_lower for kw in LOOKUP_KEYWORDS):
        return "lookup"

    # Default: semantic search through FAISS
    return "search"


# ---------------------------------------------------------------------------
# Aggregation handler — answers from pre-computed summary stats
# ---------------------------------------------------------------------------

def handle_aggregation(question: str, summary: dict, df=None, col=None) -> str:
    """
    Answer aggregation questions directly from the summary dict or DataFrame.
    Much faster than going through FAISS and the LLM.

    Handles:
      - "How many open claims are there?"
      - "What is the total claim value?"
      - "Give me total value by ClaimType"
      - "Show me the breakdown by region"

    Args:
        question: User's question.
        summary:  Pre-computed summary from ClaimsDataLoader.
        df:       Full DataFrame for group-by calculations.
        col:      Column name mapping from config.

    Returns:
        A formatted answer string.
    """
    q = question.lower()

    # --- Count BY region ---
    if df is not None and col is not None and (
        ("how many" in q or "count" in q) and "region" in q
    ):
        result = df.groupby(col["region"])[col["claim_id"]].count().sort_values(ascending=False)
        lines  = [f"- {r}: {c:,}" for r, c in result.items()]
        return "**Claims Count by Region:**\n" + "\n".join(lines)

    # --- Count BY type ---
    if df is not None and col is not None and (
        ("how many" in q or "count" in q) and "type" in q
    ):
        result = df.groupby(col["claim_type"])[col["claim_id"]].count().sort_values(ascending=False)
        lines  = [f"- {t}: {c:,}" for t, c in result.items()]
        return "**Claims Count by Claim Type:**\n" + "\n".join(lines)

    # --- Average BY type ---
    if df is not None and col is not None and (
        ("average" in q or "avg" in q) and "type" in q
    ):
        result = df.groupby(col["claim_type"])[col["claim_amount"]].mean().sort_values(ascending=False)
        lines  = [f"- {t}: £{v:,.2f}" for t, v in result.items()]
        return "**Average Claim Value by Claim Type:**\n" + "\n".join(lines)

    # --- Average BY region ---
    if df is not None and col is not None and (
        ("average" in q or "avg" in q) and "region" in q
    ):
        result = df.groupby(col["region"])[col["claim_amount"]].mean().sort_values(ascending=False)
        lines  = [f"- {r}: £{v:,.2f}" for r, v in result.items()]
        return "**Average Claim Value by Region:**\n" + "\n".join(lines)

    # --- Total value / amount BY claim type ---
    if df is not None and col is not None and (
        "by claimtype" in q or "by claim type" in q or "per type" in q or
        ("type" in q and ("total" in q or "value" in q or "amount" in q))
    ):
        result = df.groupby(col["claim_type"])[col["claim_amount"]].sum().sort_values(ascending=False)
        lines  = [f"- {t}: £{v:,.2f}" for t, v in result.items()]
        return "**Total Claim Value by Claim Type:**\n" + "\n".join(lines)

    # --- Total value / amount BY region ---
    if df is not None and col is not None and (
        "by region" in q or "per region" in q or
        ("region" in q and ("total" in q or "value" in q or "amount" in q))
    ):
        result = df.groupby(col["region"])[col["claim_amount"]].sum().sort_values(ascending=False)
        lines  = [f"- {r}: £{v:,.2f}" for r, v in result.items()]
        return "**Total Claim Value by Region:**\n" + "\n".join(lines)

    # --- Total value / amount BY status ---
    if df is not None and col is not None and (
        "by status" in q or "per status" in q or
        ("status" in q and ("total" in q or "value" in q or "amount" in q))
    ):
        result = df.groupby(col["status"])[col["claim_amount"]].sum().sort_values(ascending=False)
        lines  = [f"- {s}: £{v:,.2f}" for s, v in result.items()]
        return "**Total Claim Value by Status:**\n" + "\n".join(lines)

    # --- Status count questions ---
    if "how many" in q or "count" in q:
        for status in ["open", "closed", "pending", "rejected", "under review"]:
            if status in q:
                count = summary["status_counts"].get(status.title(), 0)
                return f"There are **{count:,}** {status.title()} claims in the current dataset."
        if "claim" in q:
            return f"There are **{summary['total_claims']:,}** claims in the current dataset."

    # --- Total value questions ---
    if "total" in q and ("value" in q or "amount" in q or "claim" in q):
        return (
            f"The total claim value across all {summary['total_claims']:,} claims is "
            f"**£{summary['total_claim_amount']:,.2f}**.\n\n"
            f"- Total paid: £{summary['total_paid_amount']:,.2f}\n"
            f"- Total reserves: £{summary['total_reserve_amount']:,.2f}"
        )

    # --- Average questions ---
    if "average" in q or "avg" in q:
        if "day" in q or "open" in q:
            return f"The average number of days a claim is open is **{summary['avg_days_open']}** days."
        return f"The average claim value is **£{summary['avg_claim_amount']:,.2f}**."

    # --- Region breakdown ---
    if "region" in q and "breakdown" in q:
        lines = [f"- {r}: {c:,}" for r, c in summary["region_counts"].items()]
        return "**Claims by Region:**\n" + "\n".join(lines)

    # --- Status breakdown ---
    if "status" in q or "breakdown" in q:
        lines = [f"- {s}: {c:,}" for s, c in summary["status_counts"].items()]
        return "**Claims by Status:**\n" + "\n".join(lines)

    # --- Type breakdown ---
    if "type" in q:
        lines = [f"- {t}: {c:,}" for t, c in summary["type_counts"].items()]
        return "**Claims by Type:**\n" + "\n".join(lines)

    # --- Fallback full summary ---
    return (
        f"**Claims Summary** (as of {summary.get('data_loaded_at', 'unknown')}):\n\n"
        f"- Total claims: {summary['total_claims']:,}\n"
        f"- Total value: £{summary['total_claim_amount']:,.2f}\n"
        f"- Total paid: £{summary['total_paid_amount']:,.2f}\n"
        f"- Total reserves: £{summary['total_reserve_amount']:,.2f}\n"
        f"- Average claim: £{summary['avg_claim_amount']:,.2f}\n"
        f"- Average days open: {summary['avg_days_open']} days\n"
        f"- Date range: {summary['date_range_start']} → {summary['date_range_end']}"
    )


# ---------------------------------------------------------------------------
# Lookup handler — direct DataFrame lookup by Claim ID
# ---------------------------------------------------------------------------

def handle_lookup(
    question: str,
    df: pd.DataFrame,
    col: dict,
) -> str:
    """
    Look up a specific claim by its ID directly in the DataFrame.

    Args:
        question: User's question (expected to contain a claim ID).
        df:       The full claims DataFrame.
        col:      Column name mapping from config.

    Returns:
        Formatted claim detail string, or not-found message.
    """
    # Extract claim ID from question (e.g. CLM0000042)
    match = re.search(r'\bclm\d+\b', question, re.IGNORECASE)
    if not match:
        return "I couldn't find a Claim ID in your question. Please include the claim ID (e.g. CLM0000042)."

    claim_id = match.group(0).upper()
    row = df[df[col["claim_id"]] == claim_id]

    if row.empty:
        return f"Claim **{claim_id}** was not found in the current dataset."

    r = row.iloc[0]

    def s(field):
        val = r.get(col.get(field, ""), "N/A")
        return "N/A" if pd.isna(val) else str(val)

    def c(field):
        try:
            return f"£{float(r.get(col.get(field, ''), 0)):,.2f}"
        except Exception:
            return "N/A"

    return (
        f"**Claim {claim_id}**\n\n"
        f"- Status: {s('status')}\n"
        f"- Type: {s('claim_type')}\n"
        f"- Claimant: {s('claimant_name')}\n"
        f"- Region: {s('region')}\n"
        f"- Submitted: {s('submitted_date')[:10]}\n"
        f"- Closed: {s('closed_date')[:10] if s('closed_date') != 'N/A' else 'Still open'}\n"
        f"- Claim Amount: {c('claim_amount')}\n"
        f"- Paid Amount: {c('paid_amount')}\n"
        f"- Reserve: {c('reserve_amount')}\n"
        f"- Days Open: {s('days_open')}"
    )


# ---------------------------------------------------------------------------
# Main RAG Pipeline class
# ---------------------------------------------------------------------------

class RAGPipeline:
    """
    Orchestrates the full question-answering pipeline.

    Flow for aggregation questions:
        question → detect_type → handle_aggregation → answer

    Flow for lookup questions:
        question → detect_type → handle_lookup → answer

    Flow for search questions:
        question → detect_type → FAISS search → retrieve rows → LLM → answer

    Usage:
        pipeline = RAGPipeline(loader, search_engine, llm)
        response = pipeline.ask("How many open claims are in London?")
        print(response["answer"])
    """

    def __init__(self, loader, search_engine, llm):
        """
        Args:
            loader:        ClaimsDataLoader instance (already loaded)
            search_engine: ClaimsSearchEngine instance (already built)
            llm:           ClaimsLLM instance
        """
        self.loader        = loader
        self.search_engine = search_engine
        self.llm           = llm

    # ------------------------------------------------------------------
    def ask(self, question: str) -> Dict[str, Any]:
        """
        Answer a natural language question about claims data.

        Args:
            question: Plain English question from the user.

        Returns:
            Dict with keys:
              - "answer"        : the answer string
              - "question_type" : "aggregation" | "lookup" | "search"
              - "sources"       : list of matched claim IDs (for search)
              - "error"         : error message if something went wrong
        """
        if not question or not question.strip():
            return {"answer": "Please ask a question.", "question_type": "none", "sources": []}

        question = question.strip()
        logger.info(f"Question received: '{question}'")

        question_type = detect_question_type(question)
        logger.info(f"Question type: {question_type}")

        # ---- Aggregation: answer from summary stats (fast) ----
        if question_type == "aggregation":
            answer = handle_aggregation(question, self.loader.summary, self.loader.df, self.loader.col)
            return {"answer": answer, "question_type": "aggregation", "sources": []}

        # ---- Lookup: direct DataFrame search by claim ID ----
        if question_type == "lookup":
            answer = handle_lookup(question, self.loader.df, self.loader.col)
            return {"answer": answer, "question_type": "lookup", "sources": []}

        # ---- Search: FAISS + LLM ----
        if not self.search_engine.is_ready:
            return {
                "answer": "⚠️ Search engine is not ready. Please wait for the index to build.",
                "question_type": "search",
                "sources": [],
            }

        # 1. Find relevant chunks via FAISS
        matched_chunks = self.search_engine.search(question)
        if not matched_chunks:
            return {
                "answer": "I couldn't find any relevant claims for that question.",
                "question_type": "search",
                "sources": [],
            }

        # 2. Retrieve full rows from DataFrame
        from data.text_chunker import retrieve_rows_from_chunks
        context_rows = retrieve_rows_from_chunks(self.loader.df, matched_chunks)

        # 3. Send to LLM
        answer  = self.llm.answer(
            question     = question,
            context_rows = context_rows,
            col          = self.loader.col,
            summary      = self.loader.summary,
        )

        sources = [c["claim_id"] for c in matched_chunks]
        return {"answer": answer, "question_type": "search", "sources": sources}

    # ------------------------------------------------------------------
    def rebuild(self):
        """
        Reload data and rebuild the search index.
        Called on manual or scheduled refresh.
        """
        logger.info("RAG pipeline rebuild triggered")
        self.loader.reload()

        from data.text_chunker import dataframe_to_chunks
        chunks = dataframe_to_chunks(
            self.loader.df,
            self.loader.col,
            chunk_size=self.loader.config["data"]["chunk_size"],
        )
        self.search_engine.rebuild(chunks)
        logger.info("RAG pipeline rebuild complete ✓")
