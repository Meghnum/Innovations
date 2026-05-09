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
        elif ext in (".xlsx", ".xls"):
            df = pl.read_excel(p)
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
