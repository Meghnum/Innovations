# presentation-builder/tests/test_adversarial.py
import polars as pl
from pathlib import Path
from pptx import Presentation
from scripts.ingest import ingest
from scripts.profile import profile, detect_context, build_outline
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
    assert outline["slides"][0]["content_type"] == "exec_summary"


def test_all_null_dataframe(tmp_path):
    df = pl.DataFrame({"a": [None, None, None], "b": [None, None, None]})
    prof = profile(df)
    assert prof["null_pct"]["a"] == 100.0
    ctx = detect_context(prof)
    outline = build_outline(prof, ctx)
    assert any(s["content_type"] in ("exec_summary", "section") for s in outline["slides"])


def test_single_row_no_outliers():
    df = pl.DataFrame({"x": [42]})
    prof = profile(df)
    assert prof["outliers"] == []


def test_only_pii_columns_produces_exclusions(tmp_path):
    df = pl.DataFrame({"SSN": ["111-22-3333"], "Email": ["a@b.com"]})
    prof = profile(df)
    assert "SSN" in prof["pii_columns"]
    assert "Email" in prof["pii_columns"]
    ctx = detect_context(prof)
    outline = build_outline(prof, ctx)
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
