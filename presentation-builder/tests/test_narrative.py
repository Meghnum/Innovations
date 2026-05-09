from scripts.narrative import build_prompt


def test_build_prompt_contains_kv_facts():
    kv = {"q3_revenue": 4_200_000, "sep_mom_delta_pct": -7.0}
    slide_ctx = {"title": "Q3 Revenue", "audience": "exec leadership"}
    prompt = build_prompt(kv, slide_ctx)
    assert "4200000" in prompt or "4,200,000" in prompt
    assert "-7" in prompt or "7" in prompt
    assert "Observe" in prompt
    assert "Analyze" in prompt
    assert "Synthesize" in prompt
    assert "exec leadership" in prompt


def test_build_prompt_includes_slide_title():
    prompt = build_prompt({"x": 1}, {"title": "My Slide", "audience": "team"})
    assert "My Slide" in prompt
