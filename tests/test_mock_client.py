"""Tests for mock client (DEV_MODE response generator)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.mock_client import _extract_fields_from_text, _pick_response, get_mock_response
from app.models import BlipSubmission, HistoricalBlip, Quadrant, Ring


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def collect_chunks(gen) -> list[dict]:
    """Drain an async generator into a list."""
    return [chunk async for chunk in gen]


# ---------------------------------------------------------------------------
# _extract_fields_from_text
# ---------------------------------------------------------------------------


class TestExtractFields:
    def test_extract_ring_adopt(self):
        blip = BlipSubmission(name="Docker")
        changes = _extract_fields_from_text("I think this should be in the adopt ring", blip)
        assert changes["ring"] == Ring.ADOPT

    def test_extract_ring_hold(self):
        blip = BlipSubmission(name="Docker")
        changes = _extract_fields_from_text("We should hold on this one", blip)
        assert changes["ring"] == Ring.HOLD

    def test_extract_quadrant_tools(self):
        blip = BlipSubmission(name="Docker")
        changes = _extract_fields_from_text("It belongs in the tools quadrant", blip)
        assert changes["quadrant"] == Quadrant.TOOLS

    def test_extract_quadrant_frameworks_alias(self):
        blip = BlipSubmission(name="React")
        changes = _extract_fields_from_text("It's a frameworks technology", blip)
        assert changes["quadrant"] == Quadrant.LANGUAGES_FRAMEWORKS

    def test_extract_name_from_quoted_text(self):
        blip = BlipSubmission()
        changes = _extract_fields_from_text('I want to submit "Terraform"', blip)
        assert changes["name"] == "Terraform"

    def test_extract_name_single_quotes(self):
        blip = BlipSubmission()
        changes = _extract_fields_from_text("I want to submit 'Terraform'", blip)
        assert changes["name"] == "Terraform"

    def test_no_name_extraction_when_name_set(self):
        blip = BlipSubmission(name="Docker")
        changes = _extract_fields_from_text('I want to submit "Terraform"', blip)
        assert "name" not in changes

    def test_extract_name_filler_stripped(self):
        blip = BlipSubmission()
        changes = _extract_fields_from_text("I'd like to submit Terraform", blip)
        assert changes["name"] == "Terraform"

    def test_extract_client_reference(self):
        blip = BlipSubmission(name="Docker")
        changes = _extract_fields_from_text(
            "We used it on a client project for container orchestration", blip
        )
        assert "client_references" in changes
        assert len(changes["client_references"]) == 1

    def test_extract_email_as_contact(self):
        blip = BlipSubmission(name="Docker")
        changes = _extract_fields_from_text("You can reach me at jane@tw.com", blip)
        assert changes["submitter_contact"] == "jane@tw.com"

    def test_extract_submitter_name(self):
        blip = BlipSubmission()
        changes = _extract_fields_from_text("My name is Jane Smith", blip)
        assert changes["submitter_name"] == "Jane Smith"

    def test_long_text_becomes_description(self):
        blip = BlipSubmission(name="Docker")
        long_text = "x" * 100
        changes = _extract_fields_from_text(long_text, blip)
        assert changes.get("description") == long_text

    def test_short_text_not_description(self):
        blip = BlipSubmission(name="Docker")
        changes = _extract_fields_from_text("short text", blip)
        assert "description" not in changes


# ---------------------------------------------------------------------------
# _pick_response
# ---------------------------------------------------------------------------


class TestPickResponse:
    def test_asks_for_name_first(self):
        blip = BlipSubmission()
        response, pending = _pick_response(blip, "hello", is_submit=False)
        assert "name" in response.lower()
        assert pending == "name"

    def test_asks_for_ring_after_name(self):
        blip = BlipSubmission(name="Docker")
        response, pending = _pick_response(blip, "Docker", is_submit=False)
        assert "ring" in response.lower()
        assert pending == "ring"

    def test_asks_for_quadrant_after_ring(self):
        blip = BlipSubmission(name="Docker", ring=Ring.ADOPT)
        response, pending = _pick_response(blip, "adopt", is_submit=False)
        assert "quadrant" in response.lower()
        assert pending == "quadrant"

    def test_asks_for_description_after_quadrant(self):
        blip = BlipSubmission(name="Docker", ring=Ring.ADOPT, quadrant=Quadrant.PLATFORMS)
        response, pending = _pick_response(blip, "platforms", is_submit=False)
        assert "description" in response.lower()
        assert pending == "description"

    def test_asks_client_refs_when_missing(self):
        blip = BlipSubmission(
            name="Docker",
            ring=Ring.ADOPT,
            quadrant=Quadrant.PLATFORMS,
            description="Container platform for app deployment",
        )
        response, pending = _pick_response(blip, "desc", is_submit=False)
        assert "client" in response.lower()
        assert pending == "client_references"

    def test_adopt_asks_for_2_client_refs(self):
        blip = BlipSubmission(
            name="Docker",
            ring=Ring.ADOPT,
            quadrant=Quadrant.PLATFORMS,
            description="Container platform for app deployment",
        )
        response, pending = _pick_response(blip, "desc", is_submit=False)
        assert "2 client references" in response
        assert pending == "client_references"

    def test_trial_asks_for_1_client_ref(self):
        blip = BlipSubmission(
            name="Docker",
            ring=Ring.TRIAL,
            quadrant=Quadrant.PLATFORMS,
            description="Container platform for app deployment",
        )
        response, pending = _pick_response(blip, "desc", is_submit=False)
        assert "1 client reference" in response
        assert pending == "client_references"

    def test_complete_blip_encourages_submit(self, populated_blip):
        response, pending = _pick_response(populated_blip, "anything", is_submit=False)
        assert "Submit Blip" in response
        assert pending is None

    def test_submit_shows_summary(self, populated_blip):
        response, pending = _pick_response(populated_blip, "", is_submit=True)
        assert "Thanks for your submission" in response
        assert "Terraform" in response
        assert pending is None


# ---------------------------------------------------------------------------
# get_mock_response (async generator)
# ---------------------------------------------------------------------------


class TestGetMockResponse:
    @pytest.mark.asyncio
    async def test_yields_text_deltas_and_done(self):
        blip = BlipSubmission()
        messages = [{"role": "user", "content": "hello"}]
        chunks = await collect_chunks(get_mock_response(messages, blip))

        types = [c["type"] for c in chunks]
        assert "text_delta" in types
        assert types[-1] == "done"

    @pytest.mark.asyncio
    async def test_yields_extract_tool_result_on_field_change(self):
        blip = BlipSubmission()
        messages = [{"role": "user", "content": 'I want to submit "Terraform"'}]
        chunks = await collect_chunks(get_mock_response(messages, blip))

        tool_results = [c for c in chunks if c["type"] == "tool_result"]
        extract_results = [
            c for c in tool_results if c["tool_name"] == "extract_blip_data"
        ]
        assert len(extract_results) == 1
        assert extract_results[0]["data"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_yields_history_check_on_new_name(self):
        match = HistoricalBlip(
            name="Terraform", ring="Adopt", quadrant="Platforms",
            volume="Volume 31 (Oct 2024)",
        )
        blip = BlipSubmission()
        messages = [{"role": "user", "content": 'I want to submit "Terraform"'}]

        with patch("app.mock_client.find_matching_blips", return_value=[match]):
            chunks = await collect_chunks(get_mock_response(messages, blip))

        history_results = [
            c for c in chunks
            if c["type"] == "tool_result" and c["tool_name"] == "check_radar_history"
        ]
        assert len(history_results) == 1
        assert history_results[0]["data"]["found"] is True

    @pytest.mark.asyncio
    async def test_no_history_when_no_matches(self):
        blip = BlipSubmission()
        messages = [{"role": "user", "content": 'I want to submit "Terraform"'}]

        with patch("app.mock_client.find_matching_blips", return_value=[]):
            chunks = await collect_chunks(get_mock_response(messages, blip))

        history_results = [
            c for c in chunks
            if c["type"] == "tool_result" and c["tool_name"] == "check_radar_history"
        ]
        assert len(history_results) == 0

    @pytest.mark.asyncio
    async def test_submit_flow(self, populated_blip):
        messages = [{"role": "user", "content": "please submit"}]
        chunks = await collect_chunks(
            get_mock_response(messages, populated_blip, force_submit=True)
        )

        text = "".join(c["text"] for c in chunks if c["type"] == "text_delta")
        assert "Thanks for your submission" in text
        assert types_ending_done(chunks)


def types_ending_done(chunks: list[dict]) -> bool:
    return chunks[-1]["type"] == "done"
