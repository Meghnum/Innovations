from pathlib import Path
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns

# Hardcoded fallback brand palette — replace with corporate colors via template extraction.
FALLBACK_COLORS = {
    "primary": "#1F4E79",
    "secondary": "#2E75B6",
    "accent": "#FFC000",
    "neutral": "#595959",
    "background": "#FFFFFF",
}


def get_brand_colors(template_path: str | None) -> dict:
    """Extract brand colors from corporate template's theme XML, or use fallback."""
    if template_path is None or not Path(template_path).exists():
        return dict(FALLBACK_COLORS)
    try:
        import zipfile
        import re
        with zipfile.ZipFile(template_path) as z:
            theme_files = [n for n in z.namelist() if n.startswith("ppt/theme/theme") and n.endswith(".xml")]
            if not theme_files:
                return dict(FALLBACK_COLORS)
            theme_xml = z.read(theme_files[0]).decode("utf-8", errors="replace")
        # Extract sRGB hex codes from theme color scheme; first 6 are typical brand
        # Theme XML uses namespace; use regex to find srgbClr values reliably
        srgb_matches = re.findall(r'<a:srgbClr val="([0-9A-Fa-f]{6})"', theme_xml)
        if len(srgb_matches) < 2:
            return dict(FALLBACK_COLORS)
        # Standard PPTX theme order: bg1, tx1, bg2, tx2, accent1..accent6
        # Use accent1 (index 4) as primary if available, else fallback
        colors = dict(FALLBACK_COLORS)
        # Try to map: tx1 (dark) → neutral, accent1 → primary, accent2 → secondary
        if len(srgb_matches) >= 5:
            colors["primary"] = "#" + srgb_matches[4].upper()
        if len(srgb_matches) >= 6:
            colors["secondary"] = "#" + srgb_matches[5].upper()
        if len(srgb_matches) >= 7:
            colors["accent"] = "#" + srgb_matches[6].upper()
        return colors
    except Exception:
        return dict(FALLBACK_COLORS)


def render_chart(chart_data: dict, out_path: str, title: str = "", template_path: str | None = None) -> dict:
    labels = chart_data.get("labels", [])
    values = chart_data.get("values", [])
    chart_type = chart_data.get("chart_type", "bar")
    if not labels or not values:
        return {"error": "no data to render", "png_path": None}

    colors = get_brand_colors(template_path)
    sns.set_style("whitegrid")
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)

    if chart_type == "line":
        ax.plot(labels, values, color=colors["primary"], linewidth=2.5, marker="o", markersize=8)
    elif chart_type == "bar":
        ax.bar(labels, values, color=colors["primary"], edgecolor=colors["neutral"])
    elif chart_type == "scatter":
        ax.scatter(labels, values, color=colors["primary"], s=80)
    elif chart_type == "stacked_bar":
        ax.bar(labels, values, color=colors["primary"])
    elif chart_type == "histogram":
        ax.hist(values, bins=min(20, len(values)), color=colors["primary"], edgecolor=colors["neutral"])
    else:
        ax.bar(labels, values, color=colors["primary"])

    if title:
        ax.set_title(title, fontsize=14, fontweight="bold", color=colors["neutral"])
    ax.set_xlabel(chart_data.get("x_axis", ""), color=colors["neutral"])
    ax.set_ylabel(chart_data.get("y_axis", ""), color=colors["neutral"])
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return {"png_path": out_path, "width_px": 3000, "height_px": 1800}
