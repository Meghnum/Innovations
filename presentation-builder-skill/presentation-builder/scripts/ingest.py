from __future__ import annotations

from pathlib import Path

try:
    import polars as pl
except ImportError as _e:  # pragma: no cover
    raise ImportError(
        "presentation-builder requires 'polars' — pip install polars "
        "(use polars-lts-cpu on emulated/older CPUs)") from _e

# SKILL.md failure mode: very large files are sampled, never fully loaded.
MAX_INGEST_ROWS = 5_000_000


def _ingest_pdf(p: Path) -> dict:
    try:
        import fitz  # PyMuPDF — imported lazily so CSV/XLSX ingest works without it
    except ImportError:
        return {"error": "PDF ingestion requires PyMuPDF — pip install PyMuPDF"}
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


def ingest(file_path: str) -> dict:
    """Load a CSV/XLSX/PDF into {"dataframe": pl.DataFrame, "metadata": {...}}
    or {"error": <plain reason>}. CSVs larger than MAX_INGEST_ROWS are
    sampled (first rows) with a parse warning — never fully materialised."""
    p = Path(file_path)
    if not p.exists():
        return {"error": f"file not found: {file_path}"}
    ext = p.suffix.lower()
    warnings = []
    try:
        if ext == ".csv":
            # n_rows stops reading at the cap — a 100M-row export is never
            # fully materialised (SKILL.md: sample and warn)
            df = pl.read_csv(p, n_rows=MAX_INGEST_ROWS + 1)
            if df.height > MAX_INGEST_ROWS:
                df = df.head(MAX_INGEST_ROWS)
                warnings.append(
                    f"large file: loaded the first {MAX_INGEST_ROWS:,} rows only "
                    f"(skill size cap); figures describe that sample")
        elif ext in (".xlsx", ".xls"):
            df = pl.read_excel(p)   # xlsx sheets cap at ~1M rows; no sampling needed
        elif ext == ".pdf":
            return _ingest_pdf(p)
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
            "parse_warnings": warnings,
            "file_type": ext.lstrip("."),
        },
    }