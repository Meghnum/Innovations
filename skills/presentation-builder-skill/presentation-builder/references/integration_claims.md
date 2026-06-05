# Claims-analytics → deck integration (the combined agent)

The two skills compose: **claims-data-analytics produces accurate, cited numbers; this
skill turns them into an executive deck.** In the combined agent, a claims question
flows: run claims-data-analytics → collect the answers as `insights` → call
`profile.outline_from_analytics(insights)` → outline-first approval → build.

## The insight contract

Pass a list of dicts. Only `metric` is required; the richer it is, the better the
slide. The compute/definition work is already done by claims-data-analytics — do NOT
recompute here.

```
{
  "metric": "Closing Ratio",          # business name (already plain-language)
  "value": 0.93,
  "display": "93%",                    # pre-formatted for the slide
  "period": "Apr 2025",
  "comparison": {"prior": 0.88, "delta_pct": 5.7},   # optional, drives deltas
  "definition": "Claims closed in the period / claims opened in the period.",
  "provenance": "OWNER-DEFINED",       # or INDUSTRY-STANDARD / PROPRIETARY
  "app": "MAR - Operational",          # source dashboard (for the footnote/notes)
  "app_url": "https://.../app",        # link placeholder from the claims skill
  "rag": "amber",                      # owner Red/Amber/Green band, if any
  "breakdown": {"labels": ["UK","FR"], "values": [420, 310]}  # optional -> bar
}
```

## How insights become slides

- `breakdown` present → **comparative bar** (distinct claims by category).
- a `comparison.delta_pct` → **KPI card** with the delta in the title.
- otherwise → **KPI card** (headline number).
- Slides are scored by impact (RAG severity + delta magnitude) and trimmed to the
  10-slide budget; red/worsening metrics surface first.

## What must be preserved from claims-data-analytics

- **Accuracy & citation:** the figures are the claims skill's; never alter or
  invent. The narrative validator still runs as a backstop.
- **Provenance:** in speaker notes, name the source dashboard and flag any
  non-owner-approved definition. Surface the RAG band in plain words.
- **Business language:** slides stay free of column/indicator/formula names —
  the claims skill already enforces this; the deck must not reintroduce it.
