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

def test_ingest_xlsx_returns_dataframe_and_metadata(sample_xlsx):
    result = ingest(str(sample_xlsx))
    assert "dataframe" in result
    assert result["metadata"]["file_type"] == "xlsx"
    assert result["metadata"]["rows"] == 200
    assert result["metadata"]["cols"] == 6

def test_ingest_pdf_extracts_text_blocks(sample_pdf):
    result = ingest(str(sample_pdf))
    assert "metadata" in result
    assert result["metadata"]["file_type"] == "pdf"
    assert "text_blocks" in result["metadata"]
    assert any("Quarterly Report" in t for t in result["metadata"]["text_blocks"])
