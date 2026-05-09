from pathlib import Path
from scripts.chart import render_chart, get_brand_colors

def test_render_bar_chart_writes_png(tmp_path):
    chart_data = {
        "labels": ["A", "B", "C"],
        "values": [10, 20, 15],
        "chart_type": "bar",
        "x_axis": "Category",
        "y_axis": "Value",
    }
    out_path = tmp_path / "chart.png"
    result = render_chart(chart_data, str(out_path), title="Test Chart")
    assert "png_path" in result
    assert Path(result["png_path"]).exists()
    assert Path(result["png_path"]).stat().st_size > 1000

def test_render_line_chart_writes_png(tmp_path):
    chart_data = {
        "labels": ["2026-07", "2026-08", "2026-09"],
        "values": [4500, 4200, 3900],
        "chart_type": "line",
    }
    out_path = tmp_path / "trend.png"
    result = render_chart(chart_data, str(out_path), title="Trend")
    assert Path(result["png_path"]).exists()

def test_render_empty_data_skips_with_reason(tmp_path):
    chart_data = {"labels": [], "values": [], "chart_type": "bar"}
    out_path = tmp_path / "empty.png"
    result = render_chart(chart_data, str(out_path), title="Empty")
    assert "error" in result

def test_brand_colors_fallback_when_no_template():
    colors = get_brand_colors(None)
    assert "primary" in colors
    assert colors["primary"].startswith("#")
    assert len(colors["primary"]) == 7
