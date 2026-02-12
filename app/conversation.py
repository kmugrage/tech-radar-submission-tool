"""Conversation session management."""

from __future__ import annotations

from app.models import BlipSubmission


class ConversationSession:
    """Manages state for a single blip submission conversation."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.messages: list[dict] = []
        self.blip = BlipSubmission()
        self.submitted = False

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str | list[dict]) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_results(self, results: list[dict]) -> None:
        """Add tool result messages in the format Claude expects."""
        self.messages.append({"role": "user", "content": results})

    def reset(self) -> None:
        """Start a new submission within the same session."""
        self.messages.clear()
        self.blip = BlipSubmission()
        self.submitted = False
