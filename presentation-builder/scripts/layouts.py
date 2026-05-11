from difflib import get_close_matches

MAX_TABLE_ROWS = 10
MAX_TABLE_COLS = 5

LAYOUT_FOR_CONTENT = {
    "exec_summary": "Title and Content",
    "section": "Image + Text",
    "deep_dive": "Big Number",
    "table": "Table Layout",
    "title": "Title Slide",
}


def decide_render_mode(rows: int, cols: int) -> str:
    if rows <= MAX_TABLE_ROWS and cols <= MAX_TABLE_COLS:
        return "native_table"
    return "image"


def pick_layout(presentation, layout_name: str):
    """Find slide layout by name; fall back to closest match or first available."""
    available = {layout.name: layout for layout in presentation.slide_layouts}
    if layout_name in available:
        return available[layout_name]
    candidates = get_close_matches(layout_name, list(available.keys()), n=1, cutoff=0.3)
    if candidates:
        return available[candidates[0]]
    return presentation.slide_layouts[0]


def layout_for_content(content_type: str) -> str:
    return LAYOUT_FOR_CONTENT.get(content_type, "Title and Content")
