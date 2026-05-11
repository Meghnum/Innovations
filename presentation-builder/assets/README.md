# Assets

- `default_template.pptx` — generated fallback template (11 python-pptx default layouts, 16:9). Used when no corporate template is supplied. The default does NOT contain the named layouts the skill expects ("Image + Text", "Two-Column", "Big Number", "Table Layout") — `scripts/layouts.py` uses closest-match fallback in that case.
- `company_template.pptx` — REPLACE THIS with your enterprise PPTX template containing branded Slide Masters before deployment.
  For best results, name your Slide Master layouts: "Title Slide", "Title and Content", "Image + Text", "Two-Column", "Big Number", "Table Layout".
  If your layout names differ, `scripts/layouts.py` will pick the closest match.
