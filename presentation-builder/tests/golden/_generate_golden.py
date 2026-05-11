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
