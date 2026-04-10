# Claims Assistant — Full Overhaul Design
**Date:** 2026-04-10  
**Scope:** Code reliability, reasoning power, and UI improvement  
**Interfaces:** Streamlit (primary) + Microsoft Teams Bot (primary)  
**Model:** gemma3:4b via Ollama (local, CPU-only)

---

## Overview

Full overhaul of the Claims ChatGPT system across five layers:

1. **Query Analysis Layer** — replace keyword routing with LLM-based intent + entity extraction
2. **RAG Pipeline** — pre-filtered FAISS search, score thresholding, retry + fallback chain
3. **Prompt Engineering** — chain-of-thought, structured output rules, anti-hallucination rules
4. **Streamlit UI** — Professional Dark full rebuild with inline charts and response badges
5. **Teams Bot** — richer Adaptive Cards mapped to response types, proactive notifications wired

---

## Section 1: Query Analysis Layer

### Problem
`detect_question_type()` in `ai/rag_pipeline.py` uses substring matching (`"how many" in q`). Misses natural variations ("give me the count of", "what's the total open", "list all") and incorrectly routes many questions.

### Solution: `QueryAnalyzer` class (new file: `ai/query_analyzer.py`)

Makes a fast structured LLM call before any routing. Returns a validated JSON object:

```json
{
  "intent": "aggregation | lookup | search | trend | comparison",
  "claim_id": "CLM0000042 | null",
  "status": "Open | Closed | Pending | Rejected | Under Review | null",
  "region": "London | North West | South East | Midlands | Scotland | Wales | null",
  "claim_type": "Medical | Motor | Property | Liability | Life | Travel | null",
  "date_from": "YYYY-MM-DD | null",
  "date_to": "YYYY-MM-DD | null",
  "high_value": true | false
}
```

**Intent definitions:**
- `aggregation` — counts, totals, averages, percentages, breakdowns
- `lookup` — specific claim by ID
- `search` — semantic search for claims matching criteria (no specific ID)
- `trend` — patterns over time
- `comparison` — across regions, types, or periods

**Fallback:** If LLM call fails or JSON is malformed → fall back to existing keyword matching in `detect_question_type()`. Never hard-fails.

**Performance:** Uses a minimal prompt (< 100 tokens) so response time < 1s on gemma3:4b.

---

## Section 2: Smarter RAG Pipeline

### 2a — Pre-filtered FAISS Search
Before searching the full FAISS index, the extracted entities from `QueryAnalyzer` filter `loader.df` to a relevant subset. FAISS then searches only vectors belonging to that subset.

```python
# Example: "high value pending motor claims in London"
# QueryAnalyzer extracts: status=Pending, claim_type=Motor, region=London, high_value=True
# → filter df to matching rows
# → search FAISS index of only those rows
# → result: highly relevant chunks, no noise
```

**Implementation note:** The FAISS index stores the full dataset — it is never rebuilt per query. Pre-filtering works as follows: extract the `df_index` values of rows matching the entity filters, then call FAISS `search()` with `top_k × 5` to get a wider candidate set, then post-filter candidates to only those whose `df_index` is in the pre-filtered set, then take the top `top_k` by score. This avoids rebuilding the index while still concentrating results on relevant rows.

### 2b — Score Threshold + Re-ranking
- Drop any FAISS result with cosine similarity < 0.35
- If fewer than 2 results survive → widen search (threshold 0.20, top_k × 2)
- If still no results → return empty, do not call LLM with bad context

### 2c — LLM Retry + Fallback Chain
```
Attempt 1: LLM call, timeout=30s
     ↓ fail or timeout
Attempt 2: retry with simplified prompt (no chain-of-thought block), timeout=20s
     ↓ fail or timeout
Fallback: answer from summary stats + message "AI engine unavailable, showing summary data"
```
User always receives a meaningful response. No bare Python exceptions surface to the UI.

### Files changed
- `ai/rag_pipeline.py` — updated `RAGPipeline.ask()` to use `QueryAnalyzer` and pre-filtering
- `ai/query_analyzer.py` — new file
- `ai/embeddings.py` — add `search_with_filter(df_indices, query, top_k)` method

### Files unchanged
- `data/qvd_loader.py`
- `data/text_chunker.py`
- FAISS index build logic

---

## Section 3: Prompt Engineering

### New prompt structure in `ai/llm.py` — `build_prompt()`

**Block 1 — Role + Hard Rules**
```
You are a Claims Data Analyst for an insurance company.

Rules you must never break:
- Only use numbers explicitly present in the data below. Never invent or estimate figures.
- If a Claim ID is mentioned in context, cite it in your answer.
- Format all currency as £ with comma separators (e.g. £45,000).
- If the answer is not in the provided data, say exactly: "I don't have that information in the current dataset."
- Do not apologise or hedge. Give direct, factual answers.
```

**Block 2 — Chain-of-thought instruction (internal only)**
```
Before writing your answer, reason through these steps silently:
1. What exactly is being asked?
2. Which rows or summary figures are relevant?
3. What calculation or lookup produces the answer?
Output ONLY the final answer — no reasoning steps in your response.
```

**Block 3 — Structured context** (same as current, cleaner formatting)

**Block 4 — Output format rules (new)**
```
Format rules:
- 3 or more items → markdown table with headers
- Single number answer → bold it with **£X,XXX**
- List of claims → bullet points with Claim ID first
- Comparison → side-by-side table
```

---

## Section 4: Streamlit UI — Full Rebuild

### Design language
- **Theme:** Professional Dark (`#0d1117` background, `#161b22` cards, `#30363d` borders)
- **Accent:** Microsoft Blue (`#0078d4`, `#58a6ff`)
- **Status colours:** Green `#3fb950` (amounts/positive), Amber `#d29922` (warnings), Red `#f85149` (overdue/rejected)

### Layout
```
┌──────────────────────────────────────────────────────────────┐
│  SIDEBAR (240px)          │  HEADER (full width)             │
│  ─ Logo + subtitle        │  ● Live · gemma3:4b · N claims   │
│  ─ 4 KPI tiles (2×2 grid) ├─────────────────────────────────┤
│  ─ Status progress bars   │  CHAT AREA (scrollable)          │
│  ─ Quick-question buttons │  ─ User bubbles (right-aligned)  │
│  ─ Refresh Data button    │  ─ Bot bubbles (left-aligned)    │
│  ─ Timestamps             │    with badge + content + meta   │
│                           ├─────────────────────────────────┤
│                           │  INPUT BAR                       │
│                           │  [rounded input field]  [send]   │
└───────────────────────────┴──────────────────────────────────┘
```

### Response types → rendering

| Badge | Colour | Content |
|---|---|---|
| ⚡ Aggregation | Blue | Text answer + inline bar chart (Plotly) |
| 🎯 Lookup | Amber | Fact table with colour-coded values |
| 🔍 AI Search | Green | Text answer + results table + source tags |
| ⚠️ Error | Red | Error message + suggestion |

### Inline charts
- Plotly `go.Bar` horizontal bar charts for region/type/status breakdowns
- Rendered inside `st.plotly_chart()` directly in the chat message container
- Dark theme (`template="plotly_dark"`, transparent background)
- Height: 250px for ≤6 bars, 400px for more

### Source tags
Below every AI Search answer: small dark pill badges showing matched Claim IDs.

### Timing indicator
- < 1s → "⚡ instant"
- ≥ 1s → "⏱ X.Xs · gemma3:4b"

### Files changed
- `ui/streamlit_app.py` — complete rewrite
  - New CSS (Professional Dark)
  - `render_aggregation_response()` with Plotly chart
  - `render_lookup_response()` with colour-coded table
  - `render_search_response()` with table + source tags
  - `render_sidebar()` updated with KPI grid

---

## Section 5: Teams Bot

### Response type → Adaptive Card mapping

| Response type | Card layout |
|---|---|
| Aggregation | KPI fact blocks + bar chart image (base64 Plotly PNG) |
| Lookup | Structured fact table with coloured status badge |
| Search | Answer text + source claim ID action buttons |
| Error | Red alert card + "Try rephrasing" button |
| Notification | Alert card with claim details + View/Assign/Dismiss buttons |

### Proactive notifications wired
`notifications/rules_engine.py` → `notifications/teams_notify.py` connected to `scheduler/refresh_scheduler.py`:
- High value claim (> £100k) → immediate Teams alert
- Daily 07:00 → summary Adaptive Card pushed to channel
- Data refresh complete → confirmation card

### Bot commands tightened
```
@bot help     → Adaptive Card with example questions
@bot refresh  → triggers reload, replies with completion card
@bot status   → LLM health + data freshness card
```

### Files changed
- `bot/adaptive_cards.py` — new response-type card templates
- `bot/teams_bot.py` — map RAGPipeline response types to card builders
- `notifications/rules_engine.py` — connected to scheduler
- `scheduler/refresh_scheduler.py` — wired to notifications

### Files unchanged
- `bot/bot_server.py`
- Azure Bot registration / manifest

---

## What Is NOT Changed

| Component | Reason |
|---|---|
| `data/qvd_loader.py` | Works correctly, no issues found |
| `data/text_chunker.py` | Row-to-text conversion is good |
| `ai/embeddings.py` (index build) | FAISS build logic is correct |
| `config/config.yaml` | Structure stays, 2 new keys added |
| `requirements.txt` | `plotly` added, rest unchanged |
| Azure Bot registration | No change needed |

---

## New Config Keys

```yaml
ai:
  query_analyzer_timeout: 8       # seconds for QueryAnalyzer LLM call
  faiss_score_threshold: 0.35     # drop results below this cosine similarity
  llm_retry_count: 2              # number of LLM attempts before fallback
  llm_timeout: 30                 # seconds per LLM attempt
```

---

## New Dependency

```
plotly>=5.0.0    # inline charts in Streamlit + PNG export for Teams cards
```

---

## File Change Summary

| File | Action |
|---|---|
| `ai/query_analyzer.py` | **New** |
| `ai/rag_pipeline.py` | **Rewrite** |
| `ai/llm.py` | **Update** (prompt blocks) |
| `ai/embeddings.py` | **Update** (filter search method) |
| `ui/streamlit_app.py` | **Rewrite** |
| `bot/adaptive_cards.py` | **New** |
| `bot/teams_bot.py` | **Update** |
| `notifications/rules_engine.py` | **Update** |
| `scheduler/refresh_scheduler.py` | **Update** |
| `config/config.yaml` | **Update** (4 new keys) |
| `requirements.txt` | **Update** (plotly) |
