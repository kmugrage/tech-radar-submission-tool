"""Tests for JSON file storage."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.models import BlipSubmission, Ring, Quadrant
from app.storage import load_submissions, save_submission


def test_load_empty_submissions(tmp_path):
    sfile = tmp_path / "submissions.json"
    with patch("app.storage.SUBMISSIONS_FILE", sfile), \
         patch("app.storage.DATA_DIR", tmp_path):
        result = load_submissions()
    assert result == []
    assert sfile.exists()
    assert json.loads(sfile.read_text()) == []


def test_save_and_load(tmp_path):
    sfile = tmp_path / "submissions.json"
    blip = BlipSubmission(
        name="Docker",
        ring=Ring.TRIAL,
        quadrant=Quadrant.PLATFORMS,
        description="Container platform",
        submitter_name="Jane",
    )

    with patch("app.storage.SUBMISSIONS_FILE", sfile), \
         patch("app.storage.DATA_DIR", tmp_path):
        record = save_submission(blip, "test-session-1")

    assert record["name"] == "Docker"
    assert record["ring"] == "Trial"
    assert "id" in record
    assert "timestamp" in record
    assert record["session_id"] == "test-session-1"

    with patch("app.storage.SUBMISSIONS_FILE", sfile), \
         patch("app.storage.DATA_DIR", tmp_path):
        submissions = load_submissions()
    assert len(submissions) == 1
    assert submissions[0]["name"] == "Docker"


def test_multiple_submissions(tmp_path):
    sfile = tmp_path / "submissions.json"

    with patch("app.storage.SUBMISSIONS_FILE", sfile), \
         patch("app.storage.DATA_DIR", tmp_path):
        save_submission(BlipSubmission(name="Docker"), "s1")
        save_submission(BlipSubmission(name="Kubernetes"), "s2")
        submissions = load_submissions()

    assert len(submissions) == 2
    names = [s["name"] for s in submissions]
    assert "Docker" in names
    assert "Kubernetes" in names
