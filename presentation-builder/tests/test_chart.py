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


def test_brand_colors_extracted_from_template_with_srgb(tmp_path):
    """Generate a minimal pptx-like zip with theme XML and verify color extraction."""
    import zipfile
    fake_template = tmp_path / "fake.pptx"
    theme_xml = '''<?xml version="1.0"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <a:themeElements>
    <a:clrScheme>
      <a:dk1><a:srgbClr val="000000"/></a:dk1>
      <a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="111111"/></a:dk2>
      <a:lt2><a:srgbClr val="EEEEEE"/></a:lt2>
      <a:accent1><a:srgbClr val="FF5733"/></a:accent1>
      <a:accent2><a:srgbClr val="33FF57"/></a:accent2>
    </a:clrScheme>
  </a:themeElements>
</a:theme>'''
    with zipfile.ZipFile(fake_template, "w") as z:
        z.writestr("ppt/theme/theme1.xml", theme_xml)
    colors = get_brand_colors(str(fake_template))
    assert colors["primary"] == "#FF5733"
    assert colors["secondary"] == "#33FF57"


def test_brand_colors_fallback_when_template_invalid(tmp_path):
    bad = tmp_path / "bad.pptx"
    bad.write_bytes(b"not a real pptx")
    colors = get_brand_colors(str(bad))
    assert colors["primary"] == "#1F4E79"  # fallback
