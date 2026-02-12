"""Tests for Pydantic models."""

from app.models import BlipSubmission, HistoricalBlip, Quadrant, Ring


def test_ring_enum_values():
    assert Ring.ADOPT.value == "Adopt"
    assert Ring.TRIAL.value == "Trial"
    assert Ring.ASSESS.value == "Assess"
    assert Ring.HOLD.value == "Hold"


def test_quadrant_enum_values():
    assert Quadrant.TECHNIQUES.value == "Techniques"
    assert Quadrant.TOOLS.value == "Tools"
    assert Quadrant.PLATFORMS.value == "Platforms"
    assert Quadrant.LANGUAGES_FRAMEWORKS.value == "Languages & Frameworks"


def test_blip_submission_defaults():
    blip = BlipSubmission()
    assert blip.name is None
    assert blip.ring is None
    assert blip.quadrant is None
    assert blip.description is None
    assert blip.client_references is None
    assert blip.is_resubmission is False
    assert blip.previous_appearances is None
    assert blip.resubmission_rationale is None


def test_blip_submission_with_values():
    blip = BlipSubmission(
        name="Terraform",
        ring=Ring.ADOPT,
        quadrant=Quadrant.PLATFORMS,
        description="Infrastructure as code",
        client_references=["Client A", "Client B"],
        submitter_name="Jane",
    )
    assert blip.name == "Terraform"
    assert blip.ring == Ring.ADOPT
    assert blip.quadrant == Quadrant.PLATFORMS
    assert len(blip.client_references) == 2


def test_blip_submission_serialization():
    blip = BlipSubmission(name="Docker", ring=Ring.TRIAL)
    data = blip.model_dump(exclude_none=True)
    assert data["name"] == "Docker"
    assert data["ring"] == "Trial"
    assert "description" not in data


def test_historical_blip():
    hb = HistoricalBlip(
        name="Terraform",
        ring="Adopt",
        quadrant="Platforms",
        volume="Volume 31 (Oct 2024)",
    )
    assert hb.name == "Terraform"
    assert hb.volume == "Volume 31 (Oct 2024)"
