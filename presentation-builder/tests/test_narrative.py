from scripts.narrative import build_prompt, validate_narrative


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


def test_validate_passes_when_numbers_match_kv():
    kv = {"q3_revenue": 4_200_000, "sep_mom_delta_pct": -7.0}
    narrative = {
        "observe": "Q3 revenue is $4,200,000.",
        "analyze": "Down 7% MoM.",
        "synthesize": "Momentum stalled; investigate.",
    }
    result = validate_narrative(narrative, kv)
    assert result["valid"] is True
    assert result["mismatches"] == []


def test_validate_within_tolerance_passes():
    kv = {"x": 100.0}
    narrative = {
        "observe": "x is 100.005.",  # within 0.01%
        "analyze": "noted.",
        "synthesize": "ok.",
    }
    result = validate_narrative(narrative, kv)
    assert result["valid"] is True


def test_validate_catches_fabricated_number():
    kv = {"q3_revenue": 4_200_000}
    narrative = {
        "observe": "Q3 revenue is $9,999,999.",
        "analyze": "huge.",
        "synthesize": "investigate.",
    }
    result = validate_narrative(narrative, kv)
    assert result["valid"] is False
    assert any("9999999" in str(m) or "9,999,999" in str(m) for m in result["mismatches"])


def test_validate_blocks_pii_reference():
    kv = {"customer_count": 100}
    narrative = {
        "observe": "100 customers including John Smith with SSN 123-45-6789.",
        "analyze": "growth.",
        "synthesize": "scale up.",
    }
    pii_columns = ["Customer_Name", "SSN"]
    result = validate_narrative(narrative, kv, pii_columns=pii_columns)
    assert result["valid"] is False
    assert any("PII" in m or "ssn" in m.lower() for m in result["mismatches"])
