"""Tests for quality scoring."""

import pytest

from app.models import BlipSubmission, Ring, Quadrant
from app.quality import (
    RING_EVIDENCE,
    _BONUS_TOTAL,
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


def test_quality_full_blip_with_all_ring_bonuses():
    """Full blip with Adopt ring and all evidence earns max quality."""
    blip = BlipSubmission(
        name="Terraform",
        quadrant=Quadrant.PLATFORMS,
        ring=Ring.ADOPT,
        description="Infrastructure as code tool for managing cloud resources",
        client_references=["Client A", "Client B"],
        submitter_name="Jane",
        submitter_contact="jane@tw.com",
        why_now="Mature and widely adopted",
        alternatives_considered=["Pulumi"],
        strengths=["Declarative"],
        weaknesses=["HCL learning curve"],
    )
    completeness, quality = calculate_scores(blip)
    assert completeness == 100.0
    # (100 + 40) / 140 * 100 = 100.0
    assert quality == 100.0


def test_quality_without_ring_equals_completeness_scaled():
    """When no ring is set, quality = completeness / 140 * 100."""
    blip = BlipSubmission(
        name="Docker",
        quadrant=Quadrant.TOOLS,
        description="Containerization platform",
        submitter_name="Jane",
        submitter_contact="jane@tw.com",
    )
    completeness = calculate_completeness(blip)
    quality = calculate_quality(blip)
    # No ring → no bonus → quality = completeness / 140 * 100
    assert quality == pytest.approx(completeness / 140 * 100)


def test_quality_denominator_equal_across_rings():
    """Same blip data with different rings produces the same quality score.

    This is the core fairness guarantee: each ring has exactly 40 bonus
    points, so the denominator is always 140.
    """
    # Use a blip that fills ALL ring-specific evidence fields for every ring
    kwargs = dict(
        name="Docker",
        quadrant=Quadrant.TOOLS,
        description="Containerization platform",
        client_references=["Client A", "Client B"],
        submitter_name="Jane",
        submitter_contact="jane@tw.com",
        why_now="Cloud-native adoption",
        alternatives_considered=["Podman"],
        strengths=["Ecosystem"],
        weaknesses=["Image sizes"],
    )
    scores = []
    for ring in Ring:
        blip = BlipSubmission(ring=ring, **kwargs)
        _, quality = calculate_scores(blip)
        scores.append(quality)
    # All should be identical because completeness=100 and all ring checks pass
    assert len(set(scores)) == 1
    assert scores[0] == 100.0


def test_quality_with_ring_bonus_partial():
    """Quality includes ring bonus when some evidence is present."""
    blip = BlipSubmission(
        name="Terraform",
        quadrant=Quadrant.PLATFORMS,
        ring=Ring.ADOPT,
        description="Short description",
        submitter_name="Jane",
        submitter_contact="jane@tw.com",
        why_now="Yes",
        alternatives_considered=["Pulumi"],
        strengths=["Good"],
    )
    completeness, quality = calculate_scores(blip)
    assert completeness == 85.0  # missing client_references (10) and weaknesses (5)
    # Adopt bonus: client_references (need 2, have 0) = 0,
    # description (filled) = 10, strengths (filled) = 10 → bonus = 20
    assert quality == pytest.approx((85.0 + 20) / 140 * 100)


def test_ring_evidence_totals_are_equal():
    """Every ring must have exactly the same total bonus points."""
    for ring_name, checks in RING_EVIDENCE.items():
        total = sum(c["bonus"] for c in checks)
        assert total == _BONUS_TOTAL, (
            f"Ring {ring_name} has {total} bonus points, expected {_BONUS_TOTAL}"
        )


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


# ---------------------------------------------------------------------------
# get_ring_gaps tests
# ---------------------------------------------------------------------------


def test_ring_gaps_adopt_missing_refs():
    """Adopt blip without 2 client refs should report a gap."""
    blip = BlipSubmission(
        name="Docker",
        ring=Ring.ADOPT,
        description="A containerization platform",
        strengths=["Ecosystem"],
    )
    gaps = get_ring_gaps(blip)
    assert any("2 client references" in g for g in gaps)


def test_ring_gaps_adopt_all_met():
    """Adopt blip with all evidence should have no gaps."""
    blip = BlipSubmission(
        name="Docker",
        ring=Ring.ADOPT,
        description="A containerization platform",
        client_references=["Client A", "Client B"],
        strengths=["Ecosystem"],
    )
    gaps = get_ring_gaps(blip)
    assert gaps == []


def test_ring_gaps_hold_missing_weaknesses():
    """Hold blip without weaknesses should report a gap."""
    blip = BlipSubmission(
        name="Legacy Tool",
        ring=Ring.HOLD,
        description="Should avoid",
        alternatives_considered=["Better Tool"],
    )
    gaps = get_ring_gaps(blip)
    assert any("weaknesses" in g.lower() for g in gaps)


def test_ring_gaps_no_ring():
    """No ring set → no ring gaps."""
    blip = BlipSubmission(name="Docker")
    gaps = get_ring_gaps(blip)
    assert gaps == []
