# =============================================================================
# ui/streamlit_app.py
# Professional Dark Theme Streamlit Chat Interface
# =============================================================================

import sys
import re
import time
import logging
import csv
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from data.qvd_loader import ClaimsDataLoader, load_config
from ai.embeddings import ClaimsSearchEngine
from ai.llm import ClaimsLLM, semantic_guardrail, explain_precedents, batch_keyword_discovery
from ai.rag_pipeline import RAGPipeline
from ai.triage_rules import evaluate_deterministic_rules, load_triage_config, save_triage_config
from ai.triage_brain import TriageBrain

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

    /* === Dividers === */
    hr { border-color: #30363d !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Pipeline init (cached)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def initialise_pipeline():
    """Load data and create pipeline. FAISS index built lazily on first search."""
    cfg = load_config("config/config.yaml")
    loader = ClaimsDataLoader(config_path="config/config.yaml")
    loader.load()

    engine = ClaimsSearchEngine(cfg)
    llm = ClaimsLLM(cfg)
    pipeline = RAGPipeline(loader, engine, llm)
    return pipeline, loader

def refresh_pipeline():
    """Clear cache and rerun to force full reload."""
    st.cache_resource.clear()
    st.rerun()

@st.cache_resource(show_spinner=False)
def build_triage_brain(_loader):
    """Build the triage FAISS brain on historical data."""
    brain = TriageBrain()
    brain.build_index(_loader.df)
    return brain

# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def extract_chart_data(answer: str):
    pattern = r"^-\s+(.+?):\s+\$?([\d,]+(?:\.\d+)?)"
    matches = re.findall(pattern, answer, re.MULTILINE)
    if len(matches) < 2:
        return None, None
    labels = [m[0].strip() for m in matches]
    values = [float(m[1].replace(",", "")) for m in matches]
    return labels, values

def build_bar_chart(labels, values, title=""):
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
    st.markdown(f'<div class="user-bubble">{content}</div>', unsafe_allow_html=True)

def render_bot_msg(response_dict: dict, elapsed: float = None):
    qtype = response_dict.get("question_type", "search")
    answer = response_dict.get("answer", "")
    sources = response_dict.get("sources", [])

    badge_map = {
        "aggregation": '<span class="badge-agg">AGGREGATION</span>',
        "lookup": '<span class="badge-lookup">LOOKUP</span>',
        "search": '<span class="badge-search">SEARCH</span>',
        "out_of_scope": '<span class="badge-lookup">OUT OF SCOPE</span>',
        "fuzzy_lookup": '<span class="badge-lookup">FUZZY LOOKUP</span>',
        "pandas_agent": '<span class="badge-search">PANDAS AGENT</span>',
    }
    badge = badge_map.get(qtype, badge_map["search"])

    st.markdown(f'{badge}', unsafe_allow_html=True)
    st.markdown(f'<div class="bot-bubble">\n\n{answer}\n\n</div>', unsafe_allow_html=True)

    labels, values = extract_chart_data(answer)
    if labels and values:
        title = ""
        for line in answer.split("\n"):
            if line.startswith("**") and line.endswith("**"):
                title = line.strip("* ")
                break
        fig = build_bar_chart(labels, values, title)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    if sources:
        pills = "".join(f'<span class="source-pill">{s}</span>' for s in sources[:6])
        st.markdown(f'<div style="margin-top:4px">{pills}</div>', unsafe_allow_html=True)

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
    with st.sidebar:
        st.markdown(
            '<div style="text-align:center; padding: 10px 0 4px 0;">'
            '<span style="font-size:28px; font-weight:700; color:#58a6ff;">Claims Assistant</span><br/>'
            '<span style="font-size:12px; color:#8b949e;">Powered by RAG + Local LLM</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<hr style="margin:10px 0"/>', unsafe_allow_html=True)

        summary = loader.summary
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

        if st.button("Refresh Data", use_container_width=True):
            with st.spinner("Reloading data and rebuilding index..."):
                refresh_pipeline()

        st.markdown('<hr style="margin:10px 0"/>', unsafe_allow_html=True)

        st.markdown(
            '<div style="font-size:13px; color:#8b949e; font-weight:600; margin-bottom:6px;">Try asking...</div>',
            unsafe_allow_html=True,
        )
        examples = [
            "How many claims closed this year?",
            "Total incurred by Major LOB for the UK",
            "What are the different UWY we have?",
            "Show me pending claims in Canada",
            "Which region has the most claims?",
            "Breakdown of reserves vs paid by country",
            "Top 5 adjusters by claim count",
            "Average days open for open property damage claims",
        ]
        for ex in examples:
            if st.button(ex, use_container_width=True, key=f"ex_{hash(ex)}"):
                st.session_state.pending_example = ex
                st.rerun()

        st.markdown('<hr style="margin:10px 0"/>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# HITL Fast Track Triage UI
# ---------------------------------------------------------------------------

def log_triage_decision(claim_id: str, ai_decision: str, human_decision: str):
    """Appends the adjuster's final decision to our shadow-mode training log."""
    log_path = "data/ai_feedback_log.csv"
    os.makedirs("data", exist_ok=True)
    
    file_exists = os.path.isfile(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "claim_id", "ai_decision", "human_decision", "final_status"])
        
        final_status = "FAST TRACKED" if human_decision == "Approve" else "MANUAL REVIEW"
        writer.writerow([
            datetime.now().isoformat(),
            claim_id,
            ai_decision,
            human_decision,
            final_status
        ])

def render_triage_queue_tab(loader, brain):
    """Renders the Triage Dashboard with AI precedent analysis."""
    st.markdown("### Pending Claims for Review")
    st.markdown("Review claims with AI precedent analysis. Your feedback trains the system instantly.")

    pending_claims = loader.df.head(10)

    for idx, row in pending_claims.iterrows():
        claim_id = str(row.get("Claim Number", row.get("claim_number", f"UNK-{idx}")))
        lob = str(row.get("Major LOB", row.get("major_lob", "N/A")))
        reserve = pd.to_numeric(row.get("Nominal Reserve", row.get("outstanding_reserve_usd", 0)), errors="coerce")
        desc = str(row.get("Loss Description", row.get("loss_description", "No description.")))

        # 1. Deterministic Rules
        try:
            math_pass, math_results = evaluate_deterministic_rules(row)
        except Exception as e:
            math_pass = False
            math_results = [{"name": "System Error", "passed": False, "detail": f"Error: {e}"}]

        # 2. Semantic Guardrail
        if not desc or len(desc.strip()) < 10:
            llm_pass = True
            llm_reason = "Description too short to evaluate."
        else:
            try:
                llm_result = semantic_guardrail(desc)
                llm_pass = llm_result.get("semantic_pass", False)
                llm_reason = llm_result.get("reason", "Unknown")
            except Exception as e:
                llm_pass, llm_reason = False, f"LLM Guardrail failed: {e}"

        # 3. Precedent Analysis (FAISS Brain)
        precedents = brain.find_precedents(row, top_k=5)
        prec_summary = brain.summarize_precedents(precedents)

        # 4. Overall verdict
        overall_ai_pass = math_pass and llm_pass
        ai_verdict = "FAST TRACK" if overall_ai_pass else "MANUAL REVIEW"
        header_icon = "🟢" if overall_ai_pass else "🔴"

        # 5. UI Card
        with st.expander(f"{header_icon} {claim_id} | LOB: {lob} | Reserve: ${reserve:,.2f}"):
            st.write(f"**Loss Description:** {desc}")
            st.markdown("---")

            # Rules Engine
            st.markdown("**Deterministic Rule Engine:**")
            for r in math_results:
                safe_detail = str(r['detail']).replace('$', '\\$')
                icon = "🟢" if r["passed"] else "🔴"
                st.markdown(f"{icon} **{r['name']}**: {safe_detail}")

            # Semantic Guardrail
            st.markdown("**Semantic Guardrail (LLM):**")
            safe_llm_reason = str(llm_reason).replace('$', '\\$')
            if llm_pass:
                st.markdown(f"🟢 **Passed**: {safe_llm_reason}")
            else:
                st.markdown(f"🔴 **Failed**: {safe_llm_reason}")

            st.markdown("---")

            # Precedent Analysis (NEW)
            st.markdown("**Precedent Analysis (Similar Past Claims):**")
            safe_summary = prec_summary.replace('$', '\\$')
            st.markdown(safe_summary)

            # Show individual precedents in a compact view
            if precedents:
                for i, p in enumerate(precedents, 1):
                    ft_icon = "🟢" if p["ft_outcome"] == "Y" else "🔴"
                    sim_pct = f"{p['similarity']:.0%}"
                    safe_desc_p = str(p.get("loss_description", ""))[:150].replace('$', '\\$')
                    human_tag = ""
                    if p.get("human_decision"):
                        h_icon = "👍" if p["human_decision"] == "Approve" else "👎"
                        human_tag = f" | Adjuster: {h_icon} {p['human_decision']}"
                    st.markdown(
                        f'<div style="background:#0d1117; border:1px solid #30363d; border-radius:6px; '
                        f'padding:8px 12px; margin:4px 0; font-size:12px;">'
                        f'{ft_icon} <strong>{p["claim_number"]}</strong> ({sim_pct} match){human_tag}<br/>'
                        f'<span style="color:#8b949e;">{safe_desc_p}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            st.markdown("---")
            st.markdown(f"**AI Recommendation:** `{ai_verdict}`")

            # HITL Buttons
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Agree (Approve)", key=f"agree_{claim_id}", use_container_width=True):
                    log_triage_decision(claim_id, ai_verdict, "Approve")
                    brain.embed_feedback(
                        claim_number=claim_id,
                        loss_description=desc,
                        ft_outcome="Y" if overall_ai_pass else "N",
                        human_decision="Approve",
                        major_lob=lob,
                        reserve=float(reserve) if not pd.isna(reserve) else 0,
                    )
                    st.success(f"Claim {claim_id} approved. Brain updated instantly.")
            with c2:
                if st.button("Disagree (Manual)", key=f"disagree_{claim_id}", use_container_width=True):
                    log_triage_decision(claim_id, ai_verdict, "Disagree")
                    brain.embed_feedback(
                        claim_number=claim_id,
                        loss_description=desc,
                        ft_outcome="Y" if overall_ai_pass else "N",
                        human_decision="Disagree",
                        major_lob=lob,
                        reserve=float(reserve) if not pd.isna(reserve) else 0,
                    )
                    st.warning(f"Claim {claim_id} routed to manual. Brain updated instantly.")


def render_optimizer_tab(loader, brain):
    """Render the Rule Optimizer tab for manager review."""
    st.markdown("### Rule Optimizer")
    st.markdown("Review AI-suggested changes based on human feedback patterns.")

    triage_cfg = load_triage_config()
    current_rules = triage_cfg.get("rules", {})

    # Current thresholds display
    st.markdown("**Current Active Thresholds:**")
    current_html = '<div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:10px 0;">'
    current_html += (
        f'<div style="background:#1c2128; border:1px solid #30363d; border-radius:8px; padding:12px; text-align:center;">'
        f'<div style="font-size:11px; color:#8b949e; text-transform:uppercase;">Reserve Limit</div>'
        f'<div style="font-size:20px; font-weight:700; color:#58a6ff;">\\${current_rules.get("reserve_limit", {}).get("max_value", 3000):,.0f}</div>'
        f'</div>'
    )
    current_html += (
        f'<div style="background:#1c2128; border:1px solid #30363d; border-radius:8px; padding:12px; text-align:center;">'
        f'<div style="font-size:11px; color:#8b949e; text-transform:uppercase;">Max Reporting Lag</div>'
        f'<div style="font-size:20px; font-weight:700; color:#58a6ff;">{current_rules.get("reporting_lag", {}).get("max_days", 14)} days</div>'
        f'</div>'
    )
    current_html += '</div>'
    st.markdown(current_html, unsafe_allow_html=True)

    blocked_injuries = current_rules.get("injury_keywords", {}).get("blocked_keywords", [])
    blocked_lobs = current_rules.get("lob_exclusions", {}).get("blocked_lobs", [])
    existing_red_flags = triage_cfg.get("semantic_guardrail", {}).get("red_flag_keywords", [])

    st.markdown(f"**Blocked Injury Keywords:** {', '.join(blocked_injuries)}")
    st.markdown(f"**Blocked LOBs:** {', '.join(blocked_lobs)}")
    st.markdown(f"**Semantic Red Flags:** {', '.join(existing_red_flags) if existing_red_flags else 'None configured'}")

    st.markdown('<hr style="margin:16px 0"/>', unsafe_allow_html=True)

    # Feedback stats
    feedback_path = Path("data/ai_feedback_log.csv")
    if feedback_path.is_file():
        feedback_df = pd.read_csv(feedback_path)
        disagree_count = (feedback_df["human_decision"].str.lower() == "disagree").sum()
        agree_count = len(feedback_df) - disagree_count
        st.markdown(
            f"**Feedback Log:** {len(feedback_df)} entries | "
            f"{agree_count} agreements | {disagree_count} disagreements"
        )

        # Brain stats
        st.markdown(f"**Brain Memory:** {brain.index.ntotal:,} vectors in FAISS index")

        st.markdown('<hr style="margin:16px 0"/>', unsafe_allow_html=True)

        # LLM Keyword Discovery
        if disagree_count > 0:
            st.markdown("**LLM Keyword Discovery (from rejected claims):**")
            disagreed_ids = set(
                feedback_df[feedback_df["human_decision"].str.lower() == "disagree"]["claim_id"].astype(str)
            )
            claim_col = "Claim Number" if "Claim Number" in loader.df.columns else "claim_number"
            desc_col = "Loss Description" if "Loss Description" in loader.df.columns else "loss_description"
            rejected_descs = loader.df[
                loader.df[claim_col].astype(str).isin(disagreed_ids)
            ][desc_col].dropna().tolist()

            if rejected_descs and st.button("Discover New Keywords", use_container_width=True, key="run_keywords"):
                with st.spinner("Analyzing rejected descriptions with local LLM..."):
                    new_kws = batch_keyword_discovery(rejected_descs, existing_keywords=existing_red_flags)
                if not new_kws:
                    st.success("No new keyword patterns detected.")
                else:
                    st.session_state["keyword_proposals"] = new_kws

            for kw in st.session_state.get("keyword_proposals", []):
                st.markdown(
                    f'<div style="background:#1c2128; border:1px solid #30363d; border-radius:8px; '
                    f'padding:10px; margin:6px 0;">'
                    f'<span style="color:#f85149; font-weight:700;">{kw["keyword"]}</span>'
                    f'<div style="font-size:12px; color:#8b949e; margin-top:2px;">{kw["reason"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.info("No human feedback logged yet. Use the Triage Queue to build feedback data.")

    st.markdown('<hr style="margin:16px 0"/>', unsafe_allow_html=True)

    # Manual threshold override
    st.markdown("**Manual Threshold Override:**")
    st.markdown(
        '<div style="font-size:12px; color:#8b949e; margin-bottom:8px;">'
        'Adjust thresholds directly. Changes take effect after clicking Apply.'
        '</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        new_reserve = st.number_input(
            "Reserve Limit ($)", min_value=500, max_value=50000,
            value=int(current_rules.get("reserve_limit", {}).get("max_value", 3000)),
            step=250, key="new_reserve",
        )
    with c2:
        new_lag = st.number_input(
            "Max Reporting Lag (days)", min_value=1, max_value=90,
            value=int(current_rules.get("reporting_lag", {}).get("max_days", 14)),
            step=1, key="new_lag",
        )

    new_kw_input = st.text_input(
        "Add Red Flag Keywords (comma-separated)",
        placeholder="e.g. subrogation, independent medical exam",
        key="new_kw_input",
    )

    if st.button("Apply All Changes", type="primary", use_container_width=True, key="apply_changes"):
        cfg = load_triage_config()
        cfg["rules"]["reserve_limit"]["max_value"] = new_reserve
        cfg["rules"]["reporting_lag"]["max_days"] = new_lag

        if new_kw_input.strip():
            new_kws = [kw.strip().lower() for kw in new_kw_input.split(",") if kw.strip()]
            existing = cfg.get("semantic_guardrail", {}).get("red_flag_keywords", [])
            for kw in new_kws:
                if kw not in existing:
                    existing.append(kw)
            cfg["semantic_guardrail"]["red_flag_keywords"] = existing

        # Apply keyword proposals if any
        for kw in st.session_state.get("keyword_proposals", []):
            existing = cfg.get("semantic_guardrail", {}).get("red_flag_keywords", [])
            if kw["keyword"] not in existing:
                existing.append(kw["keyword"])
            cfg["semantic_guardrail"]["red_flag_keywords"] = existing

        from datetime import datetime as _dt
        cfg["last_updated"] = _dt.now().isoformat()
        cfg["updated_by"] = "manager_dashboard"
        cfg["version"] = cfg.get("version", 0) + 1

        save_triage_config(cfg)
        st.session_state.pop("keyword_proposals", None)
        st.success(
            f"Configuration updated! Version {cfg['version']}. "
            f"Reserve: \\${new_reserve:,} | Lag: {new_lag} days"
        )
        st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
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

    with st.spinner("Loading data and building search index..."):
        try:
            pipeline, loader = initialise_pipeline()
        except Exception as e:
            st.error(f"Failed to initialise: {e}")
            st.stop()

    with st.spinner("Building triage brain..."):
        brain = build_triage_brain(loader)

    render_sidebar(loader)

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_question" not in st.session_state:
        st.session_state.last_question = ""

    question = st.chat_input("Ask about your claims data...")

    pending = st.session_state.pop("pending_example", None)
    if pending:
        question = pending

    new_question = False
    if question and question.strip() and question != st.session_state.get("last_question", ""):
        st.session_state.last_question = question
        st.session_state.messages.append({
            "role": "user",
            "content": question,
        })
        new_question = True

    # --- Tabs ---
    tab_chat, tab_ft, tab_opt = st.tabs(["Chat Assistant", "Fast Track Triage", "Rule Optimizer"])

    # ===================== TAB 1: Chat =====================
    with tab_chat:
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

        if new_question:
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

    # ===================== TAB 2: Fast Track =====================
    with tab_ft:
        render_triage_queue_tab(loader, brain)

    # ===================== TAB 3: Rule Optimizer =====================
    with tab_opt:
        render_optimizer_tab(loader, brain)

if __name__ == "__main__":
    main()