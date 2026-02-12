"""Tests for radar history loading and matching."""

from unittest.mock import patch

from app.models import HistoricalBlip
from app.radar_history import find_matching_blips, _parse_csv, _normalize_quadrant


SAMPLE_CSV = """name,ring,quadrant,isNew,status,description
Terraform,adopt,platforms,FALSE,no change,"<p>Terraform is...</p>"
Docker,trial,platforms,TRUE,new,"<p>Docker is...</p>"
React,adopt,languages-and-frameworks,FALSE,moved in,"<p>React is...</p>"
"""


def test_parse_csv():
    blips = _parse_csv(SAMPLE_CSV, "Volume 31 (Oct 2024)")
    assert len(blips) == 3
    assert blips[0].name == "Terraform"
    assert blips[0].ring == "Adopt"
    assert blips[0].quadrant == "Platforms"
    assert blips[0].volume == "Volume 31 (Oct 2024)"


def test_parse_csv_normalizes_quadrant():
    blips = _parse_csv(SAMPLE_CSV, "V1")
    react = [b for b in blips if b.name == "React"][0]
    assert react.quadrant == "Languages & Frameworks"


def test_normalize_quadrant():
    assert _normalize_quadrant("techniques") == "Techniques"
    assert _normalize_quadrant("tools") == "Tools"
    assert _normalize_quadrant("platforms") == "Platforms"
    assert _normalize_quadrant("languages-and-frameworks") == "Languages & Frameworks"


def test_find_exact_match():
    history = [
        HistoricalBlip(name="Terraform", ring="Adopt", quadrant="Platforms", volume="V30"),
        HistoricalBlip(name="Terraform", ring="Trial", quadrant="Platforms", volume="V28"),
        HistoricalBlip(name="Docker", ring="Trial", quadrant="Platforms", volume="V30"),
    ]

    with patch("app.radar_history._history", history):
        matches = find_matching_blips("Terraform")
    assert len(matches) == 2
    assert all(m.name == "Terraform" for m in matches)


def test_find_case_insensitive():
    history = [
        HistoricalBlip(name="Terraform", ring="Adopt", quadrant="Platforms", volume="V30"),
    ]

    with patch("app.radar_history._history", history):
        matches = find_matching_blips("terraform")
    assert len(matches) == 1


def test_find_no_match():
    history = [
        HistoricalBlip(name="Terraform", ring="Adopt", quadrant="Platforms", volume="V30"),
    ]

    with patch("app.radar_history._history", history):
        matches = find_matching_blips("Kubernetes")
    assert len(matches) == 0


def test_find_substring_match():
    history = [
        HistoricalBlip(name="React Native", ring="Trial", quadrant="Languages & Frameworks", volume="V30"),
    ]

    with patch("app.radar_history._history", history):
        matches = find_matching_blips("React Native")
    assert len(matches) == 1


def test_find_empty_name():
    history = [
        HistoricalBlip(name="Terraform", ring="Adopt", quadrant="Platforms", volume="V30"),
    ]

    with patch("app.radar_history._history", history):
        matches = find_matching_blips("")
    assert len(matches) == 0
