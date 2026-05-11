from pptx import Presentation
from scripts.layouts import pick_layout, decide_render_mode


def test_decide_render_mode_native_for_small_slice():
    mode = decide_render_mode(rows=5, cols=3)
    assert mode == "native_table"


def test_decide_render_mode_image_for_large_slice():
    mode = decide_render_mode(rows=20, cols=3)
    assert mode == "image"


def test_decide_render_mode_image_for_wide_slice():
    mode = decide_render_mode(rows=5, cols=10)
    assert mode == "image"


def test_pick_layout_finds_named_layout():
    prs = Presentation()
    layout = pick_layout(prs, "Title Slide")
    assert layout is not None


def test_pick_layout_falls_back_when_name_missing():
    prs = Presentation()
    layout = pick_layout(prs, "Nonexistent Layout Name")
    assert layout is not None  # falls back
