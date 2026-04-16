# ai/triage_brain.py
# Vector-Memory Active Learning — "The Brain"
#
# A SEPARATE FAISS index (not the RAG chat index) that embeds all historical
# claims with their fast-track outcomes. When a new claim arrives:
#   1. Find Top-K most similar past claims (precedents)
#   2. Return precedent data for LLM explanation
#   3. On adjuster feedback, instantly embed the new decision
#
# This mimics how human adjusters learn — by looking at past case precedents.

import logging
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("claims.triage_brain")


class TriageBrain:
    """
    FAISS-based precedent memory for claims triage.

    Separate from the RAG search index — this one stores claim-level
    embeddings with their triage outcomes for precedent-based reasoning.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = None
        self.index = None
        self.metadata: List[Dict[str, Any]] = []  # parallel to FAISS vectors
        self.is_built = False

    def _load_model(self):
        """Lazy-load the embedding model."""
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading triage embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)

    def _embed_text(self, text: str) -> np.ndarray:
        """Embed a single text string, return normalized vector."""
        import faiss
        self._load_model()
        vec = self.model.encode([text], convert_to_numpy=True).astype("float32")
        faiss.normalize_L2(vec)
        return vec

    def _build_claim_text(self, row) -> str:
        """
        Build a rich text representation of a claim for embedding.
        Combines loss description + key structured fields for better similarity.
        """
        parts = []

        desc = str(row.get("Loss Description", row.get("loss_description", ""))).strip()
        if desc and desc.lower() != "nan":
            parts.append(desc)

        lob = str(row.get("Major LOB", row.get("major_lob", ""))).strip()
        if lob and lob.lower() != "nan":
            parts.append(f"Line of business: {lob}")

        injury = str(row.get("Condition Injury Damage Name", row.get("injury_type", ""))).strip()
        if injury and injury.lower() != "nan":
            parts.append(f"Injury type: {injury}")

        reserve = row.get("Nominal Reserve", row.get("outstanding_reserve_usd", None))
        if reserve is not None:
            try:
                parts.append(f"Reserve: ${float(reserve):,.0f}")
            except (ValueError, TypeError):
                pass

        return " | ".join(parts) if parts else "No description available"

    def build_index(self, df: pd.DataFrame, batch_size: int = 256):
        """Embed all historical claims into the triage FAISS index."""
        import faiss
        self._load_model()

        start = time.time()
        logger.info(f"Building triage FAISS index for {len(df):,} claims...")

        texts = []
        self.metadata = []
        claim_col = "Claim Number" if "Claim Number" in df.columns else "claim_number"
        ft_col = "MAR Fast Track Flag" if "MAR Fast Track Flag" in df.columns else "mar_fast_track_flag"
        desc_col = "Loss Description" if "Loss Description" in df.columns else "loss_description"

        for idx, row in df.iterrows():
            text = self._build_claim_text(row)
            texts.append(text)

            ft_flag = str(row.get(ft_col, "")).strip().upper()
            ft_outcome = "Y" if ft_flag in ("Y", "YES", "TRUE", "1") else "N"

            self.metadata.append({
                "claim_number": str(row.get(claim_col, f"UNK-{idx}")),
                "ft_outcome": ft_outcome,
                "loss_description": str(row.get(desc_col, ""))[:500],
                "major_lob": str(row.get("Major LOB", row.get("major_lob", ""))),
                "reserve": float(pd.to_numeric(row.get("Nominal Reserve", row.get("outstanding_reserve_usd", 0)), errors="coerce") or 0),
                "injury": str(row.get("Condition Injury Damage Name", row.get("injury_type", ""))),
                "human_decision": row.get("human_decision", None),
                "df_index": idx,
            })

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            emb = self.model.encode(batch, show_progress_bar=False, convert_to_numpy=True)
            all_embeddings.append(emb)

        matrix = np.vstack(all_embeddings).astype("float32")
        faiss.normalize_L2(matrix)

        dim = matrix.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(matrix)
        self.is_built = True

        elapsed = round(time.time() - start, 1)
        logger.info(f"Triage FAISS index built in {elapsed}s — {self.index.ntotal:,} vectors")

    def find_precedents(
        self,
        claim_row,
        top_k: int = 5,
        exclude_self: bool = True,
    ) -> List[Dict[str, Any]]:
        """Find the Top-K most similar historical claims to a given claim."""
        if not self.is_built:
            raise RuntimeError("Triage brain not built. Call build_index() first.")

        import faiss

        text = self._build_claim_text(claim_row)
        query_vec = self.model.encode([text], convert_to_numpy=True).astype("float32")
        faiss.normalize_L2(query_vec)

        search_k = top_k + 3
        distances, indices = self.index.search(query_vec, search_k)

        claim_number = str(claim_row.get("Claim Number", claim_row.get("claim_number", "")))

        precedents = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue
            meta = self.metadata[idx]
            if exclude_self and meta["claim_number"] == claim_number:
                continue
            precedents.append({
                **meta,
                "similarity": round(float(dist), 4),
            })
            if len(precedents) >= top_k:
                break

        return precedents

    def embed_feedback(
        self,
        claim_number: str,
        loss_description: str,
        ft_outcome: str,
        human_decision: str,
        major_lob: str = "",
        reserve: float = 0,
        injury: str = "",
    ):
        """Immediately embed an adjuster's decision into the FAISS index."""
        import faiss

        if not self.is_built:
            raise RuntimeError("Triage brain not built. Call build_index() first.")

        row_dict = {
            "Loss Description": loss_description,
            "Major LOB": major_lob,
            "Condition Injury Damage Name": injury,
            "Nominal Reserve": reserve,
        }
        text = self._build_claim_text(row_dict)

        vec = self._embed_text(text)
        self.index.add(vec)

        self.metadata.append({
            "claim_number": claim_number,
            "ft_outcome": ft_outcome,
            "loss_description": loss_description[:500],
            "major_lob": major_lob,
            "reserve": reserve,
            "injury": injury,
            "human_decision": human_decision,
            "df_index": -1,
        })

        logger.info(
            f"Feedback embedded: claim={claim_number}, "
            f"outcome={ft_outcome}, human={human_decision} "
            f"(index now has {self.index.ntotal} vectors)"
        )

    def summarize_precedents(self, precedents: List[Dict[str, Any]]) -> str:
        """Generate a text summary of precedent outcomes."""
        if not precedents:
            return "No similar precedents found."

        approved = sum(1 for p in precedents if p["ft_outcome"] == "Y")
        denied = len(precedents) - approved

        human_overrides = [p for p in precedents if p.get("human_decision") is not None]
        agrees = sum(1 for p in human_overrides if p["human_decision"] == "Approve")
        disagrees = sum(1 for p in human_overrides if p["human_decision"] == "Disagree")

        parts = [f"Based on **{len(precedents)}** similar past claims:"]
        parts.append(f"- **{approved}** were approved for fast-track, **{denied}** were denied")

        if human_overrides:
            parts.append(f"- Adjuster feedback available: {agrees} agreed, {disagrees} disagreed with AI")

        avg_sim = np.mean([p["similarity"] for p in precedents])
        parts.append(f"- Average similarity: **{avg_sim:.1%}**")

        if approved > denied:
            parts.append("\nRecommendation: **FAST TRACK** (majority of similar claims were approved)")
        else:
            parts.append("\nRecommendation: **MANUAL REVIEW** (majority of similar claims were denied)")

        return "\n".join(parts)
