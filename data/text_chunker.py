# =============================================================================
# data/text_chunker.py
# Phase 1 - Step 2: DataFrame to Text Chunk Converter
# =============================================================================
# Responsibilities:
#   - Convert each DataFrame row into a meaningful natural language sentence
#   - Group rows into chunks for efficient embedding
#   - Preserve metadata (ClaimID, index) alongside each chunk
#     so we can retrieve the original row after FAISS search
#   - Handle missing / null values gracefully
# =============================================================================

import logging
import math
from typing import List, Dict, Any

import pandas as pd

logger = logging.getLogger("claims.chunker")


# ---------------------------------------------------------------------------
# Single row → text
# ---------------------------------------------------------------------------

def row_to_text(row: pd.Series, col: dict) -> str:
    """
    Convert one DataFrame row into a human-readable sentence.

    The sentence is what gets embedded and stored in FAISS.
    When a user asks a question, FAISS finds the most similar
    sentences and we return the original rows to the LLM as context.

    Args:
        row: A single row from the claims DataFrame (pd.Series).
        col: Column name mapping from config["columns"].

    Returns:
        A natural language string describing the claim.

    Example output:
        "Claim CLM0000001 is an Open Medical claim submitted on
         21 Nov 2023 by John Williams in the South East region,
         with a claim value of £65,910.76, reserve of £44,068.19,
         and has been open for 867 days."
    """

    def fmt_currency(val) -> str:
        """Format a number as £ currency, return 'N/A' if missing."""
        try:
            return f"£{float(val):,.2f}"
        except (TypeError, ValueError):
            return "N/A"

    def fmt_date(val) -> str:
        """Format a date as '21 Nov 2023', return 'N/A' if missing."""
        try:
            if pd.isna(val):
                return "N/A"
            return pd.to_datetime(val).strftime("%-d %b %Y")
        except Exception:
            return "N/A"

    def fmt_int(val) -> str:
        """Format an integer, return 'N/A' if missing."""
        try:
            return str(int(val))
        except (TypeError, ValueError):
            return "N/A"

    def safe(val) -> str:
        """Return string value or 'N/A' if null."""
        if pd.isna(val) if not isinstance(val, str) else False:
            return "N/A"
        return str(val).strip() or "N/A"

    # --- Extract fields ---
    claim_id     = safe(row.get(col["claim_id"], ""))
    status       = safe(row.get(col["status"], ""))
    claim_type   = safe(row.get(col["claim_type"], ""))
    submitted    = fmt_date(row.get(col["submitted_date"]))
    closed       = fmt_date(row.get(col["closed_date"]))
    region       = safe(row.get(col["region"], ""))
    claimant     = safe(row.get(col["claimant_name"], ""))
    amount       = fmt_currency(row.get(col["claim_amount"]))
    paid         = fmt_currency(row.get(col["paid_amount"]))
    reserve      = fmt_currency(row.get(col["reserve_amount"]))
    days_open    = fmt_int(row.get(col["days_open"]))

    # --- Build sentence ---
    # Core description always present
    text = (
        f"Claim {claim_id} is a {status} {claim_type} claim "
        f"submitted on {submitted} by {claimant} in the {region} region, "
        f"with a claim value of {amount}"
    )

    # Append financial details based on status
    if status == "Closed":
        text += f", paid amount of {paid}, and was closed on {closed}."
    elif status in ("Open", "Pending", "Under Review"):
        text += (
            f", reserve of {reserve}, "
            f"and has been open for {days_open} days."
        )
    elif status == "Rejected":
        text += f" and was rejected on {closed}."
    else:
        text += "."

    return text


# ---------------------------------------------------------------------------
# Full DataFrame → list of chunk dicts
# ---------------------------------------------------------------------------

def dataframe_to_chunks(
    df: pd.DataFrame,
    col: dict,
    chunk_size: int = 500,
) -> List[Dict[str, Any]]:
    """
    Convert an entire DataFrame into a list of text chunks with metadata.

    Each chunk contains:
        - "text"      : the natural language sentence for this row
        - "claim_id"  : the ClaimID so we can look up the full row later
        - "df_index"  : the DataFrame index for direct row retrieval
        - "chunk_id"  : sequential chunk number (used by FAISS)

    We process in batches (chunk_size rows at a time) so even large
    DataFrames don't spike memory.

    Args:
        df:         The claims DataFrame.
        col:        Column name mapping from config["columns"].
        chunk_size: How many rows to process per batch (default 500).

    Returns:
        List of chunk dicts, one per DataFrame row.

    Example return:
        [
            {
                "chunk_id": 0,
                "df_index": 0,
                "claim_id": "CLM0000001",
                "text": "Claim CLM0000001 is an Open Medical claim..."
            },
            ...
        ]
    """
    if df is None or len(df) == 0:
        logger.warning("Empty DataFrame passed to dataframe_to_chunks.")
        return []

    total_rows   = len(df)
    total_chunks = math.ceil(total_rows / chunk_size)
    chunks       = []
    chunk_id     = 0

    logger.info(
        f"Converting {total_rows:,} rows to text chunks "
        f"(batch size: {chunk_size}, batches: {total_chunks})"
    )

    for batch_num in range(total_chunks):
        start = batch_num * chunk_size
        end   = min(start + chunk_size, total_rows)
        batch = df.iloc[start:end]

        for df_index, row in batch.iterrows():
            try:
                text = row_to_text(row, col)
                chunks.append({
                    "chunk_id": chunk_id,
                    "df_index": df_index,
                    "claim_id": str(row.get(col["claim_id"], f"ROW_{df_index}")),
                    "text":     text,
                })
                chunk_id += 1
            except Exception as e:
                logger.error(f"Failed to convert row {df_index}: {e}")

        # Progress log every 10 batches
        if (batch_num + 1) % 10 == 0 or batch_num == total_chunks - 1:
            logger.info(f"  Batch {batch_num + 1}/{total_chunks} done — {chunk_id:,} chunks so far")

    logger.info(f"Text conversion complete. Total chunks: {len(chunks):,}")
    return chunks


# ---------------------------------------------------------------------------
# Retrieve original rows from chunk search results
# ---------------------------------------------------------------------------

def retrieve_rows_from_chunks(
    df: pd.DataFrame,
    matched_chunks: List[Dict[str, Any]],
) -> pd.DataFrame:
    """
    Given a list of matched chunk dicts (returned by FAISS search),
    retrieve the corresponding full rows from the DataFrame.

    This is called after FAISS finds the most relevant chunks so we
    can pass the full row data to the LLM as context.

    Args:
        df:             The full claims DataFrame.
        matched_chunks: List of chunk dicts from FAISS results,
                        each must have a "df_index" key.

    Returns:
        DataFrame of the matched rows (preserves original column order).
    """
    if not matched_chunks:
        return pd.DataFrame()

    indices = [c["df_index"] for c in matched_chunks if c["df_index"] in df.index]

    if not indices:
        logger.warning("No valid df_index values found in matched chunks.")
        return pd.DataFrame()

    return df.loc[indices].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Quick preview helper (useful for debugging)
# ---------------------------------------------------------------------------

def preview_chunks(chunks: List[Dict[str, Any]], n: int = 5) -> None:
    """
    Print the first N chunks to the console for inspection.

    Args:
        chunks: List of chunk dicts.
        n:      Number of chunks to preview.
    """
    print(f"\n--- Chunk Preview (first {min(n, len(chunks))}) ---")
    for chunk in chunks[:n]:
        print(f"\n[Chunk {chunk['chunk_id']}] ClaimID: {chunk['claim_id']}")
        print(f"  {chunk['text']}")
    print("---\n")
