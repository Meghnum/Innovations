# Visual catalog — the only visuals, and the exact spec each must define

Visual-First Law: every slide names one of these, with concrete fields filled in.
`render.visual_spec(slide, kv)` proposes one; you confirm/sharpen it.

## KPI card (`kpi_card`)
A single headline number, optionally with a delta vs prior period. Best for the
one metric a slide is about.
- Required: `label`, `value` (formatted, e.g. "93%"), optional `delta` (e.g. +5.7%).
- Use when: one figure carries the slide (e.g. "Declinatures 1.8%, +50% MoM").

## Comparative bar (`comparative_bar`)
Compare a measure across categories (country, LOB, region, vendor).
- Required: `x_axis` (the category), `y_axis` (the measure), `data_points`
  (label→value pairs, ≤12, pre-aggregated).
- Use when: "by country / by LOB / top N" breakdowns. Counts are distinct claims.

## Trend line (`trend_line`)
A measure over time.
- Required: `x_axis` (period — month/quarter), `y_axis` (measure), `data_points`
  (ordered period→value).
- Use when: showing movement over accounting periods.

## Process diagram (`process_diagram`)
A workflow or funnel (e.g. claim lifecycle, STP path, declinature funnel).
- Required: `steps` (ordered list), optional per-step value/drop-off.
- Use when: the story is a sequence, not a quantity comparison.

## Native table (`native_table`)
Only when ≤10 rows AND ≤5 columns (`render.decide_render_mode`); else render a
chart image. Tables are a last resort — a visual usually lands harder.

Rules: charts are pre-aggregated to ≤100 points via `analyze.aggregate`; never
hand a raw DataFrame to a renderer; brand colours come from the template theme or
the fallback palette.
