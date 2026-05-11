import polars as pl
import re
import datetime as dt

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
        # m is "YYYY-MM" — use 3-letter month abbr for readability
        mm = m.split("-")[1]
        abbr = _MONTH_ABBR.get(mm, mm)
        key = abbr + "_revenue"
        out[key] = float(t)
    if len(totals) >= 2 and totals[-2] != 0:
        delta = (totals[-1] - totals[-2]) / totals[-2] * 100.0
        out["last_mom_delta_pct"] = round(delta, 2)
    out["total_revenue"] = float(sum(totals))
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
    fn = COMPUTATIONS.get(computation_id)
    if fn is None:
        return {}
    return fn(df)


# ── aggregator ────────────────────────────────────────────────────────────────

MAX_POINTS = 100


def aggregate(df: pl.DataFrame, chart_spec: dict) -> dict:
    if df is None or df.is_empty():
        return {"labels": [], "values": [], "chart_type": chart_spec.get("type", "bar")}
    x = chart_spec.get("x")
    y = chart_spec.get("y")
    chart_type = chart_spec.get("type", "bar")
    if x not in df.columns or y not in df.columns:
        return {"labels": [], "values": [], "chart_type": chart_type}
    if chart_type == "line" and df[x].dtype in (pl.Date, pl.Datetime):
        # Group by month
        grouped = (
            df.with_columns(pl.col(x).cast(pl.Date).dt.strftime("%Y-%m").alias("_x"))
              .group_by("_x")
              .agg(pl.col(y).sum().alias("_y"))
              .sort("_x")
        )
    else:
        grouped = (
            df.group_by(x)
              .agg(pl.col(y).sum().alias("_y"))
              .rename({x: "_x"})
        )
    if grouped.height > MAX_POINTS:
        # Sort by value descending so we keep the most significant points
        if chart_type != "line":  # preserve chronological order for time series
            grouped = grouped.sort("_y", descending=True)
        grouped = grouped.head(MAX_POINTS)
    return {
        "labels": [str(v) for v in grouped["_x"].to_list()],
        "values": [float(v) for v in grouped["_y"].to_list()],
        "chart_type": chart_type,
        "x_axis": x,
        "y_axis": y,
    }
