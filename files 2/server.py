# =============================================================================
# api/server.py
# FastAPI Backend — serves the RAG pipeline to the React frontend
# =============================================================================
# Run with:
#   uvicorn api.server:app --reload --port 8000
# =============================================================================

import sys
import logging
import time
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from data.qvd_loader import ClaimsDataLoader, load_config
from data.text_chunker import dataframe_to_chunks
from ai.embeddings import ClaimsSearchEngine
from ai.llm import ClaimsLLM
from ai.rag_pipeline import RAGPipeline

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("claims.api")

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title       = "Claims Assistant API",
    description = "Local RAG-powered claims Q&A backend",
    version     = "1.0.0",
)

# Allow React dev server (port 5173) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:5173", "http://localhost:3000"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ---------------------------------------------------------------------------
# Global pipeline state — loaded once at startup
# ---------------------------------------------------------------------------
pipeline: RAGPipeline = None
loader: ClaimsDataLoader = None


@app.on_event("startup")
async def startup_event():
    """Initialise the full RAG pipeline when the server starts."""
    global pipeline, loader

    logger.info("Server starting — initialising RAG pipeline...")
    cfg = load_config("config/config.yaml")

    loader = ClaimsDataLoader(config_path="config/config.yaml")
    loader.load()

    chunks = dataframe_to_chunks(
        loader.df,
        loader.col,
        chunk_size=cfg["data"]["chunk_size"],
    )

    engine = ClaimsSearchEngine(cfg)
    engine.build(chunks)

    llm      = ClaimsLLM(cfg)
    pipeline = RAGPipeline(loader, engine, llm)

    logger.info("RAG pipeline ready ✓")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class QuestionRequest(BaseModel):
    question: str


class QuestionResponse(BaseModel):
    answer:        str
    question_type: str
    sources:       List[str]
    elapsed:       float


class SummaryResponse(BaseModel):
    total_claims:        int
    total_claim_amount:  float
    total_paid_amount:   float
    total_reserve_amount: float
    avg_claim_amount:    float
    avg_days_open:       float
    status_counts:       dict
    type_counts:         dict
    region_counts:       dict
    date_range_start:    str
    date_range_end:      str
    data_loaded_at:      str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Quick health check — confirms server and pipeline are running."""
    return {
        "status":   "ok",
        "pipeline": pipeline is not None,
        "llm":      pipeline.llm.check() if pipeline else False,
        "rows":     len(loader.df) if loader and loader.df is not None else 0,
    }


@app.get("/summary", response_model=SummaryResponse)
def get_summary():
    """Return pre-computed summary stats for the sidebar."""
    if not loader or not loader.summary:
        raise HTTPException(status_code=503, detail="Data not loaded yet")
    s = loader.summary
    return SummaryResponse(
        total_claims         = s["total_claims"],
        total_claim_amount   = s["total_claim_amount"],
        total_paid_amount    = s["total_paid_amount"],
        total_reserve_amount = s["total_reserve_amount"],
        avg_claim_amount     = s["avg_claim_amount"],
        avg_days_open        = s["avg_days_open"],
        status_counts        = s["status_counts"],
        type_counts          = s["type_counts"],
        region_counts        = s["region_counts"],
        date_range_start     = s["date_range_start"],
        date_range_end       = s["date_range_end"],
        data_loaded_at       = s["data_loaded_at"],
    )


@app.post("/ask", response_model=QuestionResponse)
def ask_question(req: QuestionRequest):
    """
    Main Q&A endpoint. Accepts a question, returns an answer.
    Routes automatically to aggregation, lookup, or RAG search.
    """
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not ready")

    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    start    = time.time()
    response = pipeline.ask(req.question.strip())
    elapsed  = round(time.time() - start, 2)

    return QuestionResponse(
        answer        = response["answer"],
        question_type = response["question_type"],
        sources       = response.get("sources", []),
        elapsed       = elapsed,
    )


@app.post("/refresh")
def refresh_data():
    """Force a full data reload and FAISS index rebuild."""
    global pipeline, loader
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not ready")

    pipeline.rebuild()
    return {
        "status":     "refreshed",
        "rows":       len(loader.df),
        "loaded_at":  loader.last_loaded,
    }


@app.get("/suggested-questions")
def suggested_questions():
    """Return example questions for the UI quick-select."""
    return {"questions": [
        "How many open claims are there?",
        "What is the total claim value?",
        "Give me total value by ClaimType",
        "Give me total value by region",
        "How many claims by region?",
        "Average claim value by type",
        "Tell me about claim CLM0000003",
        "Show me high value medical claims",
        "Which claims have been open the longest?",
        "Show me open claims in London",
        "Show me rejected claims in Scotland",
        "What are the largest property claims?",
    ]}
