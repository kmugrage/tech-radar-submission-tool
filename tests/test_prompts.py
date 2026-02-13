"""Tests for system prompt builder."""

from app.prompts import build_system_prompt


def test_build_prompt_includes_blip_state():
    result = build_system_prompt(
        blip_state_json='{"name": "Docker"}',
        completeness_score=50.0,
        quality_score=40.0,
        missing_fields=["ring"],
        ring_gaps=["Needs description"],
    )
    # JSON is re-formatted with indentation for readability
    assert '"name": "Docker"' in result


def test_build_prompt_formats_scores_as_integers():
    result = build_system_prompt(
        blip_state_json="{}",
        completeness_score=75.0,
        quality_score=82.0,
        missing_fields=[],
        ring_gaps=[],
    )
    assert "75%" in result
    assert "82%" in result
    # Should NOT contain decimal points
    assert "75.0%" not in result
    assert "82.0%" not in result


def test_build_prompt_missing_fields_joined():
    result = build_system_prompt(
        blip_state_json="{}",
        completeness_score=0,
        quality_score=0,
        missing_fields=["name", "description", "ring"],
        ring_gaps=[],
    )
    assert "name, description, ring" in result


def test_build_prompt_no_missing_fields():
    result = build_system_prompt(
        blip_state_json="{}",
        completeness_score=100,
        quality_score=100,
        missing_fields=[],
        ring_gaps=[],
    )
    assert "Missing fields: None" in result


def test_build_prompt_contains_coaching_content():
    result = build_system_prompt(
        blip_state_json="{}",
        completeness_score=0,
        quality_score=0,
        missing_fields=[],
        ring_gaps=[],
    )
    assert "Technology Radar blip submission coach" in result
    assert "Techniques" in result
    assert "Tools" in result
    assert "Platforms" in result
    assert "Languages & Frameworks" in result
    assert "Adopt" in result
    assert "Trial" in result
    assert "Assess" in result
    assert "Hold" in result


def test_build_prompt_ring_gaps_formatted():
    result = build_system_prompt(
        blip_state_json="{}",
        completeness_score=50,
        quality_score=40,
        missing_fields=["description"],
        ring_gaps=["Adopt suggests at least 2 client references", "List strengths"],
    )
    assert "Adopt suggests at least 2 client references, List strengths" in result


def test_build_prompt_no_ring_gaps():
    result = build_system_prompt(
        blip_state_json="{}",
        completeness_score=100,
        quality_score=100,
        missing_fields=[],
        ring_gaps=[],
    )
    assert "Ring-specific gaps: None" in result


def test_build_prompt_ring_gaps_default_none():
    """ring_gaps parameter defaults to None when not provided."""
    result = build_system_prompt(
        blip_state_json="{}",
        completeness_score=50,
        quality_score=40,
        missing_fields=["ring"],
    )
    assert "Ring-specific gaps: None" in result


def test_build_prompt_contains_ring_evidence_guidelines():
    result = build_system_prompt(
        blip_state_json="{}",
        completeness_score=0,
        quality_score=0,
        missing_fields=[],
        ring_gaps=[],
    )
    assert "RING-SPECIFIC EVIDENCE GUIDELINES" in result
    assert "2 client references" in result
