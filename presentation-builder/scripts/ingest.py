from pathlib import Path
import polars as pl
import fitz  # PyMuPDF

MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB hard cap

FORMULA_PREFIXES = ("=", "+", "-", "@")

def _strip_formula_prefixes(df: pl.DataFrame) -> pl.DataFrame:
    """Remove leading formula-trigger chars from string cells (Excel/CSV injection guard)."""
    str_cols = [c for c in df.columns if df[c].dtype == pl.String]
    if not str_cols:
        return df
    for c in str_cols:
        df = df.with_columns(
            pl.col(c).map_elements(
                lambda v: v.lstrip("=+-@") if isinstance(v, str) and v.startswith(FORMULA_PREFIXES) else v,
                return_dtype=pl.String,
            ).alias(c)
        )
    return df


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
        df = _strip_formula_prefixes(df)
        return {
            "dataframe": df,
            "metadata": {
                "source": p.name,
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
            "source": p.name,
            "rows": 0,
            "cols": 0,
            "parse_warnings": ["no tables found in PDF"],
            "file_type": "pdf",
            "text_blocks": text_blocks,
        },
    }


def ingest(file_path: str) -> dict:
    p = Path(file_path)
    if not p.exists():
        return {"error": f"file not found: {file_path}"}
    size = p.stat().st_size
    if size > MAX_FILE_BYTES:
        return {"error": f"file too large: {size} bytes (max {MAX_FILE_BYTES})"}
    ext = p.suffix.lower()
    try:
        if ext == ".csv":
            df = pl.read_csv(p)
            df = _strip_formula_prefixes(df)
        elif ext in (".xlsx", ".xls"):
            df = pl.read_excel(p)
            df = _strip_formula_prefixes(df)
        elif ext == ".pdf":
            return _ingest_pdf(p)
        else:
            return {"error": f"unsupported file type: {ext}"}
    except Exception as e:
        return {"error": f"parse failed: {e}"}
    return {
        "dataframe": df,
        "metadata": {
            "source": p.name,
            "rows": df.height,
            "cols": df.width,
            "parse_warnings": [],
            "file_type": ext.lstrip("."),
        },
    }
