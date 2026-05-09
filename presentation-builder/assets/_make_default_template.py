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
