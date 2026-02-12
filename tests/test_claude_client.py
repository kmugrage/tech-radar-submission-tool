"""Tests for Claude API client (helper functions and streaming generator)."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from app.claude_client import (
    _build_system,
    _handle_check_history,
    _handle_extract_blip,
    get_claude_response,
)
from app.models import BlipSubmission, HistoricalBlip, Quadrant, Ring


# ---------------------------------------------------------------------------
# Helper to drain async generator
# ---------------------------------------------------------------------------

async def collect_chunks(gen) -> list[dict]:
    return [chunk async for chunk in gen]


# ---------------------------------------------------------------------------
# Fake streaming infrastructure for mocking the Anthropic API
# ---------------------------------------------------------------------------

class FakeContentBlock:
    def __init__(self, type, **kwargs):
        self.type = type
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeDelta:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeEvent:
    def __init__(self, type, **kwargs):
        self.type = type
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeStream:
    """Simulates anthropic's async streaming context manager."""

    def __init__(self, events):
        self._events = list(events)
        self._index = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._index]
        self._index += 1
        return event


def make_text_events(text: str) -> list[FakeEvent]:
    """Create streaming events for a simple text-only response."""
    return [
        FakeEvent(
            "content_block_start",
            content_block=FakeContentBlock("text"),
        ),
        FakeEvent(
            "content_block_delta",
            delta=FakeDelta(text=text),
        ),
    ]


def make_tool_use_events(tool_id: str, tool_name: str, tool_input: dict) -> list[FakeEvent]:
    """Create streaming events for a tool-use response."""
    return [
        FakeEvent(
            "content_block_start",
            content_block=FakeContentBlock("tool_use", id=tool_id, name=tool_name),
        ),
        FakeEvent(
            "content_block_delta",
            delta=FakeDelta(partial_json=json.dumps(tool_input)),
        ),
    ]


# ---------------------------------------------------------------------------
# _build_system
# ---------------------------------------------------------------------------


class TestBuildSystem:
    def test_returns_string_with_state(self):
        blip = BlipSubmission(name="Docker")
        result = _build_system(blip)
        assert isinstance(result, str)
        assert "Docker" in result

    def test_includes_scores(self):
        blip = BlipSubmission(
            name="Docker", ring=Ring.TRIAL, quadrant=Quadrant.PLATFORMS,
            description="A container platform",
        )
        result = _build_system(blip)
        assert "Completeness:" in result
        assert "Quality:" in result


# ---------------------------------------------------------------------------
# _handle_check_history
# ---------------------------------------------------------------------------


class TestHandleCheckHistory:
    def test_no_matches(self):
        with patch("app.claude_client.find_matching_blips", return_value=[]):
            result = _handle_check_history("Unknown Tech")
        assert result == {"found": False, "appearances": []}

    def test_with_matches(self):
        matches = [
            HistoricalBlip(
                name="Docker", ring="Adopt", quadrant="Platforms",
                volume="Volume 31 (Oct 2024)",
            ),
            HistoricalBlip(
                name="Docker", ring="Trial", quadrant="Platforms",
                volume="Volume 28 (Apr 2023)",
            ),
        ]
        with patch("app.claude_client.find_matching_blips", return_value=matches):
            result = _handle_check_history("Docker")

        assert result["found"] is True
        assert len(result["appearances"]) == 2
        assert result["appearances"][0]["volume"] == "Volume 31 (Oct 2024)"
        assert result["appearances"][0]["ring"] == "Adopt"


# ---------------------------------------------------------------------------
# _handle_extract_blip
# ---------------------------------------------------------------------------


class TestHandleExtractBlip:
    def test_merges_data_into_blip(self):
        blip = BlipSubmission()
        result = _handle_extract_blip({"name": "Docker", "ring": Ring.TRIAL}, blip)

        assert blip.name == "Docker"
        assert blip.ring == Ring.TRIAL
        assert result["status"] == "ok"
        assert "completeness_score" in result
        assert "quality_score" in result

    def test_coerces_string_to_enum(self):
        """Claude sends ring/quadrant as strings — they must be coerced to enums."""
        blip = BlipSubmission()
        _handle_extract_blip({"name": "Docker", "ring": "Trial", "quadrant": "Platforms"}, blip)
        assert blip.ring == Ring.TRIAL
        assert blip.quadrant == Quadrant.PLATFORMS

    def test_ignores_none_values(self):
        blip = BlipSubmission(name="Docker", ring=Ring.ADOPT)
        _handle_extract_blip({"name": "Docker", "ring": None}, blip)
        assert blip.ring == Ring.ADOPT  # Not overwritten with None

    def test_ignores_unknown_fields(self):
        blip = BlipSubmission()
        # Should not raise
        result = _handle_extract_blip(
            {"name": "Docker", "unknown_field": "value"}, blip
        )
        assert result["status"] == "ok"
        assert not hasattr(blip, "unknown_field")


# ---------------------------------------------------------------------------
# get_claude_response (mocked streaming)
# ---------------------------------------------------------------------------


def _make_mock_client(*stream_sequences):
    """Create a mock Anthropic client that returns FakeStreams in sequence.

    Each call to client.messages.stream() returns the next FakeStream.
    """
    mock_client = MagicMock()
    streams = [FakeStream(events) for events in stream_sequences]
    mock_client.messages.stream.side_effect = streams
    return mock_client


class TestGetClaudeResponse:
    @pytest.mark.asyncio
    async def test_text_only_response(self):
        mock_client = _make_mock_client(make_text_events("Hello there"))

        with patch("app.claude_client._get_client", return_value=mock_client):
            blip = BlipSubmission()
            messages = [{"role": "user", "content": "hi"}]
            chunks = await collect_chunks(get_claude_response(messages, blip))

        text_chunks = [c for c in chunks if c["type"] == "text_delta"]
        assert len(text_chunks) == 1
        assert text_chunks[0]["text"] == "Hello there"
        assert chunks[-1]["type"] == "done"
        # No messages should have been appended (no tool use loop)
        assert len(messages) == 1

    @pytest.mark.asyncio
    async def test_tool_use_extract_blip(self):
        # Claude sends ring/quadrant as strings — the fix coerces them to enums
        tool_input = {"name": "Docker", "quadrant": "Platforms",
                       "ring": "Trial", "description": None,
                       "client_references": None,
                       "submitter_name": None, "submitter_contact": None,
                       "why_now": None, "alternatives_considered": None,
                       "strengths": None, "weaknesses": None}

        # First API call: tool use
        first_call_events = make_tool_use_events("tool_1", "extract_blip_data", tool_input)
        # Second API call (after tool result): text response
        second_call_events = make_text_events("I've recorded Docker as Trial.")

        mock_client = _make_mock_client(first_call_events, second_call_events)

        with patch("app.claude_client._get_client", return_value=mock_client):
            blip = BlipSubmission()
            messages = [{"role": "user", "content": "Docker for trial"}]
            chunks = await collect_chunks(get_claude_response(messages, blip))

        # Should have yielded a tool_result and then text
        tool_results = [c for c in chunks if c["type"] == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0]["tool_name"] == "extract_blip_data"
        assert tool_results[0]["data"]["status"] == "ok"

        # Blip should have been mutated with proper enum types
        assert blip.name == "Docker"
        assert blip.ring == Ring.TRIAL
        assert blip.quadrant == Quadrant.PLATFORMS

        # Messages should have been appended (assistant + tool results)
        assert len(messages) == 3  # original + assistant + tool_result

        # Final chunk should be done
        assert chunks[-1]["type"] == "done"

    @pytest.mark.asyncio
    async def test_tool_use_check_history(self):
        tool_input = {"name": "Docker"}
        first_call_events = make_tool_use_events("tool_2", "check_radar_history", tool_input)
        second_call_events = make_text_events("Docker has appeared before.")

        mock_client = _make_mock_client(first_call_events, second_call_events)

        with patch("app.claude_client._get_client", return_value=mock_client), \
             patch("app.claude_client.find_matching_blips", return_value=[]):
            blip = BlipSubmission()
            messages = [{"role": "user", "content": "Docker"}]
            chunks = await collect_chunks(get_claude_response(messages, blip))

        tool_results = [c for c in chunks if c["type"] == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0]["tool_name"] == "check_radar_history"
        assert tool_results[0]["data"]["found"] is False

    @pytest.mark.asyncio
    async def test_force_submit_appends_hint(self):
        mock_client = _make_mock_client(make_text_events("Submission summary"))

        with patch("app.claude_client._get_client", return_value=mock_client):
            blip = BlipSubmission(name="Docker")
            messages = [{"role": "user", "content": "submit"}]
            chunks = await collect_chunks(
                get_claude_response(messages, blip, force_submit=True)
            )

        # The mock client should have been called with messages including the submit hint
        call_kwargs = mock_client.messages.stream.call_args
        sent_messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        assert any("Submit" in str(m.get("content", "")) for m in sent_messages)

    @pytest.mark.asyncio
    async def test_unknown_tool_yields_error(self):
        first_call_events = make_tool_use_events("tool_3", "unknown_tool", {})
        second_call_events = make_text_events("Sorry about that.")

        mock_client = _make_mock_client(first_call_events, second_call_events)

        with patch("app.claude_client._get_client", return_value=mock_client):
            blip = BlipSubmission()
            messages = [{"role": "user", "content": "test"}]
            chunks = await collect_chunks(get_claude_response(messages, blip))

        # Unknown tool should still allow the loop to continue
        # and the tool result in messages should contain the error
        tool_result_msg = messages[-1]  # Last appended message
        assert tool_result_msg["role"] == "user"
        tool_content = tool_result_msg["content"][0]["content"]
        assert "Unknown tool" in tool_content
