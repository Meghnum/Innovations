# =============================================================================
# ai/embeddings.py
# Phase 2 - Steps 4 & 5: Sentence Embeddings + FAISS In-Memory Index
# =============================================================================
# Responsibilities:
#   - Load the sentence-transformer model (CPU friendly, no GPU needed)
#   - Convert text chunks into vector embeddings
#   - Build a FAISS index entirely in memory (nothing written to disk)
#   - Search the index given a user question
#   - Return the most relevant chunk dicts for the RAG pipeline
# =============================================================================

import logging
import time
from typing import List, Dict, Any

import numpy as np

logger = logging.getLogger("claims.embeddings")


# ---------------------------------------------------------------------------
# Embedding model loader
# ---------------------------------------------------------------------------

def load_embedding_model(model_name: str = "all-MiniLM-L6-v2"):
    """
    Load the sentence-transformer model used to convert text to vectors.

    'all-MiniLM-L6-v2' is the best choice for CPU-only machines:
      - Small (80MB), fast on CPU, good quality
      - Produces 384-dimensional vectors
      - Downloads once, cached locally after first run

    Args:
        model_name: HuggingFace model name from config.

    Returns:
        A loaded SentenceTransformer model object.
    """
    from sentence_transformers import SentenceTransformer

    logger.info(f"Loading embedding model: {model_name}")
    logger.info("  (First run downloads ~80MB — cached after that)")

    start = time.time()
    model = SentenceTransformer(model_name)
    elapsed = round(time.time() - start, 1)

    logger.info(f"Embedding model loaded in {elapsed}s ✓")
    return model


# ---------------------------------------------------------------------------
# FAISS index builder
# ---------------------------------------------------------------------------

def build_faiss_index(
    chunks: List[Dict[str, Any]],
    model,
    batch_size: int = 256,
):
    """
    Convert all text chunks to embeddings and load them into a FAISS
    in-memory index.

    How it works:
      1. Extract the "text" field from each chunk
      2. Run sentence-transformer to get a 384-dim vector per text
      3. Normalise vectors (enables cosine similarity via dot product)
      4. Add all vectors to a FAISS IndexFlatIP (inner product) index
      5. Return the index + original chunks list

    The index lives purely in RAM — nothing is written to disk.
    On refresh, it is simply rebuilt from scratch.

    Args:
        chunks:     List of chunk dicts from text_chunker.py
        model:      Loaded SentenceTransformer model
        batch_size: Texts to embed per batch (tune down if RAM is tight)

    Returns:
        Tuple of (faiss_index, chunks) where chunks list is unchanged
        but now positionally aligned with the index vectors.
    """
    import faiss

    if not chunks:
        raise ValueError("No chunks provided to build_faiss_index.")

    texts = [c["text"] for c in chunks]
    total = len(texts)
    logger.info(f"Building FAISS index for {total:,} chunks...")

    # --- Embed in batches to avoid memory spikes ---
    all_embeddings = []
    num_batches = (total + batch_size - 1) // batch_size

    start = time.time()
    for i in range(num_batches):
        batch_texts = texts[i * batch_size : (i + 1) * batch_size]
        embeddings  = model.encode(
            batch_texts,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        all_embeddings.append(embeddings)

        if (i + 1) % 10 == 0 or i == num_batches - 1:
            done = min((i + 1) * batch_size, total)
            logger.info(f"  Embedded {done:,}/{total:,} chunks")

    # Stack into single matrix: shape (total, embedding_dim)
    matrix = np.vstack(all_embeddings).astype("float32")

    # Normalise so inner product == cosine similarity
    faiss.normalize_L2(matrix)

    # Build index — IndexFlatIP is exact search (no approximation)
    # Perfect for up to ~500k vectors on CPU
    dim   = matrix.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(matrix)

    elapsed = round(time.time() - start, 1)
    logger.info(
        f"FAISS index built in {elapsed}s — "
        f"{index.ntotal:,} vectors, {dim} dimensions ✓"
    )

    return index, chunks


# ---------------------------------------------------------------------------
# FAISS search
# ---------------------------------------------------------------------------

def search_index(
    query: str,
    index,
    chunks: List[Dict[str, Any]],
    model,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Search the FAISS index with a natural language question and return
    the most relevant chunks.

    Steps:
      1. Embed the query using the same model as the index
      2. Normalise the query vector
      3. FAISS returns the top_k most similar chunk positions
      4. We look up those positions in the chunks list and return them

    Args:
        query:  The user's question as a plain English string.
        index:  The FAISS index built by build_faiss_index().
        chunks: The same chunks list passed to build_faiss_index().
        model:  The loaded SentenceTransformer model.
        top_k:  Number of results to return (from config).

    Returns:
        List of chunk dicts, ordered by relevance (most relevant first).
        Each dict has: chunk_id, df_index, claim_id, text.
    """
    import faiss

    if index is None or index.ntotal == 0:
        logger.error("FAISS index is empty or not built.")
        return []

    # Embed and normalise the query
    query_vec = model.encode([query], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(query_vec)

    # Search — returns distances and indices arrays, shape (1, top_k)
    distances, indices = index.search(query_vec, top_k)

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx == -1:           # FAISS returns -1 when fewer results exist
            continue
        chunk = chunks[idx].copy()
        chunk["score"] = round(float(dist), 4)   # cosine similarity score
        results.append(chunk)

    logger.debug(
        f"Query: '{query[:60]}...' → {len(results)} results, "
        f"top score: {results[0]['score'] if results else 'N/A'}"
    )

    return results


# ---------------------------------------------------------------------------
# ClaimsSearchEngine — wraps everything into one object
# ---------------------------------------------------------------------------

class ClaimsSearchEngine:
    """
    The main search object used by the RAG pipeline and Streamlit UI.

    Usage:
        engine = ClaimsSearchEngine(config)
        engine.build(chunks)               # Call once after data load
        results = engine.search("Show me open medical claims in London")
        engine.rebuild(new_chunks)         # Call on data refresh
    """

    def __init__(self, config: dict):
        """
        Initialise with the full config dict.

        Args:
            config: Loaded config.yaml as a dict.
        """
        self.config     = config
        self.ai_cfg     = config["ai"]
        self.model      = None
        self.index      = None
        self.chunks     = []
        self._built     = False

    # ------------------------------------------------------------------
    def load_model(self):
        """Load the embedding model. Called once at startup."""
        self.model = load_embedding_model(self.ai_cfg["embedding_model"])

    # ------------------------------------------------------------------
    def build(self, chunks: List[Dict[str, Any]]):
        """
        Build the FAISS index from a list of text chunks.

        Args:
            chunks: Output from dataframe_to_chunks() in text_chunker.py
        """
        if self.model is None:
            self.load_model()

        self.index, self.chunks = build_faiss_index(
            chunks     = chunks,
            model      = self.model,
            batch_size = 256,
        )
        self._built = True

    # ------------------------------------------------------------------
    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for claims relevant to a natural language query.

        Args:
            query: Plain English question from the user.

        Returns:
            List of matching chunk dicts with similarity scores.

        Raises:
            RuntimeError: If the index hasn't been built yet.
        """
        if not self._built:
            raise RuntimeError("Search engine not built. Call engine.build(chunks) first.")

        return search_index(
            query  = query,
            index  = self.index,
            chunks = self.chunks,
            model  = self.model,
            top_k  = self.ai_cfg["top_k_results"],
        )

    # ------------------------------------------------------------------
    def rebuild(self, chunks: List[Dict[str, Any]]):
        """
        Rebuild the index from scratch — used when data is refreshed.

        Args:
            chunks: Fresh chunks from the reloaded DataFrame.
        """
        logger.info("Rebuilding FAISS index after data refresh...")
        self._built = False
        self.build(chunks)

    # ------------------------------------------------------------------
    @property
    def is_ready(self) -> bool:
        """True if the index is built and ready to search."""
        return self._built and self.index is not None

    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        vectors = self.index.ntotal if self.index else 0
        return f"<ClaimsSearchEngine vectors={vectors:,} ready={self.is_ready}>"
