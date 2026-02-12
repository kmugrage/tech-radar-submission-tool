"""Tests for the FastAPI WebSocket endpoint."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from starlette.testclient import TestClient

from app.main import app, sessions, WELCOME_MESSAGE


# ---------------------------------------------------------------------------
# Mock async generator for get_claude_response
# ---------------------------------------------------------------------------

async def _fake_claude_simple(messages, blip, force_submit=False):
    """Yields a simple text response."""
    yield {"type": "text_delta", "text": "Mock response"}
    yield {"type": "done"}


async def _fake_claude_with_extraction(messages, blip, force_submit=False):
    """Yields a tool result (extract) then text."""
    blip.name = "Docker"
    yield {
        "type": "tool_result",
        "tool_name": "extract_blip_data",
        "data": {"status": "ok", "completeness_score": 10, "quality_score": 5,
                 "missing_fields": ["ring"], "ring_gaps": []},
    }
    yield {"type": "text_delta", "text": "Got it — Docker."}
    yield {"type": "done"}


async def _fake_claude_submit(messages, blip, force_submit=False):
    """Yields a submit summary."""
    yield {"type": "text_delta", "text": "Submission recorded."}
    yield {"type": "done"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_sessions():
    sessions.clear()
    yield
    sessions.clear()


@pytest.fixture(autouse=True)
def _mock_startup():
    """Prevent startup from fetching real radar history."""
    with patch("app.main.load_history", return_value=[]):
        yield


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_root_serves_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "html" in response.text.lower()


def test_websocket_sends_welcome_on_connect(client):
    with patch("app.main.get_claude_response", side_effect=_fake_claude_simple):
        with client.websocket_connect("/ws/test-session-1") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "assistant_message"
            assert msg["content"] == WELCOME_MESSAGE


def test_websocket_sends_quality_update_on_connect(client):
    with patch("app.main.get_claude_response", side_effect=_fake_claude_simple):
        with client.websocket_connect("/ws/test-session-1") as ws:
            _welcome = ws.receive_json()  # welcome
            quality = ws.receive_json()  # quality update
            assert quality["type"] == "quality_update"
            assert quality["completeness"] == 0
            assert quality["quality"] == 0


def test_websocket_message_action(client):
    with patch("app.main.get_claude_response", side_effect=_fake_claude_simple):
        with client.websocket_connect("/ws/test-session-1") as ws:
            _welcome = ws.receive_json()
            _quality = ws.receive_json()

            ws.send_json({"action": "message", "message": "hello"})

            # Should get assistant_chunk(s), then quality_update, then assistant_done
            chunk = ws.receive_json()
            assert chunk["type"] == "assistant_chunk"
            assert chunk["content"] == "Mock response"

            done = ws.receive_json()
            assert done["type"] == "assistant_done"


def test_websocket_empty_message_ignored(client):
    """Empty message should not trigger a response."""
    with patch("app.main.get_claude_response", side_effect=_fake_claude_simple) as mock_resp:
        with client.websocket_connect("/ws/test-session-1") as ws:
            _welcome = ws.receive_json()
            _quality = ws.receive_json()

            ws.send_json({"action": "message", "message": ""})

            # Send a real message to verify the connection is still alive
            ws.send_json({"action": "message", "message": "real message"})
            chunk = ws.receive_json()
            assert chunk["type"] == "assistant_chunk"

            # get_claude_response should only have been called once (for "real message")
            assert mock_resp.call_count == 1


def test_websocket_reset_action(client):
    with patch("app.main.get_claude_response", side_effect=_fake_claude_simple):
        with client.websocket_connect("/ws/test-session-1") as ws:
            _welcome = ws.receive_json()
            _quality = ws.receive_json()

            ws.send_json({"action": "reset"})

            # Should get a new welcome message
            new_welcome = ws.receive_json()
            assert new_welcome["type"] == "assistant_message"
            assert new_welcome["content"] == WELCOME_MESSAGE

            # And a fresh quality update
            quality = ws.receive_json()
            assert quality["type"] == "quality_update"
            assert quality["completeness"] == 0


def test_websocket_quality_updates_after_extraction(client):
    with patch("app.main.get_claude_response", side_effect=_fake_claude_with_extraction):
        with client.websocket_connect("/ws/test-session-1") as ws:
            _welcome = ws.receive_json()
            _initial_quality = ws.receive_json()

            ws.send_json({"action": "message", "message": "Docker"})

            # After extraction, there should be a quality_update before the text
            messages = []
            for _ in range(10):
                try:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] == "assistant_done":
                        break
                except Exception:
                    break

            types = [m["type"] for m in messages]
            assert "quality_update" in types


def test_websocket_submit_action(client):
    with patch("app.main.get_claude_response", side_effect=_fake_claude_submit), \
         patch("app.main.save_submission", return_value={"id": "sub-123", "name": "Docker"}):
        with client.websocket_connect("/ws/test-session-1") as ws:
            _welcome = ws.receive_json()
            _quality = ws.receive_json()

            ws.send_json({"action": "submit", "message": ""})

            # Collect all messages until we see submission_complete
            messages = []
            for _ in range(10):
                try:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] == "submission_complete":
                        break
                except Exception:
                    break

            types = [m["type"] for m in messages]
            assert "submission_complete" in types

            submit_msg = next(m for m in messages if m["type"] == "submission_complete")
            assert submit_msg["submission_id"] == "sub-123"


def test_websocket_double_submit_prevented(client):
    with patch("app.main.get_claude_response", side_effect=_fake_claude_submit), \
         patch("app.main.save_submission", return_value={"id": "sub-123", "name": "Docker"}) as mock_save:
        with client.websocket_connect("/ws/test-session-1") as ws:
            _welcome = ws.receive_json()
            _quality = ws.receive_json()

            # First submit
            ws.send_json({"action": "submit", "message": ""})
            messages = []
            for _ in range(10):
                try:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] in ("submission_complete", "assistant_done"):
                        break
                except Exception:
                    break

            # Drain any remaining messages from first submit
            try:
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] == "submission_complete":
                        break
            except Exception:
                pass

            assert any(m["type"] == "submission_complete" for m in messages)

            # Second submit — should NOT produce another submission_complete
            ws.send_json({"action": "submit", "message": ""})
            second_messages = []
            for _ in range(10):
                try:
                    msg = ws.receive_json()
                    second_messages.append(msg)
                    if msg["type"] == "assistant_done":
                        break
                except Exception:
                    break

            assert not any(m["type"] == "submission_complete" for m in second_messages)
            # save_submission should only have been called once
            assert mock_save.call_count == 1
