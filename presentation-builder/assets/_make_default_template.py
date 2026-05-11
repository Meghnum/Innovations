"""Generate a minimal default fallback template (16:9, 11 default python-pptx layouts).

The skill expects layout names like "Image + Text", "Two-Column", "Big Number", "Table Layout"
in the corporate template. The default python-pptx template does NOT contain those names —
scripts/layouts.py uses closest-match fallback when the requested layout name is missing.
"""
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches

OUT = Path(__file__).parent / "default_template.pptx"


def main():
    prs = Presentation()
    # Default slide width/height (16:9)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    prs.save(OUT)
    print(f"default template at {OUT}")

if __name__ == "__main__":
    main()
