# Presentation Builder Skill — Design Spec

**Date:** 2026-05-09
**Scope:** Enterprise-grade SKILL.md that ingests PDF/XLSX/CSV, performs world-class data analysis, and produces board-ready PPTX presentations.
**Skill Format:** Anthropic SKILL.md style (markdown + bundled Python scripts; runs on internal AI platform supporting both Opus 4.7 and GPT-5).
**Output:** Branded `.pptx` file via Slide Masters from corporate template.
**V1 Input Scope:** Single file per run. Multi-file synthesis deferred to V2 roadmap.

---

## Overview

The skill transforms raw enterprise files (PDF, Excel, CSV) into executive-ready PowerPoint decks via a two-stage pipeline:

1. **Stage 1 — Profile + Outline:** Ingest, profile, infer story shape, propose deck outline. User confirms before any deck is built.
2. **Stage 2 — Build:** Per-slide analysis → chart/table → bottom-up narrative → assembled PPTX via corporate template.

Core design principles:

- **Degrade, don't die.** Every failure mode produces a slide or an Exclusions report. Single bad slide never kills the deck.
- **Never silent fail.** Every skipped or modified slide has a documented reason in a final Exclusions slide.
- **Math integrity.** Narrative claims regex-checked against analysis output (0.01% tolerance for float precision).
- **Privacy first.** PII detection in `profile.py` excludes sensitive columns before the LLM ever sees them.
- **Slide economy.** Max 6 bullets per slide. Visual Priority: data slides must have a chart or table. The "So What?" rule: every slide ends with synthesis, not raw observation.

---

## Section 1: Skill Structure & Lifecycle

### Tech Stack (locked)

| Layer | Library | Rationale |
|---|---|---|
| Ingestion (XLSX/CSV) | **Polars** | 10–50× faster than pandas; handles enterprise file sizes without sandbox crashes. |
| Ingestion (PDF) | **PyMuPDF** | High-fidelity table extraction — the failure point of most AI tools on PDFs. |
| Analysis | Polars + scipy/numpy | Correlations, outlier detection, trend slope, group-bys. |
| Visualization | **Matplotlib + Seaborn** | Professional static PNG/SVG output, embeds cleanly into PPTX image placeholders. |
| Presentation Build | **python-pptx** | Enterprise standard. Supports Slide Masters from corporate template. |

### Directory Layout

```
presentation-builder/
├── SKILL.md                    # Instructions to invoking LLM (rules + execution pipeline)
├── scripts/
│   ├── ingest.py               # PDF (PyMuPDF) / XLSX/CSV (Polars) → Polars DataFrame + metadata
│   ├── profile.py              # Schema, stats, outlier detection, PII scrubbing
│   ├── context.py              # Context Awareness Engine — column patterns → story shape
│   ├── outline.py              # Outline JSON: Exec Summary, sections, deep-dives, viability check
│   ├── analyze.py              # Per-slide computations; output as flat KV store
│   ├── aggregator.py           # Reduces large DataFrames to Chart-Ready JSON (sandbox stability)
│   ├── chart.py                # Seaborn/Matplotlib → branded PNG (300 DPI, brand hex codes)
│   ├── tables.py               # Native PPTX editable table builder (≤10×5 only)
│   ├── narrative.py            # LLM bottom-up reasoning (Observe → Analyze → Synthesize)
│   ├── layouts.py              # Layout picker; render-mode decision (table vs image)
│   └── build_pptx.py           # Composes deck via Presentation(corporate_template.pptx)
├── assets/
│   ├── company_template.pptx   # PRIMARY brand source (Slide Masters define fonts/colors/logo)
│   └── default_template.pptx   # Fallback if corporate template absent
├── tests/
│   ├── fixtures/               # Sample files for unit + e2e tests
│   ├── golden/                 # Reference PPTX for structure-diff regression tests
│   └── test_*.py
└── requirements.txt
```

### Lifecycle

**Stage 1 — Profile + Outline (~10 sec)**
1. User: "Build deck from `q3_sales.xlsx`, audience: exec leadership."
2. SKILL.md instructs LLM to run `ingest.py` → `profile.py` → `context.py` → `outline.py`.
3. LLM presents outline JSON: Exec Summary, section slides, auto-flagged deep-dives, chart types, viability exclusions.
4. **User gate:** confirm / edit / drop slides.

**Stage 2 — Build (~30 sec)**
5. Per slide: `analyze.py` → `aggregator.py` → `chart.py` or `tables.py` → `narrative.py`.
6. `build_pptx.py` opens corporate template, fills Slide Master layouts via `layouts.py`, writes speaker notes (Observe + Analyze), saves output.
7. Returns `.pptx` path.

### Multi-Model Routing

Skill is **model-agnostic at runtime** — whichever model invokes it executes the scripts. SKILL.md notes routing guidance for users:

- **Opus 4.7** preferred for `narrative.py` and `outline.py` (instruction following, subtle reasoning).
- **GPT-5** preferred for ad-hoc complex code generation if user asks the skill to extend layouts beyond the standard set.

Cross-model orchestration inside the skill is explicitly **out of scope** (fragile, slow). User picks the invoking model upfront.

---

## Section 2: Component Contracts

Each module: single purpose, JSON in/out, independently testable.

### `ingest.py`
- **Input:** file path
- **Routing:** detects type by extension + magic bytes; routes to PyMuPDF (PDF) or Polars (XLSX/CSV).
- **PDF handling:** extracts both narrative text blocks AND tables (PyMuPDF table mode).
- **Output:** `{dataframe: polars.DataFrame, metadata: {source, rows, cols, parse_warnings, file_type}}`
- **Failure:** structured error JSON; never raises to LLM.

### `profile.py`
- **Input:** DataFrame
- **Output:** `{schema, dtypes, null_pct, distributions, outliers: [{col, value, deviation_pct}], date_range, pii_columns: [...]}`
- **Outlier rule:** value >20% deviation from mean (or IQR-based for skewed distributions) → flagged.
- **PII detection:**
  - Column-name regex: `(?i)(ssn|social.security|credit.card|cc.num|passport|home.address|tax.id|dob|date.of.birth|email|phone)`
  - Value-pattern checks: SSN regex (`\d{3}-\d{2}-\d{4}`), credit card (Luhn check on numeric columns), email/phone regex sample on string columns.
  - PII columns added to `pii_columns` and excluded from all downstream stages.

### `context.py` (Context Awareness Engine)
- **Input:** profile JSON
- **Pattern matchers infer story shape:**
  - `Date` column → time-series story (trend, seasonality, YoY).
  - `Revenue` + `Cost` → margin story (compute gross margin).
  - `Region`/`Segment` + numeric → comparative story (top/bottom-N, share of total).
  - `Date` + `Region` → cohort/dimension cross-cut.
  - Survey-like columns (Likert scale, sentiment) → distribution story.
- **Output:** `{story_type, suggested_sections: [...], required_computations: [...]}`
- **Purpose:** turns raw data into deck angle. Without this, the skill defaults to listing facts (the failure mode of most AI tools).

### `outline.py`
- **Input:** profile + context output
- **Builds outline JSON:**
  - Slide 1: Executive Summary (3 takeaways + ≥1 delta + Recommended Next Step).
  - Section slides per `suggested_sections`.
  - Auto-inserted Deep-Dive slides for each flagged outlier.
- **Data Viability Check (Ghost Slide Prevention):** for each proposed slide, check `null_pct` of required columns. If any >15% → mark `{status: "excluded", reason: "Cost column 40% null"}`.
- **Output:** `{slides: [{n, layout, title, content_type, computation_id, chart_spec, status}]}`

### `analyze.py`
- **Input:** DataFrame + computation_id from outline.
- **Runs the specific stat:** correlation, trend slope, group-by, margin calc, outlier root-cause, etc.
- **Output:** **flat key-value store**, e.g., `{"q3_revenue": 4200000, "sep_mom_delta_pct": -7.0, "north_share_pct": 40.0}`. Flat structure makes narrative regex-checking fast.

### `aggregator.py` (Polars-to-Matplotlib Bridge)
- **Input:** DataFrame slice + chart_spec.
- **Reduces** to Chart-Ready JSON (e.g., 3 trend points, 5 category bars). Never returns >100 data points.
- **Output:** `{labels: [...], values: [...], series_name, chart_type}`
- **Why:** prevents passing 50K-row DataFrames to chart rendering — sandbox stability.

### `chart.py` (Dynamic Visual Selection)
- **Input:** Chart-Ready JSON + brand hex codes (read from corporate template's Slide Master color scheme via python-pptx; if template missing or no theme metadata, hardcoded fallback constants live at top of `chart.py`).
- **Renders:** Seaborn/Matplotlib → PNG at 300 DPI, brand colors applied.
- **Chart-type picker:**
  - Time series → line chart
  - Categorical → bar chart
  - Share of total → stacked bar (no pie charts for >5 categories)
  - Correlation → scatter
  - Distribution → histogram or violin
- **Output:** `{png_path, dimensions}` for placeholder fit.

### `tables.py`
- **Input:** DataFrame slice
- **Builds native PPTX `pptx.shapes.table`** (editable, branded fonts, alternating row fill).
- **Use case:** KPI tables, top-N lists where users want raw numbers.
- **Output:** table shape descriptor for `build_pptx.py`.

### `narrative.py` (Bottom-Up Executive Narrative)
- **Input:** flat KV store from `analyze.py`.
- **Three-step LLM prompt chain per slide:**
  1. **Observe** — "What does the data literally show?" → factual statement (e.g., "Sep revenue = $3.9M").
  2. **Analyze** — "What's the comparison or trend?" → relational (e.g., "Sep down 7% MoM; first decline since May").
  3. **Synthesize** — "What does this MEAN for the business?" → final insight (e.g., "Q3 momentum stalled in September — investigate before Q4 commit").
- **Slide gets:** synthesis only.
- **Speaker notes get:** Observe + Analyze + Synthesize (full audit trail).
- **Hallucination guard:**
  - Extract every numeric claim from generated narrative via regex.
  - Cross-check each against the flat KV store from `analyze.py`.
  - Tolerance: `abs(claim - actual) / actual < 0.0001` (0.01%) → match (handles float precision).
  - Mismatch → regenerate once. Second mismatch → strip claim, log warning in speaker notes.
- **PII guard:** narrative cannot reference any column listed in `profile.pii_columns`.
- **Constraint:** ≤6 bullets per slide enforced.

### `layouts.py`
- **Input:** content_type + slice dimensions.
- **Layout mapping (matches Slide Master layout names in `company_template.pptx`):**
  - Title only → "Title Slide"
  - Single chart + insight → "Image + Text"
  - Two charts side-by-side → "Two-Column"
  - Big number callout → "Big Number"
  - Native table → "Table Layout"
- **Render-mode decision rule:**
  - Slice >10 rows OR >5 cols → image (chart or rendered table screenshot).
  - Slice ≤10 rows AND ≤5 cols → native table.
  - **Why:** large native PPTX tables overflow slide boundaries — images are safer for silent builds.
- **Fallback:** if layout name absent from template, use closest match (or "Title and Content"); warn in summary.

### `build_pptx.py`
- **Input:** outline JSON + per-slide assets (PNG paths, table descriptors, narrative bullets).
- **Opens** `Presentation(company_template.pptx)` — brand inherits via Slide Masters.
- **For each slide:**
  - Pick layout via `layouts.py`.
  - Fill placeholders: charts → image placeholder, bullets → body placeholder, tables → table placeholder.
  - Write Observe + Analyze + Synthesize to speaker notes.
- **Final slide:** Exclusions slide (only if any exclusions occurred — see Appendix B).
- **Output:** `output.pptx` path.

---

## Section 3: Data Flow (Worked Example)

Sample: `q3_sales.xlsx` — 12 columns (Date, Region, Product, Revenue, Cost, Units, etc.), 50K rows.

### Stage 1 — Profile + Outline

```
User invocation
  │
  ▼
SKILL.md loads → instructs LLM
  │
  ▼
ingest.py(q3_sales.xlsx)
  │  Polars reads → DataFrame (50K × 12)
  │  metadata: {rows: 50000, cols: 12, parse_warnings: []}
  ▼
profile.py(df)
  │  schema: {Date: date, Region: str, Revenue: float, Cost: float, ...}
  │  null_pct: {Cost: 0.3%}
  │  outliers: [{col: Revenue, value: 1.2M, deviation_pct: 340%}]
  │  date_range: 2026-07-01 → 2026-09-30
  │  pii_columns: []
  ▼
context.py(profile)
  │  matches: Date + Revenue + Cost + Region present
  │  story_type: "time-series margin breakdown by region"
  │  suggested_sections: [Trend, Margin, Regional Mix, Outliers]
  │  required_computations: [monthly_revenue, gross_margin_by_region,
  │                          top_products, outlier_drill]
  ▼
outline.py(profile + context)
  │  viability check: no col >15% null → all sections viable
  │  slides:
  │    1. Exec Summary  (3 takeaways + delta + CTA — populated in Stage 2)
  │    2. Q3 Revenue Trend (line)
  │    3. Gross Margin by Region (bar)
  │    4. Top 10 Products (native table — fits 10×5 rule)
  │    5. Regional Mix (stacked bar)
  │    6. Deep Dive: $1.2M Revenue Spike on Aug 14 (outlier-triggered)
  │    7. Recommendations
  ▼
LLM presents outline to user
  │
  ▼
USER GATE: confirm / edit / drop
```

### Stage 2 — Build

```
User confirms outline
  │
  ▼
For each slide:
  │
  ├─ analyze.py(df, computation_id)
  │     monthly_revenue → {jul_rev: 4.5M, aug_rev: 4.2M, sep_rev: 3.9M,
  │                         sep_mom_delta_pct: -7.0, q3_total: 12.6M}
  │
  ├─ aggregator.py(df_slice, chart_spec)
  │     → {labels: ["Jul","Aug","Sep"], values: [4.5,4.2,3.9],
  │        chart_type: "line"}
  │
  ├─ chart.py(chart_ready_json) OR tables.py(slice)
  │     line chart → seaborn → q3_trend.png (300 DPI, brand hex)
  │     OR native PPTX table for top-10
  │
  └─ narrative.py(analyze_kv)
        Observe:    "Revenue Aug = $4.2M, Sep = $3.9M"
        Analyze:    "Sep down 7% MoM; first decline since May"
        Synthesize: "Q3 momentum stalled in September —
                     investigate before Q4 commit"
        → hallucination check: "$3.9M" found in KV as 3,900,000 → match
        → speaker notes: all 3 statements
        → slide body: synthesis only (≤6 bullets)
  │
  ▼
build_pptx.py(outline + assets)
  │  Presentation('company_template.pptx')
  │  for slide in outline:
  │    layout = layouts.py.pick(content_type, slice_dims)
  │    add_slide(layout)
  │    fill image_placeholder ← chart PNG
  │    fill body_placeholder ← narrative bullets
  │    fill table_placeholder ← native table (if any)
  │    set speaker_notes ← Observe + Analyze + Synthesize
  │  if exclusions: append Exclusions slide
  ▼
output.pptx returned to user
```

### Invariants Enforced

- Every data slide has a chart OR table (Visual Priority).
- Every slide has ≤6 bullets (Slide Economy).
- Every insight slide has Observe/Analyze/Synthesize in speaker notes (audit).
- Slide 1 is always Exec Summary with ≥3 takeaways, ≥1 delta, 1 CTA.
- Outliers >20% always trigger a dedicated deep-dive slide.
- PII columns never appear in slide text or speaker notes.

---

## Section 4: Error Handling & Failure Modes

| Failure | Detection | Handling |
|---|---|---|
| File unreadable (corrupt PDF, password-protected, bad XLSX) | `ingest.py` try/except | Structured error JSON; LLM asks user for fixed file. |
| File too large (>500MB or >5M rows) | `ingest.py` size check | Polars lazy scan + sample first 100K rows; warn user "deck built on sample". |
| Schema unparseable (no headers, merged cells, freeform PDF) | `profile.py` detects all-null first row or zero columns | `{schema: null, reason: "no tabular structure"}`; LLM asks for sheet/region. |
| Ghost slide (required col >15% null) | `outline.py` viability check | Mark slide `excluded`; final deck adds Exclusions slide. |
| Aggregator empty (filter killed all rows) | `aggregator.py` non-empty check | Slide excluded, reason logged. |
| Chart render crash (matplotlib OOM, bad type) | `chart.py` try/except around `savefig` | Degrade to native table if slice qualifies; else exclude. |
| Native table overflow (>10 rows or >5 cols) | `layouts.py` rule | Auto-routes to image render. |
| Narrative hallucination (LLM invents numbers) | `narrative.py` regex post-check vs flat KV store, 0.01% tolerance | Regenerate once; second fail → strip claim, log warning. |
| Outlier deep-dive lacks comparison data | `analyze.py` neighbor check | Degrade to Big-Number callout (Observe only, no narrative chain). |
| Template missing or invalid | `build_pptx.py` template check | Fallback to `default_template.pptx`; warn in summary. |
| Layout name not in template | `layouts.py` Slide Master check | Fall back to closest match; warn in summary. |
| Sandbox timeout (analysis >60s per slide) | Per-script timeout wrapper | Skip slide, log; don't lose whole deck. |
| Empty result (file parses, no usable data) | Exclusions ≥ total slides | Single-slide deck: "Insufficient data for analysis" + raw schema dump. |
| PII detected | `profile.py` regex/Luhn | Excluded from all stages; final summary lists redactions. |

### Two design principles enforced everywhere

1. **Never silent fail.** Every skipped/degraded slide → reason in Exclusions slide at end of deck.
2. **Degrade, don't die.** A single bad slide never kills the deck. Worst case: empty deck with explanation.

---

## Section 5: Enterprise Wrapper

### A. PII Scrubbing (V1)

In `profile.py`:
- Column-name regex matches sensitive headers (SSN, credit card, passport, DOB, email, phone, etc.).
- Value-pattern checks: SSN regex, Luhn check on numeric columns (credit cards), email/phone regex sample.
- Columns flagged into `profile.pii_columns`.
- `outline.py` excludes any computation referencing PII columns.
- `narrative.py` cannot reference PII column names.
- Final Exclusions slide lists redactions: "Column 'Customer_SSN' excluded for privacy compliance."
- Speaker notes never contain PII either.

### B. Executive Summary Logic (V1)

Slide 1 always Exec Summary, must contain:
- **3 takeaways** — highest-impact synthesis statements selected from across the deck.
- **At least one comparative delta** — enforced by checking takeaways for delta keywords + numeric change. If absent, lowest-rank takeaway is replaced with a computed delta from `analyze.py` outputs.
- **Recommended Next Step (CTA)** — generated by feeding all synthesis statements to LLM with prompt: *"What is the single highest-priority action implied by these findings?"*
- Order: 3 takeaways → 1 delta → 1 next step.

### C. Multi-File Join Logic — DEFERRED to V2

V1 ships single-file analysis only (per Q7 decision: feature creep is silent killer; ship rock-solid single-file analyzer first).

V2 roadmap:
- Fuzzy join on common keys (Region, DeptID, CustomerID).
- Fact-vs-Dimension heuristic (XLSX = fact, CSV = dimension/target typically).
- Variance-to-Target computation type.
- Cross-source narrative weaving.

---

## Section 6: Testing Strategy

### Unit Tests (`tests/test_<module>.py`)

- `test_ingest.py` — fixtures: clean.xlsx, password.pdf, corrupt.pdf, empty.csv, freeform.pdf, 100K-row.csv. Assert correct DataFrame shape, parse_warnings, error JSON shape.
- `test_profile.py` — outlier flags fire at >20%, null_pct accuracy, PII regex catches SSN/email/CC, Luhn passes/fails correctly.
- `test_context.py` — story_type detection for time-series, margin, regional, survey fixtures.
- `test_outline.py` — viability check excludes when null >15%, Exec Summary always slide 1, deep-dive auto-inserted for outliers.
- `test_aggregator.py` — Chart-Ready JSON shape, never returns >100 data points.
- `test_chart.py` — render each chart type, PNG written, dimensions correct, brand hex applied.
- `test_tables.py` — slice ≤10×5 → native; slice >10×5 → routed to image.
- `test_narrative.py` — fabricated number caught; tolerance test (0.01% match passes); PII reference rejected.
- `test_layouts.py` — layout name mapping, fallback when template missing layout.
- `test_build_pptx.py` — golden file comparison via **Structure Crawler** (see below).

### Integration Tests (`tests/test_e2e_*.py`)

- `test_e2e_xlsx.py` — full pipeline on q3_sales.xlsx → deck has Exec Summary + Trend + Margin + Deep Dive + Exclusions; all slides have charts/tables; no PII leaked.
- `test_e2e_pdf.py` — annual report PDF → table extracted, narrative built, deck output.
- `test_e2e_csv.py` — survey CSV → distribution story.
- `test_e2e_messy.py` — high-null file → Exclusions slide present and correctly populated.
- `test_e2e_pii.py` — file with SSN/CC columns → no PII in any slide text or speaker notes (regex scan deck after build).

### Adversarial Tests (`tests/test_adversarial.py`)

- Empty file → graceful single-slide deck.
- All-null DataFrame → Exclusions-only deck.
- Single-row file → no statistical slides, just summary.
- 1M-row file → sampling triggers, warning surfaced.
- File with all PII columns → entire deck excluded, transparent message.

### Golden PPTX Fixtures via Structure Crawler

Instead of binary file diff (fragile — fails on metadata timestamps), the test:
1. Unzips `output.pptx` and `golden/expected.pptx` (PPTX = ZIP of XML files).
2. Walks `ppt/slides/` directory.
3. Asserts:
   - Expected number of `<p:sld>` slide nodes.
   - Presence of `<a:blip>` (image) tags in slides expected to have charts.
   - Presence of `<a:tbl>` (table) tags in slides expected to have native tables.
   - Layout references match expected Slide Master layout names.
   - Speaker notes (`notesSlide` parts) present where expected.
4. Ignores: timestamps, file modification metadata, exact pixel positions.

CI/CD-stable; brand template updates don't break tests.

### Coverage Targets

- 85% line coverage on `scripts/`.
- **100% on PII detection + viability check** — zero tolerance for false negatives.

---

## Appendix A: SKILL.md Draft

```markdown
# SKILL: Enterprise Data-to-Deck Architect

## Identity & Purpose
You are a world-class Data Analyst and Presentation Designer. Your goal is to transform raw files (PDF, XLSX, CSV) into board-ready .pptx presentations using a corporate template.

## Execution Pipeline

### PHASE 1: INTELLIGENT PROFILING
1. Use Polars to ingest and profile data via `scripts/ingest.py` + `scripts/profile.py`.
2. Identify keys: Time, Geography, Financials, Categories via `scripts/context.py`.
3. Detect Outliers: Any variance >20% from mean requires a "Deep Dive" slide.
4. Run Data Viability Check: any required column with >15% nulls excludes that slide.
5. Run PII Scrubbing: SSN, credit card (Luhn), email, phone, DOB, address columns excluded from all downstream stages.
6. Propose Outline via `scripts/outline.py`. Each slide includes a "Story Hook." Present to user for confirmation BEFORE building.

### PHASE 2: RIGOROUS ANALYSIS (Observe-Analyze-Synthesize)
For every insight generated by `scripts/narrative.py`:
- **Observe:** State the raw fact (e.g., "Revenue is $4.2M").
- **Analyze:** State the context (e.g., "This is a 7% decline MoM").
- **Synthesize:** State the 'So What' (e.g., "Q3 momentum is stalling; intervention required").

Hallucination guard: every numeric claim in narrative must match `analyze.py` flat KV store within 0.01% tolerance, else regenerate or strip.

### PHASE 3: PRODUCTION
1. Use `python-pptx` with `assets/company_template.pptx` (Slide Masters define brand).
2. Layout Rules:
   - Max 6 bullets per slide.
   - Use Brand Hex Codes for all Matplotlib/Seaborn charts.
   - Insert 'Synthesize' text into slide body; put 'Observe/Analyze' into Speaker Notes.
   - Native PPTX tables only when slice ≤10 rows AND ≤5 columns; else render as image.
   - Charts must reach `chart.py` only via `aggregator.py` (Chart-Ready JSON, ≤100 points).
3. Append Exclusions slide listing any skipped sections and reasons.

## Technical Constraints
- Use Polars for all data processing (speed & memory).
- Use PyMuPDF for PDF table extraction.
- Visual Priority: No "Text-Only" slides allowed for data sections.
- Failure Mode: If data quality is low (high nulls, schema unparseable), skip the slide and report in the final Exclusions slide.
- Privacy: PII columns must never appear in any slide text or speaker notes.

## Model Routing Guidance
- Opus 4.7: preferred for `narrative.py` and `outline.py` (instruction following).
- GPT-5: preferred when user requests custom layout code or complex stat extensions.
```

---

## Appendix B: Exclusions Slide Code Hook

```python
def generate_exclusions_slide(presentation, process_logs):
    """
    Appends a transparency slide detailing what was skipped and why.
    Args:
        presentation: pptx.Presentation instance (already built up).
        process_logs: list of dicts like
                      {'item': 'Revenue Drilldown',
                       'status': 'skipped',
                       'reason': 'Cost column 40% null'}
    """
    if not any(log['status'] == 'skipped' for log in process_logs):
        return  # Skip if the run was perfect

    # Layout index 6 assumed = "Title and Content" or appendix layout in template.
    # In production, look up by layout name via layouts.py.
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    title = slide.shapes.title
    title.text = "Data Integrity & Exclusions Report"

    body = slide.placeholders[1].text_frame
    body.text = "The following sections were excluded or modified to ensure accuracy and compliance:"

    for log in process_logs:
        if log['status'] == 'skipped':
            p = body.add_paragraph()
            p.text = f"• {log['item']}: {log['reason']}"
            p.level = 1
```

---

## V2 Roadmap

- **Multi-file synthesis:** fuzzy join on common keys; Fact-vs-Dimension heuristic; variance-to-target slides; cross-source narrative.
- **Iterative refinement mode:** multi-turn user steering of individual slides post-build.
- **Custom theme override:** runtime YAML config for color/font overrides without template swap.
- **Time-budget mode:** user specifies "fast" (≤15 sec) or "thorough" (≤2 min) and skill adjusts depth.
- **Chart-type override:** user can request specific chart types per slide in outline confirmation step.

---

## Decisions Log

| # | Decision | Choice | Reason |
|---|---|---|---|
| Q1 | Skill format | SKILL.md (Anthropic style) | Internal AI platform supports this. |
| Q2 | Runtime | Code execution sandbox | Required for Polars/PyMuPDF/python-pptx. |
| Q3 | Output format | PPTX | Enterprise standard; users edit and embed. |
| Q4 | Analysis depth | Descriptive + Visual + Narrative | Sweet spot for executive value. |
| Q5 | Workflow | Two-stage (profile → confirm → build) | Avoids 20-slide deck that misses the point. |
| Q6 | Branding | Corporate template (Slide Masters), default fallback | Cleanest brand enforcement. |
| Q7 | Input scope | Single file V1, multi-file V2 | Feature creep is silent killer. Ship rock-solid V1. |
| Approach | Architecture | Standalone monolithic skill | Portable, single dep surface, full theme control. |
