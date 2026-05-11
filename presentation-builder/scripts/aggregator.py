import polars as pl

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
        grouped = grouped.head(MAX_POINTS)
    return {
        "labels": [str(v) for v in grouped["_x"].to_list()],
        "values": [float(v) for v in grouped["_y"].to_list()],
        "chart_type": chart_type,
        "x_axis": x,
        "y_axis": y,
    }
