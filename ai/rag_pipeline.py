# =============================================================================
# ai/rag_pipeline.py
# RAG Pipeline with QueryAnalyzer-based intent routing
# =============================================================================
# Flow:
#   QueryAnalyzer.analyze(question)
#     -> route by intent: aggregation | lookup | search
#   Aggregation -> handle_aggregation (summary stats, entity-aware)
#   Lookup      -> handle_lookup (direct DataFrame row by claim_id)
#   Search      -> pre-filter by entities -> FAISS -> score threshold -> LLM
# =============================================================================

import logging
import re
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from ai.query_analyzer import QueryAnalyzer

logger = logging.getLogger("claims.rag")


# ---------------------------------------------------------------------------
# Aggregation handler
# ---------------------------------------------------------------------------

def handle_aggregation(
    question: str,
    summary: dict,
    df: pd.DataFrame = None,
    col: dict = None,
    entities: dict = None,
) -> str:
    """Answer aggregation questions from summary stats or DataFrame group-bys.

    Uses *entities* (from QueryAnalyzer) for entity-aware filtering when a
    specific status, region, or type is mentioned.

    Args:
        question:  User question.
        summary:   Pre-computed summary from ClaimsDataLoader.
        df:        Full DataFrame (optional, needed for group-by).
        col:       Column mapping dict.
        entities:  Dict with keys status/region/claim_type/high_value from
                   QueryAnalyzer (may be None).

    Returns:
        Formatted answer string using $ for currency.
    """
    q = question.lower()
    ent = entities or {}

    # --- Entity-aware status count ---
    if ent.get("status") and ("how many" in q or "count" in q):
        status_val = ent["status"]
        count = summary["status_counts"].get(status_val, 0)
        return f"There are **{count:,}** {status_val} claims in the current dataset."

    # --- Count BY region ---
    if df is not None and col is not None and (
        ("how many" in q or "count" in q) and "region" in q
    ):
        result = df.groupby(col["region"])[col["claim_id"]].count().sort_values(ascending=False)
        lines = [f"- {r}: {c:,}" for r, c in result.items()]
        return "**Claims Count by Region:**\n" + "\n".join(lines)

    # --- Count BY type ---
    if df is not None and col is not None and (
        ("how many" in q or "count" in q) and "type" in q
    ):
        result = df.groupby(col["claim_type"])[col["claim_id"]].count().sort_values(ascending=False)
        lines = [f"- {t}: {c:,}" for t, c in result.items()]
        return "**Claims Count by Claim Type:**\n" + "\n".join(lines)

    # --- Average BY type ---
    if df is not None and col is not None and (
        ("average" in q or "avg" in q) and "type" in q
    ):
        result = df.groupby(col["claim_type"])[col["claim_amount"]].mean().sort_values(ascending=False)
        lines = [f"- {t}: ${v:,.2f}" for t, v in result.items()]
        return "**Average Claim Value by Claim Type:**\n" + "\n".join(lines)

    # --- Average BY region ---
    if df is not None and col is not None and (
        ("average" in q or "avg" in q) and "region" in q
    ):
        result = df.groupby(col["region"])[col["claim_amount"]].mean().sort_values(ascending=False)
        lines = [f"- {r}: ${v:,.2f}" for r, v in result.items()]
        return "**Average Claim Value by Region:**\n" + "\n".join(lines)

    # --- Total value BY claim type ---
    if df is not None and col is not None and (
        "by claimtype" in q or "by claim type" in q or "per type" in q or
        ("type" in q and ("total" in q or "value" in q or "amount" in q))
    ):
        result = df.groupby(col["claim_type"])[col["claim_amount"]].sum().sort_values(ascending=False)
        lines = [f"- {t}: ${v:,.2f}" for t, v in result.items()]
        return "**Total Claim Value by Claim Type:**\n" + "\n".join(lines)

    # --- Total value BY region ---
    if df is not None and col is not None and (
        "by region" in q or "per region" in q or
        ("region" in q and ("total" in q or "value" in q or "amount" in q))
    ):
        result = df.groupby(col["region"])[col["claim_amount"]].sum().sort_values(ascending=False)
        lines = [f"- {r}: ${v:,.2f}" for r, v in result.items()]
        return "**Total Claim Value by Region:**\n" + "\n".join(lines)

    # --- Total value BY status ---
    if df is not None and col is not None and (
        "by status" in q or "per status" in q or
        ("status" in q and ("total" in q or "value" in q or "amount" in q))
    ):
        result = df.groupby(col["status"])[col["claim_amount"]].sum().sort_values(ascending=False)
        lines = [f"- {s}: ${v:,.2f}" for s, v in result.items()]
        return "**Total Claim Value by Status:**\n" + "\n".join(lines)

    # --- Status count (generic) ---
    if "how many" in q or "count" in q:
        for status in ["open", "closed", "pending", "rejected", "under review"]:
            if status in q:
                count = summary["status_counts"].get(status.title(), 0)
                return f"There are **{count:,}** {status.title()} claims in the current dataset."
        if "claim" in q:
            return f"There are **{summary['total_claims']:,}** claims in the current dataset."

    # --- Total value ---
    if "total" in q and ("value" in q or "amount" in q or "claim" in q):
        return (
            f"The total claim value across all {summary['total_claims']:,} claims is "
            f"**${summary['total_claim_amount']:,.2f}**.\n\n"
            f"- Total paid: ${summary['total_paid_amount']:,.2f}\n"
            f"- Total reserves: ${summary['total_reserve_amount']:,.2f}"
        )

    # --- Average ---
    if "average" in q or "avg" in q:
        if "day" in q or "open" in q:
            return f"The average number of days a claim is open is **{summary['avg_days_open']}** days."
        return f"The average claim value is **${summary['avg_claim_amount']:,.2f}**."

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
        f"- Total value: ${summary['total_claim_amount']:,.2f}\n"
        f"- Total paid: ${summary['total_paid_amount']:,.2f}\n"
        f"- Total reserves: ${summary['total_reserve_amount']:,.2f}\n"
        f"- Average claim: ${summary['avg_claim_amount']:,.2f}\n"
        f"- Average days open: {summary['avg_days_open']} days\n"
        f"- Date range: {summary['date_range_start']} -> {summary['date_range_end']}"
    )


# ---------------------------------------------------------------------------
# Lookup handler
# ---------------------------------------------------------------------------

def handle_lookup(claim_id: str, df: pd.DataFrame, col: dict) -> str:
    """Look up a specific claim by ID and return a markdown table.

    Args:
        claim_id: Claim ID string (e.g. "CLM0000042"), already extracted
                  by QueryAnalyzer.
        df:       Full claims DataFrame.
        col:      Column mapping dict.

    Returns:
        Markdown-formatted claim detail table, or not-found message.
    """
    if not claim_id:
        return "I couldn't find a Claim ID in your question. Please include the claim ID (e.g. CLM0000042)."

    claim_id = claim_id.upper()
    row = df[df[col["claim_id"]] == claim_id]

    if row.empty:
        return f"Claim **{claim_id}** was not found in the current dataset."

    r = row.iloc[0]

    def s(field):
        val = r.get(col.get(field, ""), "N/A")
        return "N/A" if pd.isna(val) else str(val)

    def c(field):
        try:
            return f"${float(r.get(col.get(field, ''), 0)):,.2f}"
        except Exception:
            return "N/A"

    closed_val = s("closed_date")
    closed_display = closed_val[:10] if closed_val != "N/A" else "Still open"

    lines = [
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Claim ID | {claim_id} |",
        f"| Status | {s('status')} |",
        f"| Type | {s('claim_type')} |",
        f"| Claimant | {s('claimant_name')} |",
        f"| Region | {s('region')} |",
        f"| Submitted | {s('submitted_date')[:10]} |",
        f"| Closed | {closed_display} |",
        f"| Claim Amount | {c('claim_amount')} |",
        f"| Paid Amount | {c('paid_amount')} |",
        f"| Reserve | {c('reserve_amount')} |",
        f"| Days Open | {s('days_open')} |",
    ]

    return f"**Claim {claim_id}**\n\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# RAG Pipeline
# ---------------------------------------------------------------------------

class RAGPipeline:
    """Orchestrates question-answering: QueryAnalyzer -> route -> answer.

    Flow:
        1. QueryAnalyzer classifies intent + extracts entities
        2. Route: aggregation -> handle_aggregation
                  lookup      -> handle_lookup
                  search      -> pre-filter -> FAISS -> LLM
    """

    def __init__(self, loader, search_engine, llm):
        """
        Args:
            loader:        ClaimsDataLoader instance (already loaded).
            search_engine: ClaimsSearchEngine instance (already built).
            llm:           ClaimsLLM instance.
        """
        self.loader = loader
        self.search_engine = search_engine
        self.llm = llm
        self.analyzer = QueryAnalyzer()

    # ------------------------------------------------------------------
    def ask(self, question: str) -> Dict[str, Any]:
        """Answer a natural language question about claims data.

        Returns:
            Dict with keys: answer, question_type, sources, entities.
        """
        if not question or not question.strip():
            return {
                "answer": "Please ask a question.",
                "question_type": "none",
                "sources": [],
                "entities": {},
            }

        question = question.strip()
        logger.info(f"Question received: '{question}'")

        # Step 1: Analyze intent + entities
        analysis = self.analyzer.analyze(question)
        intent = analysis.get("intent", "search")
        entities = {
            "claim_id": analysis.get("claim_id"),
            "status": analysis.get("status"),
            "region": analysis.get("region"),
            "claim_type": analysis.get("claim_type"),
            "high_value": analysis.get("high_value", False),
            "date_range": analysis.get("date_range"),
        }
        logger.info(f"Intent: {intent} | Entities: {entities}")

        # Step 2: Route by intent
        if intent == "aggregation":
            answer = handle_aggregation(
                question, self.loader.summary,
                self.loader.df, self.loader.col, entities,
            )
            return {
                "answer": answer,
                "question_type": "aggregation",
                "sources": [],
                "entities": entities,
            }

        if intent == "lookup":
            claim_id = entities.get("claim_id")
            answer = handle_lookup(claim_id, self.loader.df, self.loader.col)
            return {
                "answer": answer,
                "question_type": "lookup",
                "sources": [],
                "entities": entities,
            }

        # Step 3: Search path
        if not self.search_engine.is_ready:
            return {
                "answer": "Search engine is not ready. Please wait for the index to build.",
                "question_type": "search",
                "sources": [],
                "entities": entities,
            }

        # 3a. Pre-filter DataFrame indices by entities
        allowed = self._get_allowed_indices(entities)

        # 3b. FAISS search (filtered or unfiltered)
        if allowed is not None:
            matched_chunks = self.search_engine.search_with_filter(question, allowed)
        else:
            matched_chunks = self.search_engine.search(question)

        # 3c. Score threshold filter
        threshold = self.loader.config.get("ai", {}).get("faiss_score_threshold", 0.35)
        matched_chunks = [c for c in matched_chunks if c.get("score", 0) >= threshold]

        if not matched_chunks:
            return {
                "answer": "I couldn't find any relevant claims for that question.",
                "question_type": "search",
                "sources": [],
                "entities": entities,
            }

        # 3d. Retrieve full rows
        from data.text_chunker import retrieve_rows_from_chunks
        context_rows = retrieve_rows_from_chunks(self.loader.df, matched_chunks)

        # 3e. LLM with retry
        answer = self._ask_llm_with_retry(question, context_rows)

        sources = [c["claim_id"] for c in matched_chunks if "claim_id" in c]
        return {
            "answer": answer,
            "question_type": "search",
            "sources": sources,
            "entities": entities,
        }

    # ------------------------------------------------------------------
    def _get_allowed_indices(self, entities: dict) -> Optional[Set[int]]:
        """Build a set of allowed DataFrame indices from entity filters.

        Applies status, region, claim_type, and high_value filters.

        Returns:
            Set of df.index values, or None if no filters apply.
        """
        df = self.loader.df
        col = self.loader.col
        mask = pd.Series(True, index=df.index)
        has_filter = False

        if entities.get("status"):
            mask &= df[col["status"]].str.lower() == entities["status"].lower()
            has_filter = True

        if entities.get("region"):
            mask &= df[col["region"]].str.lower() == entities["region"].lower()
            has_filter = True

        if entities.get("claim_type"):
            mask &= df[col["claim_type"]].str.lower() == entities["claim_type"].lower()
            has_filter = True

        if entities.get("high_value"):
            threshold = self.loader.config.get("notifications", {}).get(
                "high_value_claim_threshold", 100000
            )
            mask &= df[col["claim_amount"]] >= threshold
            has_filter = True

        if not has_filter:
            return None

        return set(df.index[mask])

    # ------------------------------------------------------------------
    def _ask_llm_with_retry(self, question: str, context_rows: pd.DataFrame) -> str:
        """Call the LLM with retry logic.

        Attempts up to llm_retry_count times. On all failures, returns a
        summary-stats fallback answer.
        """
        retry_count = self.loader.config.get("ai", {}).get("llm_retry_count", 2)
        last_error = None

        for attempt in range(1, retry_count + 1):
            try:
                logger.info(f"LLM attempt {attempt}/{retry_count}")
                answer = self.llm.answer(
                    question=question,
                    context_rows=context_rows,
                    col=self.loader.col,
                    summary=self.loader.summary,
                )
                if answer and not answer.startswith("Could not reach"):
                    return answer
                last_error = answer
            except Exception as e:
                logger.warning(f"LLM attempt {attempt} failed: {e}")
                last_error = str(e)

        # Fallback: summary stats answer
        logger.warning("All LLM attempts failed, returning summary fallback")
        s = self.loader.summary
        return (
            f"I was unable to get a detailed answer from the AI model, "
            f"but here is what I know from the data:\n\n"
            f"- Total claims: {s['total_claims']:,}\n"
            f"- Total value: ${s['total_claim_amount']:,.2f}\n"
            f"- Total paid: ${s['total_paid_amount']:,.2f}\n"
            f"- Total reserves: ${s['total_reserve_amount']:,.2f}\n"
            f"- Average claim: ${s['avg_claim_amount']:,.2f}\n"
            f"- Average days open: {s['avg_days_open']} days\n\n"
            f"The search found {len(context_rows)} relevant claims. "
            f"Please try again or rephrase your question."
        )

    # ------------------------------------------------------------------
    def rebuild(self):
        """Reload data and rebuild the search index."""
        logger.info("RAG pipeline rebuild triggered")
        self.loader.reload()

        from data.text_chunker import dataframe_to_chunks
        chunks = dataframe_to_chunks(
            self.loader.df,
            self.loader.col,
            chunk_size=self.loader.config["data"]["chunk_size"],
        )
        self.search_engine.rebuild(chunks)
        logger.info("RAG pipeline rebuild complete")
