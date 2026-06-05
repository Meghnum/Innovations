from pathlib import Path
import polars as pl
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


def ingest(file_path: str) -> dict:
    p = Path(file_path)
    if not p.exists():
        return {"error": f"file not found: {file_path}"}
    ext = p.suffix.lower()
    try:
        if ext == ".csv":
            df = pl.read_csv(p)
        elif ext in (".xlsx", ".xls"):
            df = pl.read_excel(p)
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
            "parse_warnings": [],
            "file_type": ext.lstrip("."),
        },
    }
