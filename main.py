# =============================================================================
# main.py — Entry Point
# =============================================================================
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from data.qvd_loader import ClaimsDataLoader
from data.text_chunker import dataframe_to_chunks
from ai.embeddings import ClaimsSearchEngine
from ai.llm import ClaimsLLM
from ai.rag_pipeline import RAGPipeline


def run_phase2_test():
    print("\n" + "=" * 60)
    print("  Claims ChatGPT — Phase 2 Test (RAG Pipeline)")
    print("=" * 60)

    # --- Step 1: Load data ---
    print("\n[1/4] Loading data...")
    loader = ClaimsDataLoader(config_path="config/config.yaml")
    loader.load()
    print(f"      ✓ {loader.summary['total_claims']:,} claims loaded")

    # --- Step 2: Convert to text chunks ---
    print("\n[2/4] Converting rows to text chunks...")
    chunks = dataframe_to_chunks(
        loader.df, loader.col,
        chunk_size=loader.config["data"]["chunk_size"]
    )
    print(f"      ✓ {len(chunks):,} chunks ready")

    # --- Step 3: Build FAISS index ---
    print("\n[3/4] Building FAISS search index...")
    engine = ClaimsSearchEngine(loader.config)
    engine.build(chunks)
    print(f"      ✓ {engine}")

    # --- Step 4: Wire up RAG pipeline ---
    print("\n[4/4] Connecting LLM (Ollama)...")
    llm      = ClaimsLLM(loader.config)
    llm_ok   = llm.check()
    pipeline = RAGPipeline(loader, engine, llm)

    if not llm_ok:
        print("      ⚠️  Ollama not running — LLM answers will show error message")
        print("         Run: ollama serve   (in a separate terminal)")
        print("         Then: ollama pull llama3")
    else:
        print("      ✓ Llama3 ready")

    # --- Test questions ---
    print("\n" + "=" * 60)
    print("  Testing Questions")
    print("=" * 60)

    test_questions = [
        "How many open claims are there?",
        "What is the total claim value?",
        "Show me the breakdown by region",
        "Tell me about claim CLM0000003",
        "Show me high value medical claims",
    ]

    for question in test_questions:
        print(f"\n❓ {question}")
        response = pipeline.ask(question)
        print(f"   Type   : {response['question_type']}")
        print(f"   Answer : {response['answer']}")
        if response.get("sources"):
            print(f"   Sources: {response['sources']}")

    print("\n✅  Phase 2 complete — RAG pipeline working!\n")
    print("Next: Phase 3 — Streamlit chat UI\n")


if __name__ == "__main__":
    run_phase2_test()
