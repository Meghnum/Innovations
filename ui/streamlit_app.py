# =============================================================================
# ui/streamlit_app.py
# Professional Dark Theme Streamlit Chat Interface
# =============================================================================

import sys
import re
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.graph_objects as go

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
# Page config
# ---------------------------------------------------------------------------
config = load_config("config/config.yaml")
st_cfg = config.get("streamlit", {})

st.set_page_config(
    page_title=st_cfg.get("page_title", "Claims Assistant"),
    page_icon=st_cfg.get("page_icon", ""),
    layout="wide",
)

# ---------------------------------------------------------------------------
# Professional Dark CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* === Base === */
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    header[data-testid="stHeader"] { display: none; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .stDeployButton { display: none; }

    /* === Sidebar === */
    section[data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #30363d;
    }
    section[data-testid="stSidebar"] .stMarkdown { color: #c9d1d9; }

    /* === Chat bubbles === */
    .user-bubble {
        background: #0d419d;
        color: #ffffff;
        padding: 14px 18px;
        border-radius: 18px 18px 4px 18px;
        margin: 8px 0;
        max-width: 70%;
        margin-left: auto;
        font-size: 15px;
        text-align: right;
    }
    .bot-bubble {
        background: #1c2128;
        color: #c9d1d9;
        padding: 14px 18px;
        border-radius: 18px 18px 18px 4px;
        margin: 8px 0;
        max-width: 85%;
        border: 1px solid #30363d;
        font-size: 15px;
    }
    .bot-bubble strong { color: #58a6ff; }
    .bot-bubble table { width: 100%; border-collapse: collapse; margin: 8px 0; }
    .bot-bubble th { background: #21262d; color: #58a6ff; padding: 6px 10px; text-align: left; border: 1px solid #30363d; }
    .bot-bubble td { padding: 6px 10px; border: 1px solid #30363d; }

    /* === Badges === */
    .badge-agg {
        display: inline-block; background: #1f3a5f; color: #58a6ff;
        padding: 2px 10px; border-radius: 10px; font-size: 11px;
        font-weight: 600; margin-bottom: 6px;
    }
    .badge-lookup {
        display: inline-block; background: #3b2e00; color: #e3b341;
        padding: 2px 10px; border-radius: 10px; font-size: 11px;
        font-weight: 600; margin-bottom: 6px;
    }
    .badge-search {
        display: inline-block; background: #0d3321; color: #3fb950;
        padding: 2px 10px; border-radius: 10px; font-size: 11px;
        font-weight: 600; margin-bottom: 6px;
    }

    /* === Source pills === */
    .source-pill {
        display: inline-block; background: #1f3a5f; color: #58a6ff;
        padding: 2px 10px; border-radius: 12px; font-size: 12px; margin: 2px;
    }

    /* === KPI tiles === */
    .kpi-grid {
        display: grid; grid-template-columns: 1fr 1fr;
        gap: 8px; margin: 10px 0;
    }
    .kpi-tile {
        background: #0d1117; border: 1px solid #30363d; border-radius: 8px;
        padding: 10px 12px; text-align: center;
    }
    .kpi-label { font-size: 11px; color: #8b949e; text-transform: uppercase; }
    .kpi-value { font-size: 20px; font-weight: 700; margin-top: 2px; }
    .kpi-blue { color: #58a6ff; }
    .kpi-green { color: #3fb950; }
    .kpi-amber { color: #e3b341; }
    .kpi-red { color: #f85149; }

    /* === Status progress bars === */
    .status-bar-row {
        display: flex; align-items: center; margin: 4px 0; font-size: 13px;
    }
    .status-bar-label { width: 100px; color: #8b949e; }
    .status-bar-track {
        flex: 1; height: 8px; background: #21262d; border-radius: 4px;
        overflow: hidden; margin: 0 8px;
    }
    .status-bar-fill { height: 100%; border-radius: 4px; }
    .status-bar-fill-blue { background: #58a6ff; }
    .status-bar-fill-green { background: #3fb950; }
    .status-bar-fill-amber { background: #e3b341; }
    .status-bar-fill-red { background: #f85149; }
    .status-bar-fill-purple { background: #bc8cff; }
    .status-bar-count { color: #8b949e; font-size: 12px; min-width: 45px; text-align: right; }

    /* === Input — Gemini-style floating bar === */
    .stChatInput {
        background: transparent !important;
    }
    .stChatInput > div {
        background: #1e1f20 !important;
        border: 1px solid #3c4043 !important;
        border-radius: 24px !important;
        padding: 4px 8px !important;
    }
    .stChatInput textarea {
        background: transparent !important;
        color: #c9d1d9 !important;
        font-size: 15px !important;
        border: none !important;
        box-shadow: none !important;
    }
    .stChatInput textarea::placeholder {
        color: #8b949e !important;
    }
    .stChatInput button {
        background: transparent !important;
        border: none !important;
        color: #8b949e !important;
    }
    .stChatInput button:hover {
        color: #58a6ff !important;
    }

    /* Hide old text input if any */
    .stTextInput input {
        background: #161b22 !important; color: #c9d1d9 !important;
        border: 1px solid #30363d !important; border-radius: 24px !important;
        padding: 10px 18px !important; font-size: 15px !important;
    }
    .stTextInput input:focus {
        border-color: #58a6ff !important;
        box-shadow: 0 0 0 1px #58a6ff !important;
    }

    /* === Buttons === */
    .stButton > button {
        background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
        border-radius: 6px; font-size: 13px;
    }
    .stButton > button:hover { background: #30363d; border-color: #58a6ff; }

    /* === Header bar === */
    .header-bar {
        background: #161b22; border: 1px solid #30363d; border-radius: 10px;
        padding: 16px 24px; margin-bottom: 16px;
        display: flex; align-items: center; justify-content: space-between;
    }
    .header-left { display: flex; align-items: center; gap: 10px; }
    .live-dot {
        width: 8px; height: 8px; border-radius: 50%; background: #3fb950;
        display: inline-block; animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
    }
    .header-title { font-size: 20px; font-weight: 700; color: #c9d1d9; }
    .header-model { font-size: 12px; color: #8b949e; }

    /* === Timing caption === */
    .timing-cap { font-size: 11px; color: #484f58; margin-top: 4px; }

    /* === Welcome === */
    .welcome-box {
        text-align: center; padding: 50px 20px; color: #484f58;
    }
    .welcome-box h3 { color: #8b949e; margin-bottom: 8px; }

    /* === Dividers === */
    hr { border-color: #30363d !important; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Pipeline init (cached)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def initialise_pipeline():
    """Load data, build chunks, build FAISS, create pipeline."""
    cfg = load_config("config/config.yaml")
    loader = ClaimsDataLoader(config_path="config/config.yaml")
    loader.load()

    chunks = dataframe_to_chunks(
        loader.df, loader.col,
        chunk_size=cfg["data"]["chunk_size"],
    )

    engine = ClaimsSearchEngine(cfg)
    engine.build(chunks)

    llm = ClaimsLLM(cfg)
    pipeline = RAGPipeline(loader, engine, llm)
    return pipeline, loader


def refresh_pipeline():
    """Clear cache and rerun to force full reload."""
    st.cache_resource.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def extract_chart_data(answer: str):
    """Parse breakdown answers into (labels, values) for charting.

    Looks for lines like '- Label: 1,234' or '- Label: $1,234.56'.

    Returns:
        Tuple of (labels, values) or (None, None) if no match.
    """
    pattern = r"^-\s+(.+?):\s+\$?([\d,]+(?:\.\d+)?)"
    matches = re.findall(pattern, answer, re.MULTILINE)
    if len(matches) < 2:
        return None, None
    labels = [m[0].strip() for m in matches]
    values = [float(m[1].replace(",", "")) for m in matches]
    return labels, values


def build_bar_chart(labels, values, title=""):
    """Build a horizontal Plotly bar chart with dark theme."""
    # Reverse for top-to-bottom order in horizontal bars
    labels = list(reversed(labels))
    values = list(reversed(values))

    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        marker=dict(
            color=values,
            colorscale=[[0, "#1f4e79"], [1, "#58a6ff"]],
        ),
        text=[f"${v:,.0f}" if v >= 100 else f"{v:,.0f}" for v in values],
        textposition="outside",
        textfont=dict(color="#c9d1d9", size=11),
    ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=max(200, len(labels) * 36),
        margin=dict(l=10, r=60, t=30, b=10),
        title=dict(text=title, font=dict(size=13, color="#8b949e")),
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(showgrid=False, tickfont=dict(size=12)),
    )
    return fig


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

def render_user_msg(content: str):
    """Render a right-aligned blue user bubble."""
    st.markdown(f'<div class="user-bubble">{content}</div>', unsafe_allow_html=True)


def render_bot_msg(response_dict: dict, elapsed: float = None):
    """Render bot response with badge, markdown, optional chart, sources, timing."""
    qtype = response_dict.get("question_type", "search")
    answer = response_dict.get("answer", "")
    sources = response_dict.get("sources", [])

    # Badge
    badge_map = {
        "aggregation": '<span class="badge-agg">AGGREGATION</span>',
        "lookup": '<span class="badge-lookup">LOOKUP</span>',
        "search": '<span class="badge-search">SEARCH</span>',
    }
    badge = badge_map.get(qtype, badge_map["search"])

    st.markdown(f'{badge}', unsafe_allow_html=True)
    st.markdown(f'<div class="bot-bubble">\n\n{answer}\n\n</div>', unsafe_allow_html=True)

    # Optional chart for breakdown answers
    labels, values = extract_chart_data(answer)
    if labels and values:
        title = ""
        for line in answer.split("\n"):
            if line.startswith("**") and line.endswith("**"):
                title = line.strip("* ")
                break
        fig = build_bar_chart(labels, values, title)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Source pills
    if sources:
        pills = "".join(f'<span class="source-pill">{s}</span>' for s in sources[:6])
        st.markdown(f'<div style="margin-top:4px">{pills}</div>', unsafe_allow_html=True)

    # Timing
    if elapsed is not None:
        label = "instant" if elapsed < 1 else f"{elapsed:.1f}s"
        st.markdown(
            f'<div class="timing-cap">{label} | {qtype}</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar(loader):
    """Render sidebar with KPIs, status bars, controls, examples."""
    with st.sidebar:
        # Logo + subtitle
        st.markdown(
            '<div style="text-align:center; padding: 10px 0 4px 0;">'
            '<span style="font-size:28px; font-weight:700; color:#58a6ff;">Claims Assistant</span><br/>'
            '<span style="font-size:12px; color:#8b949e;">Powered by RAG + Local LLM</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<hr style="margin:10px 0"/>', unsafe_allow_html=True)

        summary = loader.summary

        # KPI tiles 2x2
        total_val_m = summary["total_claim_amount"] / 1_000_000
        st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi-tile">
                <div class="kpi-label">Total Claims</div>
                <div class="kpi-value kpi-blue">{summary['total_claims']:,}</div>
            </div>
            <div class="kpi-tile">
                <div class="kpi-label">Total Value</div>
                <div class="kpi-value kpi-green">${total_val_m:.1f}M</div>
            </div>
            <div class="kpi-tile">
                <div class="kpi-label">Avg Claim</div>
                <div class="kpi-value kpi-amber">${summary['avg_claim_amount']:,.0f}</div>
            </div>
            <div class="kpi-tile">
                <div class="kpi-label">Avg Days Open</div>
                <div class="kpi-value kpi-red">{summary['avg_days_open']}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<hr style="margin:10px 0"/>', unsafe_allow_html=True)

        # Status progress bars
        status_colors = {
            "Open": "blue", "Closed": "green", "Pending": "amber",
            "Rejected": "red", "Under Review": "purple",
        }
        total = summary["total_claims"]
        bars_html = ""
        for status_name, count in summary["status_counts"].items():
            pct = (count / total * 100) if total else 0
            color_class = status_colors.get(status_name, "blue")
            bars_html += f"""
            <div class="status-bar-row">
                <span class="status-bar-label">{status_name}</span>
                <div class="status-bar-track">
                    <div class="status-bar-fill status-bar-fill-{color_class}" style="width:{pct}%"></div>
                </div>
                <span class="status-bar-count">{count:,}</span>
            </div>
            """
        st.markdown(bars_html, unsafe_allow_html=True)

        st.markdown('<hr style="margin:10px 0"/>', unsafe_allow_html=True)

        # Refresh button
        if st.button("Refresh Data", use_container_width=True):
            with st.spinner("Reloading data and rebuilding index..."):
                refresh_pipeline()

        st.markdown('<hr style="margin:10px 0"/>', unsafe_allow_html=True)

        # Example questions
        st.markdown(
            '<div style="font-size:13px; color:#8b949e; font-weight:600; margin-bottom:6px;">Try asking...</div>',
            unsafe_allow_html=True,
        )
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
            if st.button(ex, use_container_width=True, key=f"ex_{hash(ex)}"):
                st.session_state.pending_example = ex
                st.rerun()

        st.markdown('<hr style="margin:10px 0"/>', unsafe_allow_html=True)

        # Timestamps
        st.markdown(
            f'<div style="font-size:11px; color:#484f58;">'
            f'Last loaded: {loader.last_loaded}<br/>'
            f'Data from: {summary["date_range_start"]}<br/>'
            f'Data to: {summary["date_range_end"]}'
            f'</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # --- Header bar ---
    ai_cfg = config.get("ai", {})
    model_name = ai_cfg.get("ollama_model", "gemma3:4b")
    st.markdown(f"""
    <div class="header-bar">
        <div class="header-left">
            <span class="live-dot"></span>
            <span class="header-title">Claims Assistant</span>
        </div>
        <span class="header-model">Model: {model_name}</span>
    </div>
    """, unsafe_allow_html=True)

    # --- Init pipeline ---
    with st.spinner("Loading data and building search index..."):
        try:
            pipeline, loader = initialise_pipeline()
        except Exception as e:
            st.error(f"Failed to initialise: {e}")
            st.stop()

    # --- Sidebar ---
    render_sidebar(loader)

    # --- Session state ---
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_question" not in st.session_state:
        st.session_state.last_question = ""

    # --- Chat history ---
    chat_container = st.container()
    with chat_container:
        if not st.session_state.messages:
            st.markdown("""
            <div class="welcome-box">
                <h3>Welcome to Claims Assistant</h3>
                <p>Ask questions about your claims data in plain English.<br/>
                Try the examples in the sidebar, or type your own below.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            for msg in st.session_state.messages:
                if msg["role"] == "user":
                    render_user_msg(msg["content"])
                else:
                    render_bot_msg(msg, msg.get("elapsed"))

    # --- Input bar (Gemini-style) ---
    question = st.chat_input("Ask about your claims data...")

    # --- Check for example button click ---
    pending = st.session_state.pop("pending_example", None)
    if pending:
        question = pending

    # --- Process question (with dedup guard) ---
    if question and question.strip() and question != st.session_state.get("last_question", ""):
        st.session_state.last_question = question

        st.session_state.messages.append({
            "role": "user",
            "content": question,
        })

        with st.spinner("Thinking..."):
            start = time.time()
            response = pipeline.ask(question)
            elapsed = round(time.time() - start, 1)

        st.session_state.messages.append({
            "role": "assistant",
            "content": response.get("answer", ""),
            "answer": response.get("answer", ""),
            "question_type": response.get("question_type", "search"),
            "sources": response.get("sources", []),
            "entities": response.get("entities", {}),
            "elapsed": elapsed,
        })

        max_history = st_cfg.get("max_chat_history", 50)
        if len(st.session_state.messages) > max_history:
            st.session_state.messages = st.session_state.messages[-max_history:]

        st.rerun()


if __name__ == "__main__":
    main()
