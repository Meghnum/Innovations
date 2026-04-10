# =============================================================================
# ui/streamlit_app.py
# Phase 3 - Streamlit Chat Interface
# =============================================================================
# Responsibilities:
#   - Clean chat interface in the browser
#   - Initialise the full RAG pipeline on startup (once)
#   - Maintain chat history in session
#   - Show last data load timestamp
#   - Data refresh button
#   - Display answers as text and tables
#   - Show source claim IDs for search answers
#   - Graceful error handling if Ollama is slow/unavailable
#
# Run with:
#   streamlit run ui/streamlit_app.py
# =============================================================================

import sys
import time
import logging
from pathlib import Path

# Make sure project root is on the path when running from ui/ subfolder
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

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
logger = logging.getLogger("claims.ui")

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------
config = load_config("config/config.yaml")
st_cfg  = config.get("streamlit", {})

st.set_page_config(
    page_title = st_cfg.get("page_title", "Claims Assistant"),
    page_icon  = st_cfg.get("page_icon", "📋"),
    layout     = "wide",
)

# ---------------------------------------------------------------------------
# Custom CSS — clean, professional look
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Main background */
    .stApp { background-color: #f8f9fa; }

    /* Chat message bubbles */
    .user-bubble {
        background: #0078d4;
        color: white;
        padding: 12px 16px;
        border-radius: 18px 18px 4px 18px;
        margin: 8px 0;
        max-width: 75%;
        margin-left: auto;
        font-size: 15px;
    }
    .bot-bubble {
        background: white;
        color: #1a1a1a;
        padding: 12px 16px;
        border-radius: 18px 18px 18px 4px;
        margin: 8px 0;
        max-width: 85%;
        border: 1px solid #e0e0e0;
        font-size: 15px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }

    /* Source pills */
    .source-pill {
        display: inline-block;
        background: #e8f0fe;
        color: #1a73e8;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
        margin: 2px;
    }

    /* Status bar */
    .status-bar {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 10px 16px;
        font-size: 13px;
        color: #555;
    }

    /* Header */
    .main-header {
        background: linear-gradient(135deg, #0078d4, #005a9e);
        color: white;
        padding: 20px 24px;
        border-radius: 12px;
        margin-bottom: 20px;
    }

    /* Hide Streamlit default elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Input box */
    .stTextInput input {
        border-radius: 24px;
        border: 2px solid #0078d4;
        padding: 10px 18px;
        font-size: 15px;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Pipeline initialisation — cached so it only runs once per session
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def initialise_pipeline():
    """
    Load data, build embeddings, and wire up the RAG pipeline.
    Cached by Streamlit so this only runs once when the app starts.

    Returns:
        Tuple of (pipeline, loader) ready to use.
    """
    cfg = load_config("config/config.yaml")

    # 1. Load data
    loader = ClaimsDataLoader(config_path="config/config.yaml")
    loader.load()

    # 2. Convert to text chunks
    chunks = dataframe_to_chunks(
        loader.df,
        loader.col,
        chunk_size=cfg["data"]["chunk_size"],
    )

    # 3. Build FAISS index
    engine = ClaimsSearchEngine(cfg)
    engine.build(chunks)

    # 4. Connect LLM
    llm = ClaimsLLM(cfg)

    # 5. Wire pipeline
    pipeline = RAGPipeline(loader, engine, llm)

    return pipeline, loader


def refresh_pipeline():
    """
    Force a full data reload and FAISS rebuild.
    Clears the Streamlit cache so initialise_pipeline runs again.
    """
    st.cache_resource.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# Helper: render a single chat message
# ---------------------------------------------------------------------------

def render_message(role: str, content: str, sources: list = None,
                   question_type: str = None, elapsed: float = None):
    """
    Render a chat bubble for user or assistant messages.

    Args:
        role:          "user" or "assistant"
        content:       The message text (supports markdown)
        sources:       List of source claim IDs (for search answers)
        question_type: The RAG question type label
        elapsed:       Response time in seconds
    """
    if role == "user":
        st.markdown(f'<div class="user-bubble">🧑 {content}</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="bot-bubble">📋 {content}</div>',
                    unsafe_allow_html=True)

        # Metadata row below the answer
        meta_cols = st.columns([3, 1])
        with meta_cols[0]:
            if sources:
                pills = "".join(
                    f'<span class="source-pill">{s}</span>' for s in sources[:5]
                )
                st.markdown(
                    f'<div style="margin-top:4px">🔍 Sources: {pills}</div>',
                    unsafe_allow_html=True,
                )
        with meta_cols[1]:
            if elapsed:
                label = "⚡ instant" if elapsed < 1 else f"⏱ {elapsed:.1f}s"
                st.caption(f"{label} · {question_type or ''}")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar(loader):
    """Render the sidebar with data stats and controls."""
    with st.sidebar:
        st.markdown("## ⚙️ Controls")

        # Refresh button
        if st.button("🔄 Refresh Data", use_container_width=True):
            with st.spinner("Reloading data and rebuilding index..."):
                refresh_pipeline()

        st.divider()

        # Data summary stats
        st.markdown("## 📊 Data Summary")
        summary = loader.summary

        st.metric("Total Claims",
                  f"{summary['total_claims']:,}")
        st.metric("Total Value",
                  f"£{summary['total_claim_amount']/1_000_000:.1f}M")
        st.metric("Avg Claim",
                  f"£{summary['avg_claim_amount']:,.0f}")
        st.metric("Avg Days Open",
                  f"{summary['avg_days_open']} days")

        st.divider()

        # Status breakdown
        st.markdown("**By Status**")
        for status, count in summary["status_counts"].items():
            pct = count / summary["total_claims"] * 100
            st.progress(pct / 100, text=f"{status}: {count:,} ({pct:.0f}%)")

        st.divider()

        # Timestamps
        st.caption(f"🕐 Last loaded: {loader.last_loaded}")
        st.caption(f"📅 Data from: {summary['date_range_start']}")
        st.caption(f"📅 Data to: {summary['date_range_end']}")

        st.divider()

        # Example questions
        st.markdown("## 💡 Try asking...")
        examples = [
            "How many open claims are there?",
            "What is the total claim value?",
            "Show me the breakdown by region",
            "Tell me about claim CLM0000003",
            "Show me high value medical claims",
            "Which region has the most claims?",
            "What is the average days open?",
            "Show me pending claims in London",
        ]
        for ex in examples:
            if st.button(ex, use_container_width=True, key=f"ex_{ex[:20]}"):
                st.session_state.pending_question = ex


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main():
    # --- Header ---
    st.markdown("""
    <div class="main-header">
        <h2 style="margin:0">📋 Claims Assistant</h2>
        <p style="margin:4px 0 0 0; opacity:0.85; font-size:14px">
            Ask questions about your claims data in plain English
        </p>
    </div>
    """, unsafe_allow_html=True)

    # --- Initialise pipeline ---
    with st.spinner("⚙️ Loading data and building search index... (first load takes ~30s)"):
        try:
            pipeline, loader = initialise_pipeline()
        except Exception as e:
            st.error(f"❌ Failed to initialise: {e}")
            st.stop()

    # --- Check LLM ---
    llm_ready = pipeline.llm.check()
    if not llm_ready:
        st.warning(
            "⚠️ Ollama is not running. Aggregation and lookup questions will work instantly. "
            "For AI-powered search answers, open a terminal and run: `ollama serve`",
            icon="⚠️",
        )

    # --- Sidebar ---
    render_sidebar(loader)

    # --- Session state ---
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_question" not in st.session_state:
        st.session_state.pending_question = None

    # --- Chat history ---
    chat_container = st.container()
    with chat_container:
        if not st.session_state.messages:
            st.markdown("""
            <div style="text-align:center; padding:40px; color:#888">
                <h3>👋 Hello! I'm your Claims Assistant.</h3>
                <p>Ask me anything about your claims data.<br>
                Try the example questions in the sidebar, or type your own below.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            for msg in st.session_state.messages:
                render_message(
                    role          = msg["role"],
                    content       = msg["content"],
                    sources       = msg.get("sources"),
                    question_type = msg.get("question_type"),
                    elapsed       = msg.get("elapsed"),
                )

    # --- Input area ---
    st.divider()
    col_input, col_clear = st.columns([6, 1])

    with col_input:
        default_val = st.session_state.pop("pending_question", None) or ""
        question = st.text_input(
            label            = "Ask a question",
            value            = default_val,
            placeholder      = "e.g. How many open claims are there in London?",
            label_visibility = "collapsed",
            key              = "question_input",
        )

    with col_clear:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.messages      = []
            st.session_state.last_question = ""
            st.session_state.question_input = ""
            st.rerun()

    # --- Process question ---
    if question and question.strip() and question != st.session_state.get("last_question", ""):
        st.session_state.last_question = question

        st.session_state.messages.append({
            "role":    "user",
            "content": question,
        })

        with st.spinner("🤔 Thinking..."):
            start    = time.time()
            response = pipeline.ask(question)
            elapsed  = round(time.time() - start, 1)

        st.session_state.messages.append({
            "role":          "assistant",
            "content":       response["answer"],
            "sources":       response.get("sources", []),
            "question_type": response.get("question_type"),
            "elapsed":       elapsed,
        })

        max_history = st_cfg.get("max_chat_history", 50)
        if len(st.session_state.messages) > max_history:
            st.session_state.messages = st.session_state.messages[-max_history:]

        st.rerun()


if __name__ == "__main__":
    main()
