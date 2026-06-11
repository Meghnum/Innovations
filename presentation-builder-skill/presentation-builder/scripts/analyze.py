from __future__ import annotations

try:
    import polars as pl
except ImportError as _e:  # pragma: no cover
    raise ImportError(
        "presentation-builder requires 'polars' — pip install polars "
        "(use polars-lts-cpu on emulated/older CPUs)") from _e
import re

_MONTH_ABBR = {
    "01": "jan", "02": "feb", "03": "mar", "04": "apr",
    "05": "may", "06": "jun", "07": "jul", "08": "aug",
    "09": "sep", "10": "oct", "11": "nov", "12": "dec",
}

REVENUE_RX = re.compile(r"(?i)(revenue|sales|income|amount)")
COST_RX = re.compile(r"(?i)(cost|expense|spend|cogs)")
REGION_RX = re.compile(r"(?i)(region|country|segment|territory)")
DATE_RX = re.compile(r"(?i)(date|time|month|quarter|year)")


def _first_match(df, rx):
    for c in df.columns:
        if rx.search(c):
            return c
    return None


def _monthly_revenue(df: pl.DataFrame) -> dict:
    date_col = _first_match(df, DATE_RX)
    rev_col = _first_match(df, REVENUE_RX)
    if not date_col or not rev_col:
        return {}
    monthly = (
        df.with_columns(pl.col(date_col).cast(pl.Date).dt.strftime("%Y-%m").alias("_month"))
          .group_by("_month")
          .agg(pl.col(rev_col).sum().alias("_total"))
          .sort("_month")
    )
    out = {}
    months = monthly["_month"].to_list()
    totals = monthly["_total"].to_list()
    for m, t in zip(months, totals):
        if t is None:          # all-null month: nothing factual to report
            continue
        # m is "YYYY-MM" — use 3-letter month abbr for readability
        mm = m.split("-")[1]
        abbr = _MONTH_ABBR.get(mm, mm)
        key = abbr + "_revenue"
        out[key] = float(t)
    # delta only when both endpoints exist and the prior month is non-zero
    if len(totals) >= 2 and totals[-1] is not None and totals[-2]:
        delta = (totals[-1] - totals[-2]) / totals[-2] * 100.0
        out["last_mom_delta_pct"] = round(delta, 2)
    out["total_revenue"] = float(sum(t for t in totals if t is not None))
    return out


def _gross_margin(df: pl.DataFrame) -> dict:
    rev_col = _first_match(df, REVENUE_RX)
    cost_col = _first_match(df, COST_RX)
    if not rev_col or not cost_col:
        return {}
    total_rev = float(df[rev_col].sum() or 0)
    total_cost = float(df[cost_col].sum() or 0)
    if total_rev == 0:
        return {}
    margin_pct = (total_rev - total_cost) / total_rev * 100.0
    return {
        "total_revenue": total_rev,
        "total_cost": total_cost,
        "total_gross_margin_pct": round(margin_pct, 2),
    }


def _top_n_by_region(df: pl.DataFrame) -> dict:
    region_col = _first_match(df, REGION_RX)
    rev_col = _first_match(df, REVENUE_RX)
    if not region_col or not rev_col:
        return {}
    grp = (
        df.group_by(region_col)
          .agg(pl.col(rev_col).sum().alias("_total"))
          .filter(pl.col("_total").is_not_null())   # all-null groups carry no fact
          .sort("_total", descending=True)
    )
    if grp.is_empty():
        return {}
    top = grp.row(0)
    return {
        "top_region": str(top[0]),
        "top_region_value": float(top[1]),
        "region_count": grp.height,
    }


COMPUTATIONS = {
    "monthly_revenue": _monthly_revenue,
    "gross_margin": _gross_margin,
    "top_n_by_region": _top_n_by_region,
}


def analyze(df: pl.DataFrame, computation_id: str) -> dict:
    """Run a registered computation. Returns its facts dict, or {} when the
    computation is unknown, its columns are missing, or it fails internally
    (e.g. an uncastable date column) — no facts beats a traceback or a
    partially-wrong number."""
    fn = COMPUTATIONS.get(computation_id)
    if fn is None:
        return {}
    try:
        return fn(df)
    except Exception:
        return {}


# ── aggregator ────────────────────────────────────────────────────────────────

MAX_POINTS = 100


def aggregate(df: pl.DataFrame, chart_spec: dict) -> dict:
    """Shape data for one chart: group x, sum y, cap at MAX_POINTS.
    Returns {labels, values, chart_type, x_axis, y_axis} (labels/values empty,
    plus an "error" note, when the spec can't be satisfied). Output is
    deterministic: time series sort by period; category charts sort by |value|
    desc (label as tiebreak) so the MAX_POINTS cap keeps the most material
    categories instead of a random subset."""
    if df is None or df.is_empty():
        return {"labels": [], "values": [], "chart_type": chart_spec.get("type", "bar")}
    x = chart_spec.get("x")
    y = chart_spec.get("y")
    chart_type = chart_spec.get("type", "bar")
    if x not in df.columns or y not in df.columns:
        return {"labels": [], "values": [], "chart_type": chart_type}
    if not df.schema[y].is_numeric():
        return {"labels": [], "values": [], "chart_type": chart_type,
                "error": f"measure column '{y}' is not numeric"}
    if chart_type == "line" and df[x].dtype in (pl.Date, pl.Datetime):
        # Group by month
        grouped = (
            df.with_columns(pl.col(x).cast(pl.Date).dt.strftime("%Y-%m").alias("_x"))
              .group_by("_x")
              .agg(pl.col(y).sum().alias("_y"))
              .sort("_x")
        )
    else:
        # polars group_by order is random: sort so output is reproducible and
        # the MAX_POINTS cap keeps the most material categories, not a lottery
        grouped = (
            df.group_by(x)
              .agg(pl.col(y).sum().alias("_y"))
              .rename({x: "_x"})
              .sort([pl.col("_y").abs(), pl.col("_x").cast(pl.String)],
                    descending=[True, False], nulls_last=True)
        )
    if grouped.height > MAX_POINTS:
        grouped = grouped.head(MAX_POINTS)
    return {
        "labels": [str(v) for v in grouped["_x"].to_list()],
        "values": [float(v) for v in grouped["_y"].to_list()],
        "chart_type": chart_type,
        "x_axis": x,
        "y_axis": y,
    }