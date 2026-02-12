"""Tests for quality scoring."""

from app.models import BlipSubmission, Ring, Quadrant
from app.quality import (
    calculate_completeness,
    calculate_quality,
    calculate_scores,
    get_missing_fields,
    get_ring_gaps,
)


def test_empty_blip_completeness():
    blip = BlipSubmission()
    assert calculate_completeness(blip) == 0.0


def test_full_blip_completeness():
    blip = BlipSubmission(
        name="Remix",
        quadrant=Quadrant.LANGUAGES_FRAMEWORKS,
        ring=Ring.TRIAL,
        description="A React framework for building web apps.",
        client_references=["Client A"],
        submitter_name="Jane",
        submitter_contact="jane@tw.com",
        why_now="Growing adoption in the industry",
        alternatives_considered=["Next.js"],
        strengths=["Server rendering"],
        weaknesses=["Small ecosystem"],
    )
    assert calculate_completeness(blip) == 100.0


def test_partial_completeness():
    blip = BlipSubmission(name="Docker", ring=Ring.TRIAL)
    score = calculate_completeness(blip)
    # name (10) + ring (5) = 15
    assert score == 15.0


def test_quality_with_adopt_ring_bonuses():
    blip = BlipSubmission(
        name="Terraform",
        quadrant=Quadrant.PLATFORMS,
        ring=Ring.ADOPT,
        description="x" * 250,  # > 200 chars
        client_references=["Client A", "Client B"],  # >= 2
        submitter_name="Jane",
        submitter_contact="jane@tw.com",
        why_now="Mature and widely adopted",
        alternatives_considered=["Pulumi"],
        strengths=["Declarative"],
        weaknesses=["HCL learning curve"],  # weakness provided
    )
    completeness, quality = calculate_scores(blip)
    assert completeness == 100.0
    assert quality == 100.0


def test_quality_without_ring_evidence():
    blip = BlipSubmission(
        name="Terraform",
        quadrant=Quadrant.PLATFORMS,
        ring=Ring.ADOPT,
        description="Short description",  # < 200 chars
        # No client references, no weaknesses
        submitter_name="Jane",
        submitter_contact="jane@tw.com",
        why_now="Yes",
        alternatives_considered=["Pulumi"],
        strengths=["Good"],
    )
    completeness, quality = calculate_scores(blip)
    assert completeness == 85.0  # missing client_references (10) and weaknesses (5)
    # Quality should be less than 100 because ring bonuses not met
    assert quality < 100.0


def test_missing_fields_empty():
    blip = BlipSubmission()
    missing = get_missing_fields(blip)
    assert "name" in missing
    assert "description" in missing
    assert len(missing) == 11  # all fields


def test_missing_fields_partial():
    blip = BlipSubmission(name="Docker", ring=Ring.TRIAL)
    missing = get_missing_fields(blip)
    assert "name" not in missing
    assert "ring" not in missing
    assert "description" in missing


def test_ring_gaps_adopt():
    blip = BlipSubmission(ring=Ring.ADOPT)
    gaps = get_ring_gaps(blip)
    assert any("Client References" in g for g in gaps)
    assert any("Description" in g for g in gaps)
    assert any("Weaknesses" in g for g in gaps)


def test_ring_gaps_hold():
    blip = BlipSubmission(ring=Ring.HOLD)
    gaps = get_ring_gaps(blip)
    assert any("Weaknesses" in g for g in gaps)
    assert any("Alternatives" in g for g in gaps)


def test_no_ring_no_gaps():
    blip = BlipSubmission()
    gaps = get_ring_gaps(blip)
    assert gaps == []
