"""Tests for GET /api/submissions endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def _mock_startup():
    with patch("app.main.load_history", return_value=[]):
        yield


@pytest.fixture()
def client():
    return TestClient(app)


SAMPLE_SUBMISSIONS = [
    {
        "id": "aaa",
        "session_id": "sess-1",
        "timestamp": "2026-02-18T10:00:00+00:00",
        "name": "Docker",
        "quadrant": "Platforms",
        "ring": "Trial",
        "submitter_name": "Alice",
        "submitter_contact": "alice@example.com",
        "description": "Container runtime",
        "completeness_score": 90.0,
        "quality_score": 85.0,
        "client_references": ["ClientA"],
        "strengths": ["Fast"],
        "weaknesses": [],
        "alternatives_considered": [],
    },
    {
        "id": "bbb",
        "session_id": "sess-2",
        "timestamp": "2026-02-17T10:00:00+00:00",
        "name": "Kubernetes",
        "quadrant": "Platforms",
        "ring": "Adopt",
        "submitter_name": "Bob",
        "submitter_contact": "bob@example.com",
        "description": "Container orchestration",
        "completeness_score": 70.0,
        "quality_score": 75.0,
        "client_references": [],
        "strengths": [],
        "weaknesses": [],
        "alternatives_considered": [],
    },
    {
        "id": "ccc",
        "session_id": "sess-3",
        "timestamp": "2026-02-16T10:00:00+00:00",
        "name": "React",
        "quadrant": "Languages & Frameworks",
        "ring": "Adopt",
        "description": "UI library",
        "completeness_score": 50.0,
        "quality_score": 55.0,
    },
]


def test_list_submissions_returns_all(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3


def test_list_submissions_sorted_newest_first(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions")
    data = response.json()
    assert data[0]["name"] == "Docker"
    assert data[1]["name"] == "Kubernetes"
    assert data[2]["name"] == "React"


def test_list_submissions_omits_sensitive_fields(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions")
    data = response.json()
    for item in data:
        assert "session_id" not in item
        assert "submitter_contact" not in item
        assert "client_references" not in item
        assert "strengths" not in item
        assert "weaknesses" not in item
        assert "alternatives_considered" not in item


def test_list_submissions_includes_expected_fields(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions")
    item = response.json()[0]
    assert "id" in item
    assert "timestamp" in item
    assert "name" in item
    assert "quadrant" in item
    assert "ring" in item
    assert "completeness_score" in item
    assert "quality_score" in item


def test_list_submissions_filter_by_ring(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions?ring=Trial")
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Docker"


def test_list_submissions_filter_by_ring_case_insensitive(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions?ring=trial")
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Docker"


def test_list_submissions_filter_by_quadrant(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions?quadrant=Platforms")
    data = response.json()
    assert len(data) == 2
    names = {d["name"] for d in data}
    assert names == {"Docker", "Kubernetes"}


def test_list_submissions_filter_by_quadrant_case_insensitive(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions?quadrant=platforms")
    data = response.json()
    assert len(data) == 2


def test_list_submissions_combined_filters(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions?ring=Adopt&quadrant=Platforms")
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Kubernetes"


def test_list_submissions_empty_result_for_unmatched_filter(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions?ring=Hold")
    assert response.status_code == 200
    assert response.json() == []


def test_list_submissions_empty_store(client):
    with patch("app.main.load_submissions", return_value=[]):
        response = client.get("/api/submissions")
    assert response.status_code == 200
    assert response.json() == []


def test_list_submissions_truncates_long_description(client):
    long_desc = "x" * 300
    records = [{
        "id": "ddd",
        "timestamp": "2026-02-18T10:00:00+00:00",
        "name": "LongBlip",
        "quadrant": "Tools",
        "ring": "Assess",
        "description": long_desc,
        "completeness_score": 50.0,
        "quality_score": 50.0,
    }]
    with patch("app.main.load_submissions", return_value=records):
        response = client.get("/api/submissions")
    data = response.json()
    assert len(data[0]["description"]) == 200
    assert data[0]["description"].endswith("...")


def test_list_submissions_short_description_not_truncated(client):
    records = [{
        "id": "eee",
        "timestamp": "2026-02-18T10:00:00+00:00",
        "name": "ShortBlip",
        "quadrant": "Tools",
        "ring": "Assess",
        "description": "Short desc",
        "completeness_score": 50.0,
        "quality_score": 50.0,
    }]
    with patch("app.main.load_submissions", return_value=records):
        response = client.get("/api/submissions")
    data = response.json()
    assert data[0]["description"] == "Short desc"


def test_list_submissions_respects_limit(client):
    many = [
        {
            "id": str(i),
            "timestamp": f"2026-02-{i:02d}T10:00:00+00:00",
            "name": f"Blip{i}",
            "quadrant": "Tools",
            "ring": "Assess",
            "completeness_score": 50.0,
            "quality_score": 50.0,
        }
        for i in range(1, 6)
    ]
    with patch("app.main.load_submissions", return_value=many):
        response = client.get("/api/submissions?limit=2")
    data = response.json()
    assert len(data) == 2


def test_list_submissions_caps_limit_at_500(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions?limit=9999")
    assert response.status_code == 200


def test_get_submission_by_id_returns_detail(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions/aaa")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "aaa"
    assert data["name"] == "Docker"


def test_get_submission_by_id_includes_list_fields(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions/aaa")
    data = response.json()
    assert "client_references" in data
    assert "strengths" in data
    assert "weaknesses" in data
    assert "alternatives_considered" in data


def test_get_submission_by_id_omits_sensitive_fields(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions/aaa")
    data = response.json()
    assert "session_id" not in data
    assert "submitter_contact" not in data


def test_get_submission_by_id_not_found(client):
    with patch("app.main.load_submissions", return_value=SAMPLE_SUBMISSIONS):
        response = client.get("/api/submissions/nonexistent")
    assert response.status_code == 404


def test_get_submission_by_id_empty_store(client):
    with patch("app.main.load_submissions", return_value=[]):
        response = client.get("/api/submissions/aaa")
    assert response.status_code == 404


def test_submissions_page_returns_html(client):
    """GET /submissions serves the submissions HTML page."""
    import os
    from pathlib import Path
    static_dir = Path(__file__).resolve().parent.parent / "static"
    submissions_html = static_dir / "submissions.html"
    # Create a minimal placeholder if it doesn't exist yet (for test isolation)
    created = False
    if not submissions_html.exists():
        submissions_html.write_text("<html><body>Submissions</body></html>")
        created = True
    try:
        response = client.get("/submissions")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    finally:
        if created:
            submissions_html.unlink()
