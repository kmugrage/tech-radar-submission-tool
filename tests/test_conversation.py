"""Tests for ConversationSession state management."""

from app.conversation import ConversationSession
from app.models import BlipSubmission, Ring


def test_init_creates_empty_state():
    session = ConversationSession("test-1")
    assert session.session_id == "test-1"
    assert session.messages == []
    assert isinstance(session.blip, BlipSubmission)
    assert session.blip.name is None
    assert session.submitted is False


def test_add_user_message():
    session = ConversationSession("test-1")
    session.add_user_message("hello")
    assert session.messages == [{"role": "user", "content": "hello"}]


def test_add_assistant_message_string():
    session = ConversationSession("test-1")
    session.add_assistant_message("I can help with that")
    assert session.messages == [{"role": "assistant", "content": "I can help with that"}]


def test_add_assistant_message_list():
    session = ConversationSession("test-1")
    content = [
        {"type": "text", "text": "Let me check"},
        {"type": "tool_use", "id": "t1", "name": "check_radar_history", "input": {}},
    ]
    session.add_assistant_message(content)
    assert session.messages[0]["role"] == "assistant"
    assert session.messages[0]["content"] is content


def test_add_tool_results():
    session = ConversationSession("test-1")
    results = [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]
    session.add_tool_results(results)
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] is results


def test_message_ordering():
    session = ConversationSession("test-1")
    session.add_user_message("first")
    session.add_assistant_message("second")
    session.add_user_message("third")
    assert [m["role"] for m in session.messages] == ["user", "assistant", "user"]
    assert [m["content"] for m in session.messages] == ["first", "second", "third"]


def test_reset_clears_state():
    session = ConversationSession("test-1")
    session.add_user_message("hello")
    session.blip.name = "Terraform"
    session.blip.ring = Ring.ADOPT
    session.submitted = True
    original_blip = session.blip

    session.reset()

    assert session.messages == []
    assert session.blip.name is None
    assert session.submitted is False
    assert session.blip is not original_blip  # Must be a new instance
