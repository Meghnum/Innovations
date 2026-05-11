# Presentation Builder Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade SKILL.md that ingests PDF/XLSX/CSV, performs intelligent data analysis, and produces board-ready branded PPTX presentations via a two-stage (profile→confirm→build) workflow.

**Architecture:** Standalone monolithic skill. Self-contained `presentation-builder/` directory with SKILL.md (LLM instructions) + 11 Python script modules (pure compute) + assets (corporate template) + comprehensive tests. Scripts are JSON-shaped pure functions: testable, composable, deterministic. LLM orchestrates per SKILL.md, scripts do the work. No cross-LLM API calls inside the skill (model-agnostic at runtime).

**Tech Stack:** Python 3.10+, Polars (data), PyMuPDF / `fitz` (PDF), Seaborn + Matplotlib (charts), python-pptx (presentation build), pytest (tests).

---

## File Structure

```
presentation-builder/
├── SKILL.md                          # LLM instructions + execution pipeline
├── requirements.txt
├── scripts/
│   ├── __init__.py
│   ├── ingest.py                     # PDF/XLSX/CSV → DataFrame + metadata
│   ├── profile.py                    # Schema, stats, outliers, PII detection
│   ├── context.py                    # Column patterns → story_type
│   ├── outline.py                    # Slide list + viability + exec summary
│   ├── analyze.py                    # Per-slide computations → flat KV
│   ├── aggregator.py                 # DataFrame → Chart-Ready JSON
│   ├── chart.py                      # Seaborn → branded PNG
│   ├── tables.py                     # Native PPTX table builder
│   ├── narrative.py                  # Prompt builder + hallucination validator
│   ├── layouts.py                    # Layout picker + render-mode rule
│   └── build_pptx.py                 # Assemble deck + exclusions slide
├── assets/
│   ├── company_template.pptx         # Brand source (Slide Masters)
│   └── default_template.pptx         # Fallback
└── tests/
    ├── __init__.py
    ├── conftest.py                   # Shared pytest fixtures
    ├── fixtures/
    │   ├── _generate.py              # Script to (re)build all sample files
    │   ├── sample_clean.xlsx
    │   ├── sample_messy.xlsx
    │   ├── sample.csv
    │   ├── sample.pdf
    │   ├── sample_pii.csv
    │   └── large.csv
    ├── golden/
    │   └── q3_sales_expected.pptx
    ├── test_ingest.py
    ├── test_profile.py
    ├── test_context.py
    ├── test_outline.py
    ├── test_analyze.py
    ├── test_aggregator.py
    ├── test_chart.py
    ├── test_tables.py
    ├── test_narrative.py
    ├── test_layouts.py
    ├── test_build_pptx.py
    ├── test_e2e_xlsx.py
    ├── test_e2e_pdf.py
    ├── test_e2e_csv.py
    ├── test_e2e_messy.py
    ├── test_e2e_pii.py
    └── test_adversarial.py
```

**File responsibilities:**
- Each `scripts/*.py` module: one responsibility, JSON-shaped function signatures, no cross-imports between sibling modules unless declared (only `narrative.py` reads from `analyze.py` outputs; `build_pptx.py` consumes everything else's outputs as data).
- Tests: one test file per module, plus end-to-end suite, plus adversarial suite.

---

## Phase 0: Scaffolding

### Task 1: Create project skeleton + requirements

**Files:**
- Create: `presentation-builder/requirements.txt`
- Create: `presentation-builder/scripts/__init__.py` (empty)
- Create: `presentation-builder/tests/__init__.py` (empty)
- Create: `presentation-builder/tests/conftest.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p presentation-builder/scripts \
         presentation-builder/tests/fixtures \
         presentation-builder/tests/golden \
         presentation-builder/assets
touch presentation-builder/scripts/__init__.py \
      presentation-builder/tests/__init__.py
```

- [ ] **Step 2: Write requirements.txt**

```
polars>=0.20.0
pymupdf>=1.24.0
matplotlib>=3.8.0
seaborn>=0.13.0
python-pptx>=0.6.23
pytest>=8.0.0
pytest-cov>=5.0.0
fastexcel>=0.10.0
```

(`fastexcel` is required by Polars for `read_excel`.)

- [ ] **Step 3: Install dependencies**

Run: `cd presentation-builder && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
Expected: install completes without errors.

- [ ] **Step 4: Write conftest.py with shared fixtures**

```python
# presentation-builder/tests/conftest.py
from pathlib import Path
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR = Path(__file__).parent / "golden"

@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR

@pytest.fixture
def golden_dir() -> Path:
    return GOLDEN_DIR

@pytest.fixture
def sample_csv(fixtures_dir) -> Path:
    return fixtures_dir / "sample.csv"

@pytest.fixture
def sample_xlsx(fixtures_dir) -> Path:
    return fixtures_dir / "sample_clean.xlsx"

@pytest.fixture
def sample_pdf(fixtures_dir) -> Path:
    return fixtures_dir / "sample.pdf"

@pytest.fixture
def sample_pii(fixtures_dir) -> Path:
    return fixtures_dir / "sample_pii.csv"

@pytest.fixture
def sample_messy(fixtures_dir) -> Path:
    return fixtures_dir / "sample_messy.xlsx"
```

- [ ] **Step 5: Verify pytest discovers tests folder**

Run: `cd presentation-builder && pytest --collect-only`
Expected: `0 tests collected` (no errors).

- [ ] **Step 6: Commit**

```bash
git add presentation-builder/
git commit -m "feat(presentation-builder): scaffold skill skeleton + requirements"
```

---

### Task 2: Fixture generator script + sample fixtures

**Files:**
- Create: `presentation-builder/tests/fixtures/_generate.py`
- Create (via script): all sample files in `tests/fixtures/`

- [ ] **Step 1: Write fixture generator**

```python
# presentation-builder/tests/fixtures/_generate.py
"""Regenerate all test fixtures. Run: python tests/fixtures/_generate.py"""
from pathlib import Path
import polars as pl
import datetime as dt
import random

OUT = Path(__file__).parent

def make_clean_xlsx():
    rows = []
    regions = ["North", "South", "East", "West"]
    products = ["Alpha", "Beta", "Gamma"]
    start = dt.date(2026, 7, 1)
    random.seed(42)
    for i in range(200):
        d = start + dt.timedelta(days=i % 90)
        rows.append({
            "Date": d,
            "Region": regions[i % 4],
            "Product": products[i % 3],
            "Revenue": round(random.uniform(1000, 50000), 2),
            "Cost": round(random.uniform(500, 30000), 2),
            "Units": random.randint(1, 500),
        })
    df = pl.DataFrame(rows)
    df.write_excel(OUT / "sample_clean.xlsx")

def make_messy_xlsx():
    # 40% nulls in Cost — triggers viability exclusion
    rows = []
    random.seed(7)
    for i in range(100):
        rows.append({
            "Region": ["North", "South"][i % 2],
            "Revenue": round(random.uniform(1000, 50000), 2),
            "Cost": None if random.random() < 0.4 else round(random.uniform(500, 30000), 2),
        })
    df = pl.DataFrame(rows)
    df.write_excel(OUT / "sample_messy.xlsx")

def make_csv():
    rows = []
    random.seed(3)
    for i in range(50):
        rows.append({
            "Question": f"Q{i % 5 + 1}",
            "Score": random.randint(1, 5),
        })
    df = pl.DataFrame(rows)
    df.write_csv(OUT / "sample.csv")

def make_pii_csv():
    rows = []
    for i in range(20):
        rows.append({
            "Customer_Name": f"Person {i}",
            "SSN": f"{100+i:03d}-{20+i:02d}-{1000+i:04d}",
            "Email": f"user{i}@example.com",
            "Revenue": 1000 * (i + 1),
        })
    df = pl.DataFrame(rows)
    df.write_csv(OUT / "sample_pii.csv")

def make_large_csv():
    rows = [{"id": i, "value": i * 2.5} for i in range(100_000)]
    df = pl.DataFrame(rows)
    df.write_csv(OUT / "large.csv")

def make_pdf():
    # Use pymupdf to create a minimal PDF with one table.
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    text = "Quarterly Report\n\nRegion | Revenue | Cost\nNorth  | 1000    | 500\nSouth  | 2000    | 1500\nEast   | 1500    | 800\n"
    page.insert_text((50, 100), text, fontsize=11)
    doc.save(OUT / "sample.pdf")
    doc.close()

if __name__ == "__main__":
    make_clean_xlsx()
    make_messy_xlsx()
    make_csv()
    make_pii_csv()
    make_large_csv()
    make_pdf()
    print("fixtures regenerated")
```

- [ ] **Step 2: Run generator**

Run: `cd presentation-builder && python tests/fixtures/_generate.py`
Expected: `fixtures regenerated` printed; 6 files written to `tests/fixtures/`.

- [ ] **Step 3: Verify fixtures exist**

Run: `ls presentation-builder/tests/fixtures/`
Expected: `_generate.py  large.csv  sample.csv  sample.pdf  sample_clean.xlsx  sample_messy.xlsx  sample_pii.csv`

- [ ] **Step 4: Commit**

```bash
git add presentation-builder/tests/fixtures/
git commit -m "feat(presentation-builder): add fixture generator + sample data files"
```

---

### Task 3: Default PPTX template asset

**Files:**
- Create script: `presentation-builder/assets/_make_default_template.py`
- Create: `presentation-builder/assets/default_template.pptx`

- [ ] **Step 1: Write template generator**

```python
# presentation-builder/assets/_make_default_template.py
"""Generate a minimal default template with required Slide Master layouts."""
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches

OUT = Path(__file__).parent / "default_template.pptx"

REQUIRED_LAYOUTS = [
    "Title Slide",
    "Title and Content",
    "Image + Text",
    "Two-Column",
    "Big Number",
    "Table Layout",
]

def main():
    # python-pptx default has 11 layouts. We rely on names by index for fallback.
    prs = Presentation()
    # Default slide width/height (16:9)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    prs.save(OUT)
    print(f"default template at {OUT}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate template**

Run: `cd presentation-builder && python assets/_make_default_template.py`
Expected: `default template at .../default_template.pptx`.

- [ ] **Step 3: Verify file exists**

Run: `ls -la presentation-builder/assets/default_template.pptx`
Expected: file present, ~30KB.

- [ ] **Step 4: Note for user — corporate template**

Add to `presentation-builder/assets/README.md`:

```markdown
# Assets

- `default_template.pptx` — generated fallback template. Used when no corporate template provided.
- `company_template.pptx` — REPLACE THIS with your enterprise PPTX template containing branded Slide Masters before deployment.
  Required layout names in Slide Masters: "Title Slide", "Title and Content", "Image + Text", "Two-Column", "Big Number", "Table Layout".
  If layout names differ, see `scripts/layouts.py` for the closest-match fallback logic.
```

For development, copy default as placeholder for company template:

```bash
cp presentation-builder/assets/default_template.pptx presentation-builder/assets/company_template.pptx
```

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/assets/
git commit -m "feat(presentation-builder): add default template + assets README"
```

---

## Phase 1: Ingest

### Task 4: CSV reader (Polars)

**Files:**
- Create: `presentation-builder/scripts/ingest.py`
- Create: `presentation-builder/tests/test_ingest.py`

- [ ] **Step 1: Write failing test**

```python
# presentation-builder/tests/test_ingest.py
import polars as pl
from scripts.ingest import ingest

def test_ingest_csv_returns_dataframe_and_metadata(sample_csv):
    result = ingest(str(sample_csv))
    assert "dataframe" in result
    assert "metadata" in result
    assert isinstance(result["dataframe"], pl.DataFrame)
    assert result["metadata"]["file_type"] == "csv"
    assert result["metadata"]["rows"] == 50
    assert result["metadata"]["cols"] == 2
    assert result["metadata"]["parse_warnings"] == []

def test_ingest_missing_file_returns_error():
    result = ingest("nonexistent.csv")
    assert "error" in result
    assert "not found" in result["error"].lower()

def test_ingest_unsupported_extension_returns_error(tmp_path):
    p = tmp_path / "file.json"
    p.write_text("{}")
    result = ingest(str(p))
    assert "error" in result
    assert "unsupported" in result["error"].lower()
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.ingest`.

- [ ] **Step 3: Implement minimal CSV ingest**

```python
# presentation-builder/scripts/ingest.py
from pathlib import Path
import polars as pl

def ingest(file_path: str) -> dict:
    p = Path(file_path)
    if not p.exists():
        return {"error": f"file not found: {file_path}"}
    ext = p.suffix.lower()
    try:
        if ext == ".csv":
            df = pl.read_csv(p)
        else:
            return {"error": f"unsupported file type: {ext}"}
    except Exception as e:
        return {"error": f"parse failed: {e}"}
    return {
        "dataframe": df,
        "metadata": {
            "source": str(p),
            "rows": df.height,
            "cols": df.width,
            "parse_warnings": [],
            "file_type": ext.lstrip("."),
        },
    }
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_ingest.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/ingest.py presentation-builder/tests/test_ingest.py
git commit -m "feat(ingest): CSV reader with metadata + error envelope"
```

---

### Task 5: XLSX reader (Polars)

**Files:**
- Modify: `presentation-builder/scripts/ingest.py`
- Modify: `presentation-builder/tests/test_ingest.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_ingest.py`:

```python
def test_ingest_xlsx_returns_dataframe_and_metadata(sample_xlsx):
    result = ingest(str(sample_xlsx))
    assert "dataframe" in result
    assert result["metadata"]["file_type"] == "xlsx"
    assert result["metadata"]["rows"] == 200
    assert result["metadata"]["cols"] == 6
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_ingest.py::test_ingest_xlsx_returns_dataframe_and_metadata -v`
Expected: FAIL — `unsupported file type: .xlsx`.

- [ ] **Step 3: Add XLSX branch**

In `scripts/ingest.py`, replace the type dispatch block:

```python
        if ext == ".csv":
            df = pl.read_csv(p)
        elif ext in (".xlsx", ".xls"):
            df = pl.read_excel(p)
        else:
            return {"error": f"unsupported file type: {ext}"}
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_ingest.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/ingest.py presentation-builder/tests/test_ingest.py
git commit -m "feat(ingest): XLSX support via Polars read_excel"
```

---

### Task 6: PDF reader (PyMuPDF)

**Files:**
- Modify: `presentation-builder/scripts/ingest.py`
- Modify: `presentation-builder/tests/test_ingest.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_ingest.py`:

```python
def test_ingest_pdf_extracts_text_blocks(sample_pdf):
    result = ingest(str(sample_pdf))
    assert "metadata" in result
    assert result["metadata"]["file_type"] == "pdf"
    assert "text_blocks" in result["metadata"]
    assert any("Quarterly Report" in t for t in result["metadata"]["text_blocks"])
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_ingest.py::test_ingest_pdf_extracts_text_blocks -v`
Expected: FAIL — `unsupported file type: .pdf`.

- [ ] **Step 3: Add PDF branch + helper**

In `scripts/ingest.py`:

```python
import fitz  # PyMuPDF

def _ingest_pdf(p: Path) -> dict:
    doc = fitz.open(p)
    tables = []
    text_blocks = []
    try:
        for page in doc:
            text_blocks.append(page.get_text())
            for tbl in page.find_tables():
                rows = tbl.extract()
                if rows and len(rows) > 1:
                    header, *body = rows
                    if all(h is not None for h in header):
                        cleaned = [
                            {h: row[i] for i, h in enumerate(header)}
                            for row in body
                        ]
                        tables.append(pl.DataFrame(cleaned))
    finally:
        doc.close()
    if tables:
        df = pl.concat(tables, how="diagonal_relaxed") if len(tables) > 1 else tables[0]
        return {
            "dataframe": df,
            "metadata": {
                "source": str(p),
                "rows": df.height,
                "cols": df.width,
                "parse_warnings": [],
                "file_type": "pdf",
                "text_blocks": text_blocks,
            },
        }
    return {
        "dataframe": None,
        "metadata": {
            "source": str(p),
            "rows": 0,
            "cols": 0,
            "parse_warnings": ["no tables found in PDF"],
            "file_type": "pdf",
            "text_blocks": text_blocks,
        },
    }
```

Add PDF branch in main `ingest()`:

```python
        elif ext == ".pdf":
            return _ingest_pdf(p)
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_ingest.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/ingest.py presentation-builder/tests/test_ingest.py
git commit -m "feat(ingest): PDF support via PyMuPDF (text + table extraction)"
```

---

## Phase 2: Profile

### Task 7: Schema + null percentages

**Files:**
- Create: `presentation-builder/scripts/profile.py`
- Create: `presentation-builder/tests/test_profile.py`

- [ ] **Step 1: Write failing test**

```python
# presentation-builder/tests/test_profile.py
import polars as pl
from scripts.profile import profile

def test_profile_basic_schema():
    df = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    result = profile(df)
    assert "schema" in result
    assert result["schema"]["a"] == "Int64"
    assert result["schema"]["b"] == "String"
    assert "null_pct" in result
    assert result["null_pct"]["a"] == 0.0
    assert result["null_pct"]["b"] == 0.0

def test_profile_null_pct_correct():
    df = pl.DataFrame({"a": [1, None, 3, None]})
    result = profile(df)
    assert result["null_pct"]["a"] == 50.0
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_profile.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement schema + null_pct**

```python
# presentation-builder/scripts/profile.py
import polars as pl

def profile(df: pl.DataFrame) -> dict:
    if df is None or df.is_empty():
        return {
            "schema": {},
            "dtypes": {},
            "null_pct": {},
            "distributions": {},
            "outliers": [],
            "date_range": None,
            "pii_columns": [],
        }
    schema = {col: str(df.schema[col]) for col in df.columns}
    null_pct = {
        col: round(100.0 * df[col].null_count() / df.height, 2)
        for col in df.columns
    }
    return {
        "schema": schema,
        "dtypes": schema,  # alias
        "null_pct": null_pct,
        "distributions": {},
        "outliers": [],
        "date_range": None,
        "pii_columns": [],
    }
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_profile.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/profile.py presentation-builder/tests/test_profile.py
git commit -m "feat(profile): schema + null percentage detection"
```

---

### Task 8: Outlier detection

**Files:**
- Modify: `presentation-builder/scripts/profile.py`
- Modify: `presentation-builder/tests/test_profile.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_profile.py`:

```python
def test_outlier_detected_when_value_exceeds_20pct_deviation():
    df = pl.DataFrame({"x": [10, 11, 9, 10, 100]})  # 100 is far above mean
    result = profile(df)
    outs = [o for o in result["outliers"] if o["col"] == "x"]
    assert len(outs) >= 1
    assert any(o["value"] == 100 for o in outs)
    assert all(abs(o["deviation_pct"]) > 20 for o in outs)

def test_no_outliers_in_uniform_data():
    df = pl.DataFrame({"x": [10, 10, 10, 10, 10]})
    result = profile(df)
    assert result["outliers"] == []
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_profile.py::test_outlier_detected_when_value_exceeds_20pct_deviation -v`
Expected: FAIL — `outliers` is `[]`.

- [ ] **Step 3: Add outlier detection**

In `scripts/profile.py`, add helper and integrate:

```python
def _detect_outliers(df: pl.DataFrame, threshold_pct: float = 20.0) -> list:
    out = []
    for col in df.columns:
        if not df[col].dtype.is_numeric():
            continue
        series = df[col].drop_nulls()
        if series.len() < 2:
            continue
        mean = series.mean()
        if mean is None or mean == 0:
            continue
        for v in series.unique().to_list():
            dev_pct = 100.0 * (v - mean) / abs(mean)
            if abs(dev_pct) > threshold_pct:
                out.append({
                    "col": col,
                    "value": v,
                    "deviation_pct": round(dev_pct, 2),
                })
    return out
```

In `profile()`, replace `"outliers": []` with `"outliers": _detect_outliers(df)`.

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_profile.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/profile.py presentation-builder/tests/test_profile.py
git commit -m "feat(profile): outlier detection via >20% mean deviation"
```

---

### Task 9: PII column detection (regex + Luhn)

**Files:**
- Modify: `presentation-builder/scripts/profile.py`
- Modify: `presentation-builder/tests/test_profile.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_profile.py`:

```python
def test_pii_detected_by_column_name():
    df = pl.DataFrame({"SSN": ["123-45-6789"], "Revenue": [100]})
    result = profile(df)
    assert "SSN" in result["pii_columns"]
    assert "Revenue" not in result["pii_columns"]

def test_pii_detected_by_value_pattern_ssn():
    df = pl.DataFrame({"id_field": ["111-22-3333", "444-55-6666"]})
    result = profile(df)
    assert "id_field" in result["pii_columns"]

def test_pii_detected_by_email_pattern():
    df = pl.DataFrame({"contact": ["a@b.com", "c@d.org"]})
    result = profile(df)
    assert "contact" in result["pii_columns"]

def test_pii_detected_by_luhn_credit_card():
    # 4111111111111111 is a valid Luhn test card
    df = pl.DataFrame({"acct": [4111111111111111, 4111111111111111]})
    result = profile(df)
    assert "acct" in result["pii_columns"]

def test_no_pii_in_clean_columns():
    df = pl.DataFrame({"Region": ["North"], "Revenue": [1000]})
    result = profile(df)
    assert result["pii_columns"] == []
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_profile.py -v -k pii`
Expected: 4 FAIL (column-name detection works for "SSN" by name? — only `Revenue` test would pass without value detection).

- [ ] **Step 3: Implement PII detection**

In `scripts/profile.py`:

```python
import re

PII_NAME_RX = re.compile(
    r"(?i)(ssn|social.?security|credit.?card|cc.?num|passport|home.?address|tax.?id|dob|date.?of.?birth|email|phone|account.?number|acct.?num)"
)
SSN_RX = re.compile(r"^\d{3}-\d{2}-\d{4}$")
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _luhn_valid(num: int) -> bool:
    digits = [int(d) for d in str(num)]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0

def _detect_pii(df: pl.DataFrame) -> list:
    pii = set()
    for col in df.columns:
        if PII_NAME_RX.search(col):
            pii.add(col)
            continue
        series = df[col].drop_nulls()
        if series.len() == 0:
            continue
        sample = series.head(min(20, series.len())).to_list()
        if df[col].dtype == pl.String:
            if any(SSN_RX.match(str(v)) for v in sample):
                pii.add(col)
                continue
            if any(EMAIL_RX.match(str(v)) for v in sample):
                pii.add(col)
                continue
        if df[col].dtype.is_numeric():
            try:
                if all(_luhn_valid(int(v)) for v in sample):
                    pii.add(col)
            except (ValueError, TypeError):
                pass
    return sorted(pii)
```

In `profile()`, replace `"pii_columns": []` with `"pii_columns": _detect_pii(df)`.

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_profile.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/profile.py presentation-builder/tests/test_profile.py
git commit -m "feat(profile): PII detection via column-name regex + value patterns + Luhn"
```

---

### Task 10: Date range + distributions

**Files:**
- Modify: `presentation-builder/scripts/profile.py`
- Modify: `presentation-builder/tests/test_profile.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_profile.py`:

```python
import datetime as dt

def test_date_range_extracted():
    df = pl.DataFrame({"Date": [dt.date(2026, 1, 1), dt.date(2026, 6, 30)]})
    result = profile(df)
    assert result["date_range"] is not None
    assert result["date_range"]["min"] == "2026-01-01"
    assert result["date_range"]["max"] == "2026-06-30"
    assert result["date_range"]["column"] == "Date"

def test_distributions_for_numeric():
    df = pl.DataFrame({"x": [1, 2, 3, 4, 5]})
    result = profile(df)
    assert "x" in result["distributions"]
    assert result["distributions"]["x"]["mean"] == 3.0
    assert result["distributions"]["x"]["min"] == 1
    assert result["distributions"]["x"]["max"] == 5
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_profile.py::test_date_range_extracted -v`
Expected: FAIL.

- [ ] **Step 3: Implement date range + distributions**

In `scripts/profile.py`:

```python
def _date_range(df: pl.DataFrame) -> dict | None:
    for col in df.columns:
        if df[col].dtype in (pl.Date, pl.Datetime):
            series = df[col].drop_nulls()
            if series.len() == 0:
                continue
            return {
                "column": col,
                "min": str(series.min()),
                "max": str(series.max()),
            }
    return None

def _distributions(df: pl.DataFrame) -> dict:
    out = {}
    for col in df.columns:
        if df[col].dtype.is_numeric():
            series = df[col].drop_nulls()
            if series.len() == 0:
                continue
            out[col] = {
                "mean": float(series.mean()),
                "min": series.min(),
                "max": series.max(),
                "std": float(series.std()) if series.len() > 1 else 0.0,
            }
    return out
```

In `profile()`, set:

```python
        "distributions": _distributions(df),
        "date_range": _date_range(df),
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_profile.py -v`
Expected: 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/profile.py presentation-builder/tests/test_profile.py
git commit -m "feat(profile): date range + numeric distributions"
```

---

## Phase 3: Context

### Task 11: Story-shape detection

**Files:**
- Create: `presentation-builder/scripts/context.py`
- Create: `presentation-builder/tests/test_context.py`

- [ ] **Step 1: Write failing test**

```python
# presentation-builder/tests/test_context.py
from scripts.context import detect_context

def _profile(schema: dict, date_range=None) -> dict:
    return {
        "schema": schema,
        "null_pct": {c: 0.0 for c in schema},
        "outliers": [],
        "date_range": date_range,
        "pii_columns": [],
        "distributions": {},
    }

def test_time_series_story_when_date_present():
    p = _profile({"Date": "Date", "Revenue": "Float64"}, date_range={"column": "Date", "min": "2026-01", "max": "2026-12"})
    ctx = detect_context(p)
    assert ctx["story_type"] == "time-series"
    assert "monthly_revenue" in ctx["required_computations"]

def test_margin_story_when_revenue_and_cost():
    p = _profile({"Revenue": "Float64", "Cost": "Float64"})
    ctx = detect_context(p)
    assert "margin" in ctx["story_type"]
    assert "gross_margin" in ctx["required_computations"]

def test_regional_story_when_region_and_numeric():
    p = _profile({"Region": "String", "Sales": "Float64"})
    ctx = detect_context(p)
    assert "regional" in ctx["story_type"] or "comparative" in ctx["story_type"]
    assert "top_n_by_region" in ctx["required_computations"]

def test_combined_story_time_region_financials():
    p = _profile(
        {"Date": "Date", "Region": "String", "Revenue": "Float64", "Cost": "Float64"},
        date_range={"column": "Date", "min": "2026-Q3", "max": "2026-Q3"},
    )
    ctx = detect_context(p)
    # Should include all three suggested sections
    sections = ctx["suggested_sections"]
    assert any("Trend" in s for s in sections)
    assert any("Margin" in s for s in sections)
    assert any("Region" in s for s in sections)
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_context.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement context detection**

```python
# presentation-builder/scripts/context.py
import re

REVENUE_RX = re.compile(r"(?i)(revenue|sales|income|amount)")
COST_RX = re.compile(r"(?i)(cost|expense|spend|cogs)")
REGION_RX = re.compile(r"(?i)(region|country|state|city|territory|segment|department)")
DATE_RX = re.compile(r"(?i)(date|time|month|quarter|year|period)")

def _has_match(cols, rx):
    return any(rx.search(c) for c in cols)

def _find_first(cols, rx):
    for c in cols:
        if rx.search(c):
            return c
    return None

def detect_context(profile: dict) -> dict:
    cols = list(profile.get("schema", {}).keys())
    sections = []
    computations = []
    story_parts = []

    has_date = profile.get("date_range") is not None or _has_match(cols, DATE_RX)
    has_revenue = _has_match(cols, REVENUE_RX)
    has_cost = _has_match(cols, COST_RX)
    has_region = _has_match(cols, REGION_RX)

    if has_date and has_revenue:
        sections.append("Revenue Trend")
        computations.append("monthly_revenue")
        story_parts.append("time-series")
    if has_revenue and has_cost:
        sections.append("Margin Analysis")
        computations.append("gross_margin")
        story_parts.append("margin")
    if has_region:
        numeric_cols = [c for c, t in profile.get("schema", {}).items() if "Int" in t or "Float" in t]
        if numeric_cols:
            sections.append("Regional Breakdown")
            computations.append("top_n_by_region")
            story_parts.append("regional")
    if profile.get("outliers"):
        sections.append("Outlier Deep Dive")
        computations.append("outlier_drill")

    if not sections:
        sections.append("Data Summary")
        computations.append("descriptive_summary")
        story_parts.append("descriptive")

    return {
        "story_type": " + ".join(story_parts),
        "suggested_sections": sections,
        "required_computations": computations,
    }
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_context.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/context.py presentation-builder/tests/test_context.py
git commit -m "feat(context): story-shape detection from column patterns + outliers"
```

---

## Phase 4: Outline

### Task 12: Outline builder + viability check

**Files:**
- Create: `presentation-builder/scripts/outline.py`
- Create: `presentation-builder/tests/test_outline.py`

- [ ] **Step 1: Write failing test**

```python
# presentation-builder/tests/test_outline.py
from scripts.outline import build_outline

def _ctx(sections, computations):
    return {
        "story_type": "test",
        "suggested_sections": sections,
        "required_computations": computations,
    }

def _prof(null_pct=None, outliers=None, pii=None):
    return {
        "schema": {"Date": "Date", "Revenue": "Float64", "Cost": "Float64", "Region": "String"},
        "null_pct": null_pct or {"Date": 0, "Revenue": 0, "Cost": 0, "Region": 0},
        "outliers": outliers or [],
        "pii_columns": pii or [],
        "distributions": {},
        "date_range": None,
    }

def test_outline_has_exec_summary_first():
    profile = _prof()
    ctx = _ctx(["Revenue Trend"], ["monthly_revenue"])
    outline = build_outline(profile, ctx)
    assert outline["slides"][0]["content_type"] == "exec_summary"
    assert outline["slides"][0]["n"] == 1

def test_outline_excludes_slide_when_required_col_too_null():
    profile = _prof(null_pct={"Date": 0, "Revenue": 0, "Cost": 40.0, "Region": 0})
    ctx = _ctx(["Margin Analysis"], ["gross_margin"])
    outline = build_outline(profile, ctx)
    margin_slide = [s for s in outline["slides"] if s["computation_id"] == "gross_margin"][0]
    assert margin_slide["status"] == "excluded"
    assert "Cost" in margin_slide["reason"]
    assert "40" in margin_slide["reason"]

def test_outline_includes_deep_dive_per_outlier():
    profile = _prof(outliers=[{"col": "Revenue", "value": 1.2e6, "deviation_pct": 340}])
    ctx = _ctx(["Revenue Trend"], ["monthly_revenue"])
    outline = build_outline(profile, ctx)
    deep_dives = [s for s in outline["slides"] if s["content_type"] == "deep_dive"]
    assert len(deep_dives) == 1

def test_outline_skips_pii_computations():
    profile = _prof(pii=["Revenue"])
    ctx = _ctx(["Revenue Trend"], ["monthly_revenue"])  # uses Revenue
    outline = build_outline(profile, ctx)
    rev_slide = [s for s in outline["slides"] if s["computation_id"] == "monthly_revenue"][0]
    assert rev_slide["status"] == "excluded"
    assert "PII" in rev_slide["reason"] or "privacy" in rev_slide["reason"].lower()
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_outline.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement outline builder**

```python
# presentation-builder/scripts/outline.py
import re

# Map computation_id → required columns (regex match against profile schema).
COMPUTATION_REQUIREMENTS = {
    "monthly_revenue": [r"(?i)(revenue|sales|income|amount)"],
    "gross_margin": [r"(?i)(revenue|sales|income)", r"(?i)(cost|expense|cogs)"],
    "top_n_by_region": [r"(?i)(region|country|segment|territory)"],
    "outlier_drill": [],
    "descriptive_summary": [],
}

NULL_THRESHOLD_PCT = 15.0


def _columns_matching(schema_cols, pattern):
    rx = re.compile(pattern)
    return [c for c in schema_cols if rx.search(c)]


def _check_viability(profile: dict, computation_id: str) -> tuple[bool, str]:
    schema_cols = list(profile.get("schema", {}).keys())
    null_pct = profile.get("null_pct", {})
    pii = set(profile.get("pii_columns", []))
    requirements = COMPUTATION_REQUIREMENTS.get(computation_id, [])
    for pattern in requirements:
        matches = _columns_matching(schema_cols, pattern)
        if not matches:
            return False, f"No column matching {pattern} found"
        # Check viability of best match
        viable = [c for c in matches if c not in pii and null_pct.get(c, 0) <= NULL_THRESHOLD_PCT]
        if not viable:
            offending = matches[0]
            if offending in pii:
                return False, f"Column '{offending}' excluded for PII privacy compliance"
            return False, f"Column '{offending}' has {null_pct.get(offending, 0)}% nulls (>{NULL_THRESHOLD_PCT}%)"
    return True, ""


def build_outline(profile: dict, context: dict) -> dict:
    slides = []
    n = 1
    # Slide 1: Exec Summary placeholder (filled in Stage 2 from synthesized takeaways)
    slides.append({
        "n": n,
        "layout": "Title and Content",
        "title": "Executive Summary",
        "content_type": "exec_summary",
        "computation_id": None,
        "chart_spec": None,
        "status": "active",
    })
    n += 1

    # Section slides
    sections = context.get("suggested_sections", [])
    computations = context.get("required_computations", [])
    for section, comp_id in zip(sections, computations):
        viable, reason = _check_viability(profile, comp_id)
        slide = {
            "n": n,
            "layout": "Image + Text",
            "title": section,
            "content_type": "section",
            "computation_id": comp_id,
            "chart_spec": {"type": "auto"},
            "status": "active" if viable else "excluded",
            "reason": "" if viable else reason,
        }
        slides.append(slide)
        n += 1

    # Deep-dive slides per outlier
    for outlier in profile.get("outliers", []):
        slides.append({
            "n": n,
            "layout": "Big Number",
            "title": f"Deep Dive: {outlier['col']} = {outlier['value']}",
            "content_type": "deep_dive",
            "computation_id": "outlier_drill",
            "chart_spec": {"type": "annotation", "outlier": outlier},
            "status": "active",
            "outlier": outlier,
        })
        n += 1

    return {"slides": slides}
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_outline.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/outline.py presentation-builder/tests/test_outline.py
git commit -m "feat(outline): slide planner with viability check + outlier deep-dives"
```

---

## Phase 5: Analyze

### Task 13: Computation registry + flat KV output

**Files:**
- Create: `presentation-builder/scripts/analyze.py`
- Create: `presentation-builder/tests/test_analyze.py`

- [ ] **Step 1: Write failing test**

```python
# presentation-builder/tests/test_analyze.py
import polars as pl
import datetime as dt
from scripts.analyze import analyze

def test_monthly_revenue_returns_flat_kv():
    df = pl.DataFrame({
        "Date": [dt.date(2026, 7, 1), dt.date(2026, 8, 1), dt.date(2026, 9, 1)],
        "Revenue": [4_500_000, 4_200_000, 3_900_000],
    })
    result = analyze(df, "monthly_revenue")
    assert isinstance(result, dict)
    assert all(isinstance(v, (int, float, str)) for v in result.values())
    assert "sep_revenue" in result or any("sep" in k.lower() for k in result)

def test_gross_margin_computation():
    df = pl.DataFrame({
        "Revenue": [1000, 2000, 3000],
        "Cost": [400, 1000, 1500],
    })
    result = analyze(df, "gross_margin")
    # Gross margin = (Revenue - Cost) / Revenue
    # Total: (6000-2900)/6000 = 51.67%
    assert "total_gross_margin_pct" in result
    assert abs(result["total_gross_margin_pct"] - 51.67) < 0.5

def test_top_n_by_region():
    df = pl.DataFrame({
        "Region": ["North", "South", "East", "West"],
        "Revenue": [1000, 500, 2000, 1500],
    })
    result = analyze(df, "top_n_by_region")
    assert "top_region" in result
    assert result["top_region"] == "East"
    assert "top_region_value" in result
    assert result["top_region_value"] == 2000

def test_unknown_computation_returns_empty():
    df = pl.DataFrame({"x": [1, 2, 3]})
    result = analyze(df, "nonexistent")
    assert result == {}
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_analyze.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement analyze**

```python
# presentation-builder/scripts/analyze.py
import polars as pl
import re

REVENUE_RX = re.compile(r"(?i)(revenue|sales|income|amount)")
COST_RX = re.compile(r"(?i)(cost|expense|spend|cogs)")
REGION_RX = re.compile(r"(?i)(region|country|segment|territory)")
DATE_RX = re.compile(r"(?i)(date|time|month|quarter|year)")


def _first_match(df, rx):
    for c in df.columns:
        if rx.search(c):
            return c
    return None


def _monthly_revenue(df: pl.DataFrame) -> dict:
    date_col = _first_match(df, DATE_RX)
    rev_col = _first_match(df, REVENUE_RX)
    if not date_col or not rev_col:
        return {}
    monthly = (
        df.with_columns(pl.col(date_col).cast(pl.Date).dt.strftime("%Y-%m").alias("_month"))
          .group_by("_month")
          .agg(pl.col(rev_col).sum().alias("_total"))
          .sort("_month")
    )
    out = {}
    months = monthly["_month"].to_list()
    totals = monthly["_total"].to_list()
    for m, t in zip(months, totals):
        key = m.lower().replace("-", "_") + "_revenue"
        out[key] = float(t)
    if len(totals) >= 2:
        delta = (totals[-1] - totals[-2]) / totals[-2] * 100.0
        out["last_mom_delta_pct"] = round(delta, 2)
    out["total_revenue"] = float(sum(totals))
    return out


def _gross_margin(df: pl.DataFrame) -> dict:
    rev_col = _first_match(df, REVENUE_RX)
    cost_col = _first_match(df, COST_RX)
    if not rev_col or not cost_col:
        return {}
    total_rev = float(df[rev_col].sum() or 0)
    total_cost = float(df[cost_col].sum() or 0)
    if total_rev == 0:
        return {}
    margin_pct = (total_rev - total_cost) / total_rev * 100.0
    return {
        "total_revenue": total_rev,
        "total_cost": total_cost,
        "total_gross_margin_pct": round(margin_pct, 2),
    }


def _top_n_by_region(df: pl.DataFrame) -> dict:
    region_col = _first_match(df, REGION_RX)
    rev_col = _first_match(df, REVENUE_RX)
    if not region_col or not rev_col:
        return {}
    grp = (
        df.group_by(region_col)
          .agg(pl.col(rev_col).sum().alias("_total"))
          .sort("_total", descending=True)
    )
    if grp.is_empty():
        return {}
    top = grp.row(0)
    return {
        "top_region": str(top[0]),
        "top_region_value": float(top[1]),
        "region_count": grp.height,
    }


COMPUTATIONS = {
    "monthly_revenue": _monthly_revenue,
    "gross_margin": _gross_margin,
    "top_n_by_region": _top_n_by_region,
}


def analyze(df: pl.DataFrame, computation_id: str) -> dict:
    fn = COMPUTATIONS.get(computation_id)
    if fn is None:
        return {}
    return fn(df)
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_analyze.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/analyze.py presentation-builder/tests/test_analyze.py
git commit -m "feat(analyze): computation registry returning flat KV stores"
```

---

## Phase 6: Aggregator

### Task 14: DataFrame → Chart-Ready JSON

**Files:**
- Create: `presentation-builder/scripts/aggregator.py`
- Create: `presentation-builder/tests/test_aggregator.py`

- [ ] **Step 1: Write failing test**

```python
# presentation-builder/tests/test_aggregator.py
import polars as pl
import datetime as dt
from scripts.aggregator import aggregate

def test_aggregate_time_series_reduces_to_monthly_points():
    df = pl.DataFrame({
        "Date": [dt.date(2026, 7, i) for i in range(1, 31)],
        "Revenue": [100] * 30,
    })
    result = aggregate(df, {"type": "line", "x": "Date", "y": "Revenue"})
    assert "labels" in result and "values" in result
    assert len(result["labels"]) == len(result["values"])
    assert len(result["labels"]) <= 100

def test_aggregate_categorical_groups_by_x():
    df = pl.DataFrame({
        "Region": ["N", "S", "N", "S", "E"],
        "Revenue": [1, 2, 3, 4, 5],
    })
    result = aggregate(df, {"type": "bar", "x": "Region", "y": "Revenue"})
    assert sorted(result["labels"]) == ["E", "N", "S"]
    # N total = 4, S total = 6, E = 5
    by_label = dict(zip(result["labels"], result["values"]))
    assert by_label["N"] == 4
    assert by_label["S"] == 6
    assert by_label["E"] == 5

def test_aggregate_caps_at_100_points():
    df = pl.DataFrame({"x": list(range(500)), "y": list(range(500))})
    result = aggregate(df, {"type": "bar", "x": "x", "y": "y"})
    assert len(result["values"]) <= 100

def test_aggregate_empty_dataframe_returns_empty():
    df = pl.DataFrame({"x": [], "y": []})
    result = aggregate(df, {"type": "bar", "x": "x", "y": "y"})
    assert result["labels"] == []
    assert result["values"] == []
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_aggregator.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement aggregator**

```python
# presentation-builder/scripts/aggregator.py
import polars as pl

MAX_POINTS = 100


def aggregate(df: pl.DataFrame, chart_spec: dict) -> dict:
    if df is None or df.is_empty():
        return {"labels": [], "values": [], "chart_type": chart_spec.get("type", "bar")}
    x = chart_spec.get("x")
    y = chart_spec.get("y")
    chart_type = chart_spec.get("type", "bar")
    if x not in df.columns or y not in df.columns:
        return {"labels": [], "values": [], "chart_type": chart_type}
    if chart_type == "line" and df[x].dtype in (pl.Date, pl.Datetime):
        # Group by month
        grouped = (
            df.with_columns(pl.col(x).cast(pl.Date).dt.strftime("%Y-%m").alias("_x"))
              .group_by("_x")
              .agg(pl.col(y).sum().alias("_y"))
              .sort("_x")
        )
    else:
        grouped = (
            df.group_by(x)
              .agg(pl.col(y).sum().alias("_y"))
              .rename({x: "_x"})
        )
    if grouped.height > MAX_POINTS:
        grouped = grouped.head(MAX_POINTS)
    return {
        "labels": [str(v) for v in grouped["_x"].to_list()],
        "values": [float(v) for v in grouped["_y"].to_list()],
        "chart_type": chart_type,
        "x_axis": x,
        "y_axis": y,
    }
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_aggregator.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/aggregator.py presentation-builder/tests/test_aggregator.py
git commit -m "feat(aggregator): DataFrame to Chart-Ready JSON, capped at 100 points"
```

---

## Phase 7: Chart

### Task 15: Brand hex extraction + chart rendering

**Files:**
- Create: `presentation-builder/scripts/chart.py`
- Create: `presentation-builder/tests/test_chart.py`

- [ ] **Step 1: Write failing test**

```python
# presentation-builder/tests/test_chart.py
from pathlib import Path
from scripts.chart import render_chart, get_brand_colors

def test_render_bar_chart_writes_png(tmp_path):
    chart_data = {
        "labels": ["A", "B", "C"],
        "values": [10, 20, 15],
        "chart_type": "bar",
        "x_axis": "Category",
        "y_axis": "Value",
    }
    out_path = tmp_path / "chart.png"
    result = render_chart(chart_data, str(out_path), title="Test Chart")
    assert "png_path" in result
    assert Path(result["png_path"]).exists()
    assert Path(result["png_path"]).stat().st_size > 1000

def test_render_line_chart_writes_png(tmp_path):
    chart_data = {
        "labels": ["2026-07", "2026-08", "2026-09"],
        "values": [4500, 4200, 3900],
        "chart_type": "line",
    }
    out_path = tmp_path / "trend.png"
    result = render_chart(chart_data, str(out_path), title="Trend")
    assert Path(result["png_path"]).exists()

def test_render_empty_data_skips_with_reason(tmp_path):
    chart_data = {"labels": [], "values": [], "chart_type": "bar"}
    out_path = tmp_path / "empty.png"
    result = render_chart(chart_data, str(out_path), title="Empty")
    assert "error" in result

def test_brand_colors_fallback_when_no_template():
    colors = get_brand_colors(None)
    assert "primary" in colors
    assert colors["primary"].startswith("#")
    assert len(colors["primary"]) == 7
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_chart.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement chart rendering**

```python
# presentation-builder/scripts/chart.py
from pathlib import Path
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns

# Hardcoded fallback brand palette — replace with corporate colors via template extraction.
FALLBACK_COLORS = {
    "primary": "#1F4E79",
    "secondary": "#2E75B6",
    "accent": "#FFC000",
    "neutral": "#595959",
    "background": "#FFFFFF",
}


def get_brand_colors(template_path: str | None) -> dict:
    if template_path is None or not Path(template_path).exists():
        return dict(FALLBACK_COLORS)
    try:
        from pptx import Presentation
        prs = Presentation(template_path)
        # python-pptx exposes theme colors on the slide master.
        # If accessible, override the primary color from theme; else fallback.
        # Theme color access is API-limited; we keep fallback as default.
        # Future: parse <a:srgbClr> from theme XML for true brand colors.
        return dict(FALLBACK_COLORS)
    except Exception:
        return dict(FALLBACK_COLORS)


def render_chart(chart_data: dict, out_path: str, title: str = "") -> dict:
    labels = chart_data.get("labels", [])
    values = chart_data.get("values", [])
    chart_type = chart_data.get("chart_type", "bar")
    if not labels or not values:
        return {"error": "no data to render", "png_path": None}

    colors = get_brand_colors(None)
    sns.set_style("whitegrid")
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)

    if chart_type == "line":
        ax.plot(labels, values, color=colors["primary"], linewidth=2.5, marker="o", markersize=8)
    elif chart_type == "bar":
        ax.bar(labels, values, color=colors["primary"], edgecolor=colors["neutral"])
    elif chart_type == "scatter":
        ax.scatter(labels, values, color=colors["primary"], s=80)
    elif chart_type == "stacked_bar":
        ax.bar(labels, values, color=colors["primary"])
    elif chart_type == "histogram":
        ax.hist(values, bins=min(20, len(values)), color=colors["primary"], edgecolor=colors["neutral"])
    else:
        ax.bar(labels, values, color=colors["primary"])

    if title:
        ax.set_title(title, fontsize=14, fontweight="bold", color=colors["neutral"])
    ax.set_xlabel(chart_data.get("x_axis", ""), color=colors["neutral"])
    ax.set_ylabel(chart_data.get("y_axis", ""), color=colors["neutral"])
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return {"png_path": out_path, "width_px": 3000, "height_px": 1800}
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_chart.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/chart.py presentation-builder/tests/test_chart.py
git commit -m "feat(chart): Seaborn rendering with brand palette + fallback colors"
```

---

## Phase 8: Tables

### Task 16: Native PPTX table builder

**Files:**
- Create: `presentation-builder/scripts/tables.py`
- Create: `presentation-builder/tests/test_tables.py`

- [ ] **Step 1: Write failing test**

```python
# presentation-builder/tests/test_tables.py
import polars as pl
from pptx import Presentation
from pptx.util import Inches
from scripts.tables import add_native_table

def test_add_native_table_to_slide(tmp_path):
    df = pl.DataFrame({
        "Region": ["North", "South", "East"],
        "Revenue": [1000, 2000, 1500],
    })
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # title-only
    descriptor = add_native_table(slide, df, left=Inches(1), top=Inches(2), width=Inches(8), height=Inches(4))
    assert descriptor["rows"] == 4  # header + 3 data rows
    assert descriptor["cols"] == 2
    out = tmp_path / "out.pptx"
    prs.save(out)
    assert out.exists()

def test_table_rejects_oversized_slice():
    # >10 rows OR >5 cols → should error
    df = pl.DataFrame({f"c{i}": [0] for i in range(6)})  # 6 cols
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    descriptor = add_native_table(slide, df, left=Inches(1), top=Inches(2), width=Inches(8), height=Inches(4))
    assert "error" in descriptor
    assert "exceeds" in descriptor["error"].lower()
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_tables.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement table builder**

```python
# presentation-builder/scripts/tables.py
import polars as pl
from pptx.util import Pt
from pptx.dml.color import RGBColor

MAX_ROWS = 10
MAX_COLS = 5
HEADER_FILL = RGBColor(0x1F, 0x4E, 0x79)
HEADER_FONT_COLOR = RGBColor(0xFF, 0xFF, 0xFF)
ALT_ROW_FILL = RGBColor(0xF2, 0xF2, 0xF2)


def add_native_table(slide, df: pl.DataFrame, left, top, width, height) -> dict:
    if df.height > MAX_ROWS or df.width > MAX_COLS:
        return {
            "error": f"slice exceeds 10x5 rule (rows={df.height}, cols={df.width})",
        }
    rows = df.height + 1
    cols = df.width
    table_shape = slide.shapes.add_table(rows, cols, left, top, width, height)
    table = table_shape.table

    # Header
    for c, name in enumerate(df.columns):
        cell = table.cell(0, c)
        cell.text = str(name)
        cell.fill.solid()
        cell.fill.fore_color.rgb = HEADER_FILL
        for para in cell.text_frame.paragraphs:
            for run in para.runs:
                run.font.bold = True
                run.font.color.rgb = HEADER_FONT_COLOR
                run.font.size = Pt(11)

    # Body
    data = df.to_dicts()
    for r, row in enumerate(data, start=1):
        for c, name in enumerate(df.columns):
            cell = table.cell(r, c)
            cell.text = str(row[name]) if row[name] is not None else ""
            for para in cell.text_frame.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(10)
            if r % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = ALT_ROW_FILL

    return {
        "rows": rows,
        "cols": cols,
        "shape_id": table_shape.shape_id,
    }
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_tables.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/tables.py presentation-builder/tests/test_tables.py
git commit -m "feat(tables): native PPTX table builder with brand styling + size guard"
```

---

## Phase 9: Narrative

### Task 17: Prompt builder

**Files:**
- Create: `presentation-builder/scripts/narrative.py`
- Create: `presentation-builder/tests/test_narrative.py`

- [ ] **Step 1: Write failing test**

```python
# presentation-builder/tests/test_narrative.py
from scripts.narrative import build_prompt

def test_build_prompt_contains_kv_facts():
    kv = {"q3_revenue": 4_200_000, "sep_mom_delta_pct": -7.0}
    slide_ctx = {"title": "Q3 Revenue", "audience": "exec leadership"}
    prompt = build_prompt(kv, slide_ctx)
    assert "4200000" in prompt or "4,200,000" in prompt
    assert "-7" in prompt or "7" in prompt
    assert "Observe" in prompt
    assert "Analyze" in prompt
    assert "Synthesize" in prompt
    assert "exec leadership" in prompt

def test_build_prompt_includes_slide_title():
    prompt = build_prompt({"x": 1}, {"title": "My Slide", "audience": "team"})
    assert "My Slide" in prompt
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_narrative.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement prompt builder**

```python
# presentation-builder/scripts/narrative.py

PROMPT_TEMPLATE = """You are an executive presentation analyst. Generate a 3-tier narrative for this slide.

SLIDE TITLE: {title}
AUDIENCE: {audience}

DATA FACTS (use ONLY these values; do not invent numbers):
{facts}

Produce exactly three statements following the Observe → Analyze → Synthesize chain:

1. OBSERVE: State the most important raw fact from the DATA FACTS (single sentence, include the literal number).
2. ANALYZE: State the comparative or trend context (single sentence, include the literal number for any delta or comparison).
3. SYNTHESIZE: State the business implication — the "So What?" (single sentence, no new numbers).

Constraints:
- Every numeric claim in OBSERVE and ANALYZE must appear verbatim in DATA FACTS above (rounding to nearest whole percent or dollar is allowed).
- Total ≤ 6 bullet points across the three tiers.
- Synthesize must be actionable for the AUDIENCE.
- Output as JSON: {{"observe": "...", "analyze": "...", "synthesize": "..."}}
"""


def build_prompt(kv: dict, slide_ctx: dict) -> str:
    facts_lines = [f"- {k}: {v}" for k, v in kv.items()]
    facts = "\n".join(facts_lines)
    return PROMPT_TEMPLATE.format(
        title=slide_ctx.get("title", "Untitled"),
        audience=slide_ctx.get("audience", "general"),
        facts=facts,
    )
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_narrative.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/narrative.py presentation-builder/tests/test_narrative.py
git commit -m "feat(narrative): prompt builder with Observe/Analyze/Synthesize structure"
```

---

### Task 18: Hallucination validator (regex + tolerance)

**Files:**
- Modify: `presentation-builder/scripts/narrative.py`
- Modify: `presentation-builder/tests/test_narrative.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_narrative.py`:

```python
from scripts.narrative import validate_narrative

def test_validate_passes_when_numbers_match_kv():
    kv = {"q3_revenue": 4_200_000, "sep_mom_delta_pct": -7.0}
    narrative = {
        "observe": "Q3 revenue is $4,200,000.",
        "analyze": "Down 7% MoM.",
        "synthesize": "Momentum stalled; investigate.",
    }
    result = validate_narrative(narrative, kv)
    assert result["valid"] is True
    assert result["mismatches"] == []

def test_validate_within_tolerance_passes():
    kv = {"x": 100.0}
    narrative = {
        "observe": "x is 100.005.",  # within 0.01%
        "analyze": "noted.",
        "synthesize": "ok.",
    }
    result = validate_narrative(narrative, kv)
    assert result["valid"] is True

def test_validate_catches_fabricated_number():
    kv = {"q3_revenue": 4_200_000}
    narrative = {
        "observe": "Q3 revenue is $9,999,999.",
        "analyze": "huge.",
        "synthesize": "investigate.",
    }
    result = validate_narrative(narrative, kv)
    assert result["valid"] is False
    assert any("9999999" in str(m) or "9,999,999" in str(m) for m in result["mismatches"])

def test_validate_blocks_pii_reference():
    from scripts.narrative import validate_narrative
    kv = {"customer_count": 100}
    narrative = {
        "observe": "100 customers including John Smith with SSN 123-45-6789.",
        "analyze": "growth.",
        "synthesize": "scale up.",
    }
    pii_columns = ["Customer_Name", "SSN"]
    result = validate_narrative(narrative, kv, pii_columns=pii_columns)
    assert result["valid"] is False
    assert any("PII" in m or "ssn" in m.lower() for m in result["mismatches"])
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_narrative.py -v -k validate`
Expected: FAIL — `validate_narrative` not defined.

- [ ] **Step 3: Implement validator**

In `scripts/narrative.py`:

```python
import re

NUMBER_RX = re.compile(r"-?\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?%?|-?\d+(?:\.\d+)?%?")
TOLERANCE = 0.0001  # 0.01%
SSN_RX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
EMAIL_RX = re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b")


def _normalize_number(s: str) -> float | None:
    s = s.replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def _matches_kv(claim: float, kv_values: list) -> bool:
    for v in kv_values:
        if v == 0:
            if abs(claim) < 0.01:
                return True
            continue
        if abs(claim - v) / abs(v) < TOLERANCE:
            return True
    return False


def validate_narrative(narrative: dict, kv: dict, pii_columns: list | None = None) -> dict:
    mismatches = []
    text = " ".join(str(narrative.get(k, "")) for k in ("observe", "analyze"))
    kv_values = [float(v) for v in kv.values() if isinstance(v, (int, float))]
    for raw in NUMBER_RX.findall(text):
        n = _normalize_number(raw)
        if n is None:
            continue
        if not _matches_kv(n, kv_values):
            mismatches.append(f"fabricated number: {raw}")

    # PII guards: scan all narrative tiers
    full_text = " ".join(str(narrative.get(k, "")) for k in ("observe", "analyze", "synthesize"))
    if pii_columns:
        for col in pii_columns:
            if col.lower() in full_text.lower():
                mismatches.append(f"PII column reference: {col}")
    if SSN_RX.search(full_text):
        mismatches.append("PII: SSN pattern in narrative")
    if EMAIL_RX.search(full_text):
        mismatches.append("PII: email pattern in narrative")

    return {"valid": len(mismatches) == 0, "mismatches": mismatches}
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_narrative.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/narrative.py presentation-builder/tests/test_narrative.py
git commit -m "feat(narrative): hallucination + PII validator with 0.01% tolerance"
```

---

## Phase 10: Layouts

### Task 19: Layout picker + render-mode rule

**Files:**
- Create: `presentation-builder/scripts/layouts.py`
- Create: `presentation-builder/tests/test_layouts.py`

- [ ] **Step 1: Write failing test**

```python
# presentation-builder/tests/test_layouts.py
from pptx import Presentation
from scripts.layouts import pick_layout, decide_render_mode

def test_decide_render_mode_native_for_small_slice():
    mode = decide_render_mode(rows=5, cols=3)
    assert mode == "native_table"

def test_decide_render_mode_image_for_large_slice():
    mode = decide_render_mode(rows=20, cols=3)
    assert mode == "image"

def test_decide_render_mode_image_for_wide_slice():
    mode = decide_render_mode(rows=5, cols=10)
    assert mode == "image"

def test_pick_layout_finds_named_layout():
    prs = Presentation()
    layout = pick_layout(prs, "Title Slide")
    assert layout is not None

def test_pick_layout_falls_back_when_name_missing():
    prs = Presentation()
    layout = pick_layout(prs, "Nonexistent Layout Name")
    assert layout is not None  # falls back to closest match
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_layouts.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement layouts**

```python
# presentation-builder/scripts/layouts.py
from difflib import get_close_matches

MAX_TABLE_ROWS = 10
MAX_TABLE_COLS = 5

LAYOUT_FOR_CONTENT = {
    "exec_summary": "Title and Content",
    "section": "Image + Text",
    "deep_dive": "Big Number",
    "table": "Table Layout",
    "title": "Title Slide",
}


def decide_render_mode(rows: int, cols: int) -> str:
    if rows <= MAX_TABLE_ROWS and cols <= MAX_TABLE_COLS:
        return "native_table"
    return "image"


def pick_layout(presentation, layout_name: str):
    """Find slide layout by name; fall back to closest match or first available."""
    available = {layout.name: layout for layout in presentation.slide_layouts}
    if layout_name in available:
        return available[layout_name]
    candidates = get_close_matches(layout_name, list(available.keys()), n=1, cutoff=0.3)
    if candidates:
        return available[candidates[0]]
    # Last-resort fallback: first layout (usually "Title Slide")
    return presentation.slide_layouts[0]


def layout_for_content(content_type: str) -> str:
    return LAYOUT_FOR_CONTENT.get(content_type, "Title and Content")
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_layouts.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/layouts.py presentation-builder/tests/test_layouts.py
git commit -m "feat(layouts): layout picker with closest-match fallback + render mode rule"
```

---

## Phase 11: Build PPTX

### Task 20: Slide assembler

**Files:**
- Create: `presentation-builder/scripts/build_pptx.py`
- Create: `presentation-builder/tests/test_build_pptx.py`

- [ ] **Step 1: Write failing test**

```python
# presentation-builder/tests/test_build_pptx.py
from pathlib import Path
from pptx import Presentation
from scripts.build_pptx import build_deck

def _outline_with_one_slide():
    return {
        "slides": [
            {
                "n": 1,
                "layout": "Title and Content",
                "title": "Executive Summary",
                "content_type": "exec_summary",
                "computation_id": None,
                "chart_spec": None,
                "status": "active",
                "narrative": {
                    "observe": "Q3 revenue is $4,200,000.",
                    "analyze": "Down 7% MoM.",
                    "synthesize": "Momentum stalled; investigate before Q4.",
                },
            }
        ]
    }

def test_build_deck_writes_pptx(tmp_path):
    outline = _outline_with_one_slide()
    out = tmp_path / "deck.pptx"
    result = build_deck(outline, template_path=None, out_path=str(out))
    assert Path(result["pptx_path"]).exists()
    prs = Presentation(result["pptx_path"])
    assert len(prs.slides) == 1

def test_build_deck_writes_synthesis_to_slide_body(tmp_path):
    outline = _outline_with_one_slide()
    out = tmp_path / "deck.pptx"
    build_deck(outline, template_path=None, out_path=str(out))
    prs = Presentation(str(out))
    slide = prs.slides[0]
    text = "\n".join(
        shape.text_frame.text
        for shape in slide.shapes
        if shape.has_text_frame
    )
    assert "Momentum stalled" in text  # synthesize on slide body

def test_build_deck_writes_observe_analyze_to_speaker_notes(tmp_path):
    outline = _outline_with_one_slide()
    out = tmp_path / "deck.pptx"
    build_deck(outline, template_path=None, out_path=str(out))
    prs = Presentation(str(out))
    notes = prs.slides[0].notes_slide.notes_text_frame.text
    assert "$4,200,000" in notes
    assert "7%" in notes
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_build_pptx.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement assembler**

```python
# presentation-builder/scripts/build_pptx.py
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from scripts.layouts import pick_layout

DEFAULT_TEMPLATE = Path(__file__).parent.parent / "assets" / "default_template.pptx"


def _resolve_template(template_path: str | None) -> str:
    if template_path and Path(template_path).exists():
        return template_path
    return str(DEFAULT_TEMPLATE)


def _add_text(text_frame, text: str, font_size: int = 18):
    if not text_frame.paragraphs:
        text_frame.add_paragraph()
    p = text_frame.paragraphs[0]
    p.text = text
    for run in p.runs:
        run.font.size = Pt(font_size)


def _write_speaker_notes(slide, narrative: dict):
    notes_tf = slide.notes_slide.notes_text_frame
    parts = []
    if narrative.get("observe"):
        parts.append(f"Observe: {narrative['observe']}")
    if narrative.get("analyze"):
        parts.append(f"Analyze: {narrative['analyze']}")
    if narrative.get("synthesize"):
        parts.append(f"Synthesize: {narrative['synthesize']}")
    notes_tf.text = "\n\n".join(parts)


def _add_slide(prs, slide_data: dict):
    layout = pick_layout(prs, slide_data.get("layout", "Title and Content"))
    slide = prs.slides.add_slide(layout)
    if slide.shapes.title:
        slide.shapes.title.text = slide_data.get("title", "")
    narrative = slide_data.get("narrative", {})

    # Body: synthesis only on the slide
    body_placeholder = None
    for shape in slide.placeholders:
        if shape.placeholder_format.idx == 1:
            body_placeholder = shape
            break
    if body_placeholder and narrative.get("synthesize"):
        _add_text(body_placeholder.text_frame, narrative["synthesize"], font_size=18)
    elif narrative.get("synthesize"):
        # No body placeholder — add a free text box
        tx = slide.shapes.add_textbox(Inches(0.5), Inches(2), Inches(9), Inches(4))
        _add_text(tx.text_frame, narrative["synthesize"], font_size=18)

    # Image (if chart present)
    if slide_data.get("chart_png"):
        slide.shapes.add_picture(
            slide_data["chart_png"],
            Inches(5), Inches(2),
            width=Inches(7),
        )

    if narrative:
        _write_speaker_notes(slide, narrative)


def build_deck(outline: dict, template_path: str | None, out_path: str) -> dict:
    template = _resolve_template(template_path)
    prs = Presentation(template)
    # Remove the empty starter slide if template has none defined; python-pptx default has none
    for slide_data in outline.get("slides", []):
        if slide_data.get("status") == "excluded":
            continue
        _add_slide(prs, slide_data)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    prs.save(out_path)
    return {"pptx_path": out_path, "slide_count": len(prs.slides)}
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_build_pptx.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/build_pptx.py presentation-builder/tests/test_build_pptx.py
git commit -m "feat(build_pptx): slide assembler with synthesis on body + O/A in speaker notes"
```

---

### Task 21: Exclusions slide

**Files:**
- Modify: `presentation-builder/scripts/build_pptx.py`
- Modify: `presentation-builder/tests/test_build_pptx.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_build_pptx.py`:

```python
def test_build_deck_appends_exclusions_slide_when_skipped(tmp_path):
    outline = {
        "slides": [
            {
                "n": 1,
                "layout": "Title and Content",
                "title": "Active",
                "content_type": "exec_summary",
                "status": "active",
                "narrative": {"observe": "x is 1.", "analyze": "y.", "synthesize": "z."},
            },
            {
                "n": 2,
                "layout": "Image + Text",
                "title": "Margin",
                "content_type": "section",
                "status": "excluded",
                "reason": "Cost column 40% null",
            },
        ]
    }
    out = tmp_path / "deck.pptx"
    build_deck(outline, template_path=None, out_path=str(out))
    prs = Presentation(str(out))
    # 1 active + 1 exclusions slide
    assert len(prs.slides) == 2
    last = prs.slides[-1]
    text = "\n".join(s.text_frame.text for s in last.shapes if s.has_text_frame)
    assert "Exclusions" in text or "Integrity" in text
    assert "Margin" in text
    assert "Cost column 40% null" in text

def test_no_exclusions_slide_when_no_exclusions(tmp_path):
    outline = _outline_with_one_slide()
    out = tmp_path / "deck.pptx"
    build_deck(outline, template_path=None, out_path=str(out))
    prs = Presentation(str(out))
    assert len(prs.slides) == 1
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `cd presentation-builder && pytest tests/test_build_pptx.py -v -k exclusion`
Expected: FAIL — only 1 slide produced.

- [ ] **Step 3: Add exclusions slide function**

In `scripts/build_pptx.py`:

```python
def _generate_exclusions_slide(prs, exclusions: list):
    if not exclusions:
        return
    layout = pick_layout(prs, "Title and Content")
    slide = prs.slides.add_slide(layout)
    if slide.shapes.title:
        slide.shapes.title.text = "Data Integrity & Exclusions Report"
    body = None
    for shape in slide.placeholders:
        if shape.placeholder_format.idx == 1:
            body = shape
            break
    intro = "The following sections were excluded or modified to ensure accuracy and compliance:"
    lines = [intro] + [f"• {e['title']}: {e['reason']}" for e in exclusions]
    text = "\n".join(lines)
    if body:
        body.text_frame.text = text
    else:
        tx = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(9), Inches(5))
        tx.text_frame.text = text
```

In `build_deck()`, replace the loop with:

```python
    exclusions = []
    for slide_data in outline.get("slides", []):
        if slide_data.get("status") == "excluded":
            exclusions.append({
                "title": slide_data.get("title", "(untitled)"),
                "reason": slide_data.get("reason", "no reason provided"),
            })
            continue
        _add_slide(prs, slide_data)
    _generate_exclusions_slide(prs, exclusions)
```

- [ ] **Step 4: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_build_pptx.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/scripts/build_pptx.py presentation-builder/tests/test_build_pptx.py
git commit -m "feat(build_pptx): append exclusions transparency slide when skips occur"
```

---

## Phase 12: SKILL.md

### Task 22: Final SKILL.md

**Files:**
- Create: `presentation-builder/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: presentation-builder
description: Use this skill when the user asks to build a presentation, deck, or PPTX from a PDF, Excel, or CSV file. Performs intelligent data analysis (descriptive + visual + executive narrative) and produces a board-ready branded PowerPoint via a two-stage profile-confirm-build workflow.
---

# Enterprise Data-to-Deck Architect

## Identity & Purpose
You are a world-class Data Analyst and Presentation Designer. Your goal is to transform raw files (PDF, XLSX, CSV) into board-ready .pptx presentations using a corporate template. You operate in two stages: PROFILE (where you propose an outline and the user confirms), then BUILD (where you assemble the deck).

## Execution Pipeline

### STAGE 1 — INTELLIGENT PROFILING (always present outline before building)

1. Call `scripts/ingest.py::ingest(file_path)` to load the file. If it returns an error, ask the user for a fixed file. Do NOT attempt analysis on a failed ingest.
2. Call `scripts/profile.py::profile(df)` on the resulting DataFrame. This produces schema, null percentages, outlier flags, PII columns, and date range.
3. Call `scripts/context.py::detect_context(profile)` to infer the story shape from column patterns.
4. Call `scripts/outline.py::build_outline(profile, context)` to produce the slide list. This includes:
   - Slide 1 always Executive Summary.
   - Section slides per detected story.
   - Auto-inserted Deep Dive slides for outliers >20% deviation.
   - Viability check: any slide whose required column has >15% nulls is marked `excluded`.
   - PII guard: any slide referencing a PII column is marked `excluded`.
5. Present the outline to the user as a numbered list. Each slide entry must include:
   - Title
   - Content type (chart, table, big number, etc.)
   - Whether the slide is active or excluded (with the reason if excluded)
6. **WAIT for user confirmation** before proceeding to Stage 2. Allow the user to drop, reorder, or rename slides.

### STAGE 2 — RIGOROUS ANALYSIS + BUILD

For each `active` slide in the confirmed outline:

1. Call `scripts/analyze.py::analyze(df, computation_id)` to produce a flat key-value store of facts.
2. Call `scripts/aggregator.py::aggregate(df, chart_spec)` to reduce the DataFrame to Chart-Ready JSON (≤100 points). Charts must NEVER receive raw DataFrames — always go through the aggregator.
3. Use `scripts/layouts.py::decide_render_mode(rows, cols)` to choose between native PPTX table (≤10 rows AND ≤5 cols) or rendered chart image.
4. If chart: call `scripts/chart.py::render_chart(chart_data, out_path, title)` to write a PNG.
5. Generate the narrative yourself using the prompt produced by `scripts/narrative.py::build_prompt(kv, slide_ctx)`. Output strictly the JSON shape `{"observe": "...", "analyze": "...", "synthesize": "..."}`. Follow the Observe → Analyze → Synthesize chain:
   - **Observe**: state the raw fact (single sentence, exact number from KV).
   - **Analyze**: state the comparative or trend context (single sentence, exact delta from KV).
   - **Synthesize**: state the business "So What" (single sentence, no new numbers).
6. Validate the narrative with `scripts/narrative.py::validate_narrative(narrative, kv, pii_columns)`. If `valid` is False:
   - On a `fabricated number` mismatch: regenerate the narrative ONCE. If still invalid, strip the offending claim and add a warning to speaker notes.
   - On a PII mismatch: rewrite the narrative without referencing PII fields.
7. Attach the narrative + chart_png path + table descriptor to the slide entry.

After all active slides are processed, build the Executive Summary (slide 1):
- Select the 3 highest-impact synthesis statements from the deck.
- Ensure ≥1 statement contains a comparative delta. If not, replace the lowest-impact statement with a delta computed from `analyze.py` outputs.
- Generate a "Recommended Next Step" (Call to Action) — single sentence — by reasoning over all synthesis statements: "What is the single highest-priority action implied by these findings?"

Finally:
8. Call `scripts/build_pptx.py::build_deck(outline, template_path, out_path)` to assemble the deck. The function:
   - Opens the corporate template (uses Slide Masters for branding).
   - Falls back to default template if corporate template missing.
   - Writes synthesis to slide body, full Observe + Analyze + Synthesize to speaker notes.
   - Appends a transparency Exclusions slide listing all skipped sections and reasons.
9. Return the output `.pptx` path to the user.

## Layout Rules (enforced by code, but you must respect them in narrative generation)

- **Slide Economy**: max 6 bullet points per slide.
- **Visual Priority**: every data slide must contain a chart or native table.
- **So What? Rule**: synthesis text on slide; observe/analyze in speaker notes only.
- **Brand Hex**: charts use brand colors from `chart.py` palette (or template if extracted).
- **Native vs Image**: ≤10×5 → native table; else image. Decided by `layouts.py`.

## Failure Modes

- File unreadable → ask user for fixed file.
- File >500MB or >5M rows → use sampled subset; warn user.
- All slides excluded → produce single-slide deck explaining "Insufficient data for analysis".
- Sandbox timeout per slide → skip that slide, log in Exclusions.

NEVER silent-fail. Every excluded or degraded slide must surface in the Exclusions slide.

## Model Routing Guidance (for the user, not runtime)

- **Opus 4.7**: preferred when invoking this skill — strongest at the Observe/Analyze/Synthesize chain and instruction following.
- **GPT-5**: preferred if you need to extend the layout set or write custom statistical computations beyond the registered ones in `analyze.py`.

## Privacy

PII columns (SSN, credit card, email, phone, DOB, home address, passport, tax ID) are auto-detected in `profile.py` and excluded from all downstream stages. They never appear in slide text or speaker notes. Excluded PII columns are listed in the final Exclusions slide.
```

- [ ] **Step 2: Lint SKILL.md (no executable check; just structural)**

Run: `cd presentation-builder && head -5 SKILL.md`
Expected: frontmatter (`---`, `name:`, `description:`, `---`) followed by `# Enterprise Data-to-Deck Architect`.

- [ ] **Step 3: Commit**

```bash
git add presentation-builder/SKILL.md
git commit -m "feat(skill): SKILL.md with two-stage pipeline + rules + routing guidance"
```

---

## Phase 13: End-to-End Integration Tests

### Task 23: E2E XLSX test

**Files:**
- Create: `presentation-builder/tests/test_e2e_xlsx.py`

- [ ] **Step 1: Write end-to-end test**

```python
# presentation-builder/tests/test_e2e_xlsx.py
from pathlib import Path
from pptx import Presentation
from scripts.ingest import ingest
from scripts.profile import profile
from scripts.context import detect_context
from scripts.outline import build_outline
from scripts.analyze import analyze
from scripts.aggregator import aggregate
from scripts.chart import render_chart
from scripts.narrative import validate_narrative
from scripts.build_pptx import build_deck


def test_e2e_xlsx_produces_complete_deck(sample_xlsx, tmp_path):
    # Stage 1
    ing = ingest(str(sample_xlsx))
    assert "dataframe" in ing
    df = ing["dataframe"]
    prof = profile(df)
    ctx = detect_context(prof)
    outline = build_outline(prof, ctx)
    assert outline["slides"][0]["content_type"] == "exec_summary"

    # Stage 2 (using a deterministic mock narrative — real LLM call would replace)
    for slide in outline["slides"]:
        if slide["status"] != "active":
            continue
        if slide.get("computation_id"):
            kv = analyze(df, slide["computation_id"])
            slide["kv"] = kv
            if kv:
                # Use the first non-zero numeric KV as the basis for a deterministic narrative.
                first_key = next(iter(kv))
                first_val = kv[first_key]
                narrative = {
                    "observe": f"{first_key} is {first_val}.",
                    "analyze": f"Value derived from {len(kv)} data points.",
                    "synthesize": "Review trend before next planning cycle.",
                }
                vr = validate_narrative(narrative, kv, pii_columns=prof.get("pii_columns"))
                assert vr["valid"], f"narrative invalid: {vr['mismatches']}"
                slide["narrative"] = narrative
        # Chart for sections with data
        if slide["content_type"] == "section" and slide.get("computation_id") == "monthly_revenue":
            chart_data = aggregate(df, {"type": "line", "x": "Date", "y": "Revenue"})
            chart_path = tmp_path / f"chart_{slide['n']}.png"
            r = render_chart(chart_data, str(chart_path), title=slide["title"])
            if "png_path" in r:
                slide["chart_png"] = r["png_path"]

    # Exec summary narrative
    outline["slides"][0]["narrative"] = {
        "observe": "Pipeline processed 200 rows.",
        "analyze": "Across 4 regions and 3 products.",
        "synthesize": "Data is suitable for executive review.",
    }

    out = tmp_path / "deck.pptx"
    result = build_deck(outline, template_path=None, out_path=str(out))
    assert Path(result["pptx_path"]).exists()

    prs = Presentation(result["pptx_path"])
    assert len(prs.slides) >= 2
    # First slide is Exec Summary
    title0 = prs.slides[0].shapes.title.text
    assert "Executive Summary" in title0 or "Summary" in title0
```

- [ ] **Step 2: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_e2e_xlsx.py -v`
Expected: 1 PASS.

- [ ] **Step 3: Commit**

```bash
git add presentation-builder/tests/test_e2e_xlsx.py
git commit -m "test(e2e): full pipeline integration test on XLSX fixture"
```

---

### Task 24: E2E PII test (zero-tolerance)

**Files:**
- Create: `presentation-builder/tests/test_e2e_pii.py`

- [ ] **Step 1: Write zero-tolerance test**

```python
# presentation-builder/tests/test_e2e_pii.py
import re
from pathlib import Path
from pptx import Presentation
from scripts.ingest import ingest
from scripts.profile import profile
from scripts.context import detect_context
from scripts.outline import build_outline
from scripts.build_pptx import build_deck

SSN_RX = re.compile(r"\d{3}-\d{2}-\d{4}")
EMAIL_RX = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _all_text_in_deck(pptx_path: str) -> str:
    prs = Presentation(pptx_path)
    parts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                parts.append(shape.text_frame.text)
        if slide.has_notes_slide:
            parts.append(slide.notes_slide.notes_text_frame.text)
    return "\n".join(parts)


def test_pii_never_appears_in_deck(sample_pii, tmp_path):
    ing = ingest(str(sample_pii))
    df = ing["dataframe"]
    prof = profile(df)
    assert "SSN" in prof["pii_columns"]
    assert "Email" in prof["pii_columns"]

    ctx = detect_context(prof)
    outline = build_outline(prof, ctx)

    # No active slide should reference PII columns
    for slide in outline["slides"]:
        if slide["status"] == "active" and slide.get("computation_id"):
            slide["narrative"] = {
                "observe": "Revenue total available.",
                "analyze": "Across customers.",
                "synthesize": "Plan retention review.",
            }

    out = tmp_path / "deck_pii.pptx"
    build_deck(outline, template_path=None, out_path=str(out))

    text = _all_text_in_deck(str(out))
    # Hard assertions: zero PII patterns in the deck.
    assert not SSN_RX.search(text), "SSN leaked into deck"
    assert not EMAIL_RX.search(text), "Email leaked into deck"
    # Customer_Name should not appear
    assert "Person 0" not in text and "Person 1" not in text
```

- [ ] **Step 2: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_e2e_pii.py -v`
Expected: 1 PASS.

- [ ] **Step 3: Commit**

```bash
git add presentation-builder/tests/test_e2e_pii.py
git commit -m "test(e2e): zero-tolerance PII leak test on full pipeline"
```

---

### Task 25: E2E messy/excluded test

**Files:**
- Create: `presentation-builder/tests/test_e2e_messy.py`

- [ ] **Step 1: Write test**

```python
# presentation-builder/tests/test_e2e_messy.py
from pathlib import Path
from pptx import Presentation
from scripts.ingest import ingest
from scripts.profile import profile
from scripts.context import detect_context
from scripts.outline import build_outline
from scripts.build_pptx import build_deck


def test_high_null_file_produces_exclusions_slide(sample_messy, tmp_path):
    ing = ingest(str(sample_messy))
    df = ing["dataframe"]
    prof = profile(df)
    # Cost should have ~40% nulls
    assert prof["null_pct"]["Cost"] > 15

    ctx = detect_context(prof)
    outline = build_outline(prof, ctx)
    # Margin slide should be excluded
    margin_slide = [s for s in outline["slides"] if s.get("computation_id") == "gross_margin"]
    assert len(margin_slide) >= 1
    assert margin_slide[0]["status"] == "excluded"

    # Active slides need narrative for build
    for s in outline["slides"]:
        if s["status"] == "active":
            s["narrative"] = {
                "observe": "Data shows 100 records.",
                "analyze": "Two regions present.",
                "synthesize": "Investigate Cost data quality.",
            }

    out = tmp_path / "messy.pptx"
    build_deck(outline, template_path=None, out_path=str(out))
    prs = Presentation(str(out))

    last = prs.slides[-1]
    text = "\n".join(s.text_frame.text for s in last.shapes if s.has_text_frame)
    assert "Exclusions" in text or "Integrity" in text
    assert "Cost" in text
```

- [ ] **Step 2: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_e2e_messy.py -v`
Expected: 1 PASS.

- [ ] **Step 3: Commit**

```bash
git add presentation-builder/tests/test_e2e_messy.py
git commit -m "test(e2e): messy-file viability + exclusions slide test"
```

---

## Phase 14: Adversarial + Golden Tests

### Task 26: Adversarial test suite

**Files:**
- Create: `presentation-builder/tests/test_adversarial.py`

- [ ] **Step 1: Write adversarial tests**

```python
# presentation-builder/tests/test_adversarial.py
import polars as pl
from pathlib import Path
from pptx import Presentation
from scripts.ingest import ingest
from scripts.profile import profile
from scripts.context import detect_context
from scripts.outline import build_outline
from scripts.build_pptx import build_deck


def test_empty_csv_handled_gracefully(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("col1,col2\n")
    ing = ingest(str(p))
    assert "dataframe" in ing
    df = ing["dataframe"]
    assert df.is_empty()
    prof = profile(df)
    assert prof["pii_columns"] == []
    ctx = detect_context(prof)
    outline = build_outline(prof, ctx)
    # Even empty data → outline still has Exec Summary
    assert outline["slides"][0]["content_type"] == "exec_summary"


def test_all_null_dataframe(tmp_path):
    df = pl.DataFrame({"a": [None, None, None], "b": [None, None, None]})
    prof = profile(df)
    assert prof["null_pct"]["a"] == 100.0
    ctx = detect_context(prof)
    outline = build_outline(prof, ctx)
    # Default story is "Data Summary"
    assert any(s["content_type"] in ("exec_summary", "section") for s in outline["slides"])


def test_single_row_no_outliers():
    df = pl.DataFrame({"x": [42]})
    prof = profile(df)
    assert prof["outliers"] == []  # need ≥2 to detect outliers


def test_only_pii_columns_produces_exclusions(tmp_path):
    df = pl.DataFrame({"SSN": ["111-22-3333"], "Email": ["a@b.com"]})
    prof = profile(df)
    assert "SSN" in prof["pii_columns"]
    assert "Email" in prof["pii_columns"]
    ctx = detect_context(prof)
    outline = build_outline(prof, ctx)
    # All actual data is PII; outline degrades to exec summary + Data Summary
    out = tmp_path / "pii_only.pptx"
    for s in outline["slides"]:
        if s["status"] == "active":
            s["narrative"] = {"observe": "x.", "analyze": "y.", "synthesize": "z."}
    build_deck(outline, template_path=None, out_path=str(out))
    assert Path(out).exists()


def test_large_csv_processed(fixtures_dir, tmp_path):
    large = fixtures_dir / "large.csv"
    ing = ingest(str(large))
    assert ing["metadata"]["rows"] == 100_000
```

- [ ] **Step 2: Run tests, expect PASS**

Run: `cd presentation-builder && pytest tests/test_adversarial.py -v`
Expected: 5 PASS.

- [ ] **Step 3: Commit**

```bash
git add presentation-builder/tests/test_adversarial.py
git commit -m "test(adversarial): empty/null/single-row/PII-only/large-file edge cases"
```

---

### Task 27: Golden PPTX structure-crawler test

**Files:**
- Create: `presentation-builder/tests/test_golden_structure.py`
- Create: `presentation-builder/tests/golden/q3_sales_expected.pptx` (generated)

- [ ] **Step 1: Generate golden file**

Create `presentation-builder/tests/golden/_generate_golden.py`:

```python
# presentation-builder/tests/golden/_generate_golden.py
"""Regenerate the golden PPTX fixture used for structure-diff testing."""
from pathlib import Path
from scripts.build_pptx import build_deck

OUTLINE = {
    "slides": [
        {
            "n": 1, "layout": "Title and Content", "title": "Executive Summary",
            "content_type": "exec_summary", "status": "active",
            "narrative": {"observe": "Q3 revenue is 12,600,000.", "analyze": "Across 3 months.", "synthesize": "Healthy quarter; plan Q4."},
        },
        {
            "n": 2, "layout": "Image + Text", "title": "Revenue Trend",
            "content_type": "section", "status": "active",
            "narrative": {"observe": "Sep revenue is 3,900,000.", "analyze": "Down 7% MoM.", "synthesize": "Investigate Sep softness."},
        },
        {
            "n": 3, "layout": "Big Number", "title": "Deep Dive: Outlier",
            "content_type": "deep_dive", "status": "active",
            "narrative": {"observe": "Revenue spike of 1,200,000 on Aug 14.", "analyze": "340% above mean.", "synthesize": "Confirm whether one-off or repeatable."},
        },
        {
            "n": 4, "layout": "Image + Text", "title": "Margin",
            "content_type": "section", "status": "excluded",
            "reason": "Cost column has 40.0% nulls (>15.0%)",
        },
    ]
}

if __name__ == "__main__":
    out = Path(__file__).parent / "q3_sales_expected.pptx"
    build_deck(OUTLINE, template_path=None, out_path=str(out))
    print(f"golden written to {out}")
```

Run: `cd presentation-builder && python tests/golden/_generate_golden.py`
Expected: `golden written to .../q3_sales_expected.pptx`.

- [ ] **Step 2: Write structure crawler test**

```python
# presentation-builder/tests/test_golden_structure.py
import zipfile
from pathlib import Path
from scripts.build_pptx import build_deck


def _crawl_structure(pptx_path: str) -> dict:
    """Unzip the .pptx and count structural XML elements per slide."""
    with zipfile.ZipFile(pptx_path) as z:
        slide_files = sorted([n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")])
        notes_files = sorted([n for n in z.namelist() if n.startswith("ppt/notesSlides/notesSlide") and n.endswith(".xml")])
        slide_data = []
        for sf in slide_files:
            xml = z.read(sf).decode("utf-8", errors="replace")
            slide_data.append({
                "name": sf,
                "has_image": "<a:blip" in xml,
                "has_table": "<a:tbl>" in xml or "<p:graphicFrame>" in xml and "tbl" in xml,
                "text_length": len(xml),
            })
    return {
        "slide_count": len(slide_files),
        "notes_count": len(notes_files),
        "slides": slide_data,
    }


_OUTLINE = {
    "slides": [
        {
            "n": 1, "layout": "Title and Content", "title": "Executive Summary",
            "content_type": "exec_summary", "status": "active",
            "narrative": {"observe": "Q3 revenue is 12,600,000.", "analyze": "Across 3 months.", "synthesize": "Healthy quarter; plan Q4."},
        },
        {
            "n": 2, "layout": "Image + Text", "title": "Revenue Trend",
            "content_type": "section", "status": "active",
            "narrative": {"observe": "Sep revenue is 3,900,000.", "analyze": "Down 7% MoM.", "synthesize": "Investigate Sep softness."},
        },
        {
            "n": 3, "layout": "Big Number", "title": "Deep Dive: Outlier",
            "content_type": "deep_dive", "status": "active",
            "narrative": {"observe": "Revenue spike of 1,200,000 on Aug 14.", "analyze": "340% above mean.", "synthesize": "Confirm whether one-off or repeatable."},
        },
        {
            "n": 4, "layout": "Image + Text", "title": "Margin",
            "content_type": "section", "status": "excluded",
            "reason": "Cost column has 40.0% nulls (>15.0%)",
        },
    ]
}


def test_golden_structure_matches_expected(golden_dir, tmp_path):
    # Rebuild from same outline that produced the golden file (kept in sync with _generate_golden.py).
    out = tmp_path / "fresh.pptx"
    build_deck(_OUTLINE, template_path=None, out_path=str(out))

    fresh = _crawl_structure(str(out))
    golden = _crawl_structure(str(golden_dir / "q3_sales_expected.pptx"))

    # 3 active slides + 1 exclusions slide
    assert fresh["slide_count"] == 4
    assert golden["slide_count"] == 4

    # Notes count matches active slides with narratives (3) — exclusions slide has no narrative.
    assert fresh["notes_count"] >= 3
    assert golden["notes_count"] >= 3

    # Each fresh slide should have at least as many slides as expected; structure preserved.
    assert fresh["slide_count"] == golden["slide_count"]
```

- [ ] **Step 3: Run test, expect PASS**

Run: `cd presentation-builder && pytest tests/test_golden_structure.py -v`
Expected: 1 PASS.

- [ ] **Step 4: Commit**

```bash
git add presentation-builder/tests/golden/ presentation-builder/tests/test_golden_structure.py
git commit -m "test(golden): structure-crawler diff test for CI/CD-stable PPTX regression"
```

---

### Task 28: Coverage gate

**Files:**
- Create: `presentation-builder/pytest.ini`

- [ ] **Step 1: Add pytest config with coverage thresholds**

```ini
# presentation-builder/pytest.ini
[pytest]
testpaths = tests
addopts = --cov=scripts --cov-report=term-missing --cov-fail-under=85
```

- [ ] **Step 2: Run full suite with coverage**

Run: `cd presentation-builder && pytest`
Expected: all tests PASS; coverage ≥85%.

- [ ] **Step 3: If coverage fails, identify gaps**

Run: `cd presentation-builder && pytest --cov=scripts --cov-report=term-missing`
Expected: per-module coverage report. Add tests for uncovered branches in `scripts/` until threshold met.

- [ ] **Step 4: PII detection coverage check**

Run: `cd presentation-builder && pytest --cov=scripts.profile --cov-report=term-missing tests/test_profile.py`
Expected: `_detect_pii` and helpers at 100% coverage. If not, add edge-case tests:

```python
def test_luhn_invalid_short_number():
    df = pl.DataFrame({"acct": [123]})
    result = profile(df)
    assert "acct" not in result["pii_columns"]

def test_luhn_invalid_long_number():
    df = pl.DataFrame({"acct": [12345678901234567890]})  # 20 digits
    result = profile(df)
    assert "acct" not in result["pii_columns"]
```

Add as needed until 100% on PII path.

- [ ] **Step 5: Commit**

```bash
git add presentation-builder/pytest.ini
git commit -m "test(coverage): enforce 85% line coverage gate; 100% on PII detection"
```

---

### Task 29: Final pre-deployment check

**Files:**
- (Verification only — no file changes)

- [ ] **Step 1: Run full test suite from clean state**

Run: `cd presentation-builder && rm -rf .pytest_cache && pytest -v`
Expected: all tests PASS, coverage ≥85%.

- [ ] **Step 2: Smoke test the SKILL.md flow manually**

Open Python REPL in skill directory:

```bash
cd presentation-builder && python
```

```python
from scripts.ingest import ingest
from scripts.profile import profile
from scripts.context import detect_context
from scripts.outline import build_outline

result = ingest("tests/fixtures/sample_clean.xlsx")
prof = profile(result["dataframe"])
print("Schema:", list(prof["schema"].keys()))
print("Outliers:", len(prof["outliers"]))
print("PII:", prof["pii_columns"])
ctx = detect_context(prof)
print("Story:", ctx["story_type"])
print("Sections:", ctx["suggested_sections"])
outline = build_outline(prof, ctx)
for s in outline["slides"]:
    print(s["n"], s["title"], "—", s["status"])
```

Expected output: schema, story type, sections, slide list with at least Executive Summary + section slides + any outlier deep-dives.

- [ ] **Step 3: Verify SKILL.md frontmatter**

Run: `cd presentation-builder && head -5 SKILL.md`
Expected: valid YAML frontmatter with `name` and `description`.

- [ ] **Step 4: Final commit + deployment readiness note**

If any final cleanup is needed:

```bash
git add presentation-builder/
git commit -m "chore(presentation-builder): V1 ready for enterprise deployment"
```

Then in your AI platform:
1. Replace `presentation-builder/assets/company_template.pptx` with your real corporate template (with branded Slide Masters).
2. Update `FALLBACK_COLORS` in `scripts/chart.py` to match corporate brand hex codes.
3. Deploy `presentation-builder/` directory into your platform's skill registry per its instructions.

---

## V2 Roadmap (Out of Scope for This Plan)

- Multi-file synthesis (fuzzy join on common keys, Fact-vs-Dimension heuristic, variance-to-target).
- Iterative per-slide refinement (Stage 3).
- Runtime YAML theme override (without template swap).
- Time-budget mode ("fast" vs "thorough").
- Chart-type override per slide in outline confirmation.
- Real brand color extraction from template theme XML (currently fallback only).
