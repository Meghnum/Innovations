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
    out = tmp_path / "fresh.pptx"
    build_deck(_OUTLINE, template_path=None, out_path=str(out))
    fresh = _crawl_structure(str(out))
    golden = _crawl_structure(str(golden_dir / "q3_sales_expected.pptx"))
    # 3 active + 1 exclusions slide
    assert fresh["slide_count"] == 4
    assert golden["slide_count"] == 4
    assert fresh["notes_count"] >= 3
    assert golden["notes_count"] >= 3
    assert fresh["slide_count"] == golden["slide_count"]
