"""FastAPI application with WebSocket endpoint for blip submission conversations."""

from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import DEV_MODE
from app.conversation import ConversationSession
from app.quality import calculate_scores, get_missing_fields, get_ring_gaps
from app.radar_history import load_history
from app.sanitization import sanitize_user_message, contains_injection_pattern
from app.storage import save_submission, load_submissions

if DEV_MODE:
    from app.mock_client import get_mock_response as get_claude_response
else:
    from app.claude_client import get_claude_response

logger = logging.getLogger(__name__)

# Session configuration
MAX_SESSIONS = 1000  # Maximum number of concurrent sessions
SESSION_TTL_SECONDS = 3600  # Sessions expire after 1 hour of inactivity

# Valid session ID pattern: UUID format or alphanumeric with hyphens (max 64 chars)
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")


def _validate_session_id(session_id: str) -> bool:
    """Validate that a session ID is safe and well-formed."""
    return bool(SESSION_ID_PATTERN.match(session_id))


class SessionStore:
    """Thread-safe session store with TTL and max size limits."""

    def __init__(self, max_sessions: int = MAX_SESSIONS, ttl_seconds: int = SESSION_TTL_SECONDS):
        self._sessions: OrderedDict[str, tuple[ConversationSession, float]] = OrderedDict()
        self._max_sessions = max_sessions
        self._ttl_seconds = ttl_seconds

    def get(self, session_id: str) -> ConversationSession | None:
        """Get a session, updating its last-accessed time."""
        if session_id not in self._sessions:
            return None
        session, _ = self._sessions[session_id]
        # Update access time and move to end (most recently used)
        self._sessions[session_id] = (session, time.time())
        self._sessions.move_to_end(session_id)
        return session

    def create(self, session_id: str) -> ConversationSession:
        """Create a new session, evicting old ones if necessary."""
        self._cleanup_expired()
        # Evict oldest sessions if at capacity
        while len(self._sessions) >= self._max_sessions:
            oldest_key = next(iter(self._sessions))
            del self._sessions[oldest_key]
            logger.info("Evicted session %s due to capacity limit", oldest_key)

        session = ConversationSession(session_id)
        self._sessions[session_id] = (session, time.time())
        return session

    def get_or_create(self, session_id: str) -> ConversationSession:
        """Get existing session or create a new one."""
        session = self.get(session_id)
        if session is None:
            session = self.create(session_id)
        return session

    def _cleanup_expired(self) -> None:
        """Remove sessions that have exceeded TTL."""
        now = time.time()
        expired = [
            sid for sid, (_, last_access) in self._sessions.items()
            if now - last_access > self._ttl_seconds
        ]
        for sid in expired:
            del self._sessions[sid]
            logger.info("Expired session %s due to inactivity", sid)

    def clear(self) -> None:
        """Clear all sessions (for testing)."""
        self._sessions.clear()

    def __contains__(self, session_id: str) -> bool:
        return session_id in self._sessions


# Global session store
sessions = SessionStore()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    try:
        count = len(load_history())
        logger.info("Loaded %d historical radar blips", count)
    except Exception:
        logger.warning(
            "Could not load radar history - duplicate detection will be unavailable",
            exc_info=True,
        )
    yield
    # Shutdown (nothing to clean up currently)


app = FastAPI(title="TW Tech Radar Blip Submission Tool", lifespan=lifespan)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_DEV_BANNER = (
    "[DEV MODE - using mock responses, no API key needed]\n\n"
    if DEV_MODE
    else ""
)

WELCOME_MESSAGE = (
    f"{_DEV_BANNER}"
    "Welcome to the Technology Radar blip submission tool! I'll help you "
    "craft a strong submission for the next radar edition.\n\n"
    "To get started, tell me about the technology or technique you'd like "
    "to submit. You can include as much or as little detail as you'd like - "
    "I'll ask follow-up questions to help strengthen your submission.\n\n"
    "You can click **Submit Blip** at any time to finalize your submission."
)


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    index = STATIC_DIR / "index.html"
    return HTMLResponse(index.read_text(encoding="utf-8"))


@app.get("/submissions", response_class=HTMLResponse)
async def submissions_page() -> HTMLResponse:
    page = STATIC_DIR / "submissions.html"
    return HTMLResponse(page.read_text(encoding="utf-8"))


@app.get("/api/submissions/{submission_id}")
async def get_submission(submission_id: str) -> dict:
    """Return the full detail of a single submission by ID."""
    records = load_submissions()
    for record in records:
        if record.get("id") == submission_id:
            # Omit session_id and submitter_contact from detail view
            detail_fields = {
                "id", "timestamp", "name", "quadrant", "ring",
                "submitter_name", "completeness_score", "quality_score",
                "description", "why_now", "is_resubmission", "resubmission_rationale",
                "client_references", "alternatives_considered", "strengths", "weaknesses",
                "previous_appearances",
            }
            return {k: v for k, v in record.items() if k in detail_fields}
    raise HTTPException(status_code=404, detail="Submission not found")


@app.get("/api/submissions")
async def list_submissions(
    ring: Optional[str] = None,
    quadrant: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Return a summary list of submitted blips, optionally filtered by ring or quadrant."""
    if limit > 500:
        limit = 500

    records = load_submissions()

    if ring:
        records = [r for r in records if r.get("ring", "").lower() == ring.lower()]
    if quadrant:
        records = [r for r in records if r.get("quadrant", "").lower() == quadrant.lower()]

    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    records = records[:limit]

    summary_fields = {"id", "timestamp", "name", "quadrant", "ring",
                      "submitter_name", "completeness_score", "quality_score",
                      "description"}
    result = []
    for r in records:
        item = {k: v for k, v in r.items() if k in summary_fields}
        if item.get("description") and len(item["description"]) > 200:
            item["description"] = item["description"][:197] + "..."
        result.append(item)
    return result


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    # Validate session ID format before accepting connection
    if not _validate_session_id(session_id):
        await websocket.close(code=4000, reason="Invalid session ID format")
        return

    await websocket.accept()

    session = sessions.get_or_create(session_id)

    # Send welcome
    await websocket.send_json(
        {"type": "assistant_message", "content": WELCOME_MESSAGE}
    )
    await _send_quality_update(websocket, session)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action", "message")
            raw_message = data.get("message", "").strip()

            if action == "reset":
                session.reset()
                await websocket.send_json(
                    {"type": "assistant_message", "content": WELCOME_MESSAGE}
                )
                await _send_quality_update(websocket, session)
                continue

            # Sanitize user input to prevent prompt injection
            user_message = sanitize_user_message(raw_message)

            # Log potential injection attempts (don't block, but monitor)
            if user_message and contains_injection_pattern(raw_message):
                logger.warning(
                    "Potential prompt injection detected in session %s: %s",
                    session_id,
                    raw_message[:100],
                )

            if not user_message and action != "submit":
                continue

            is_submit = action == "submit"

            if user_message:
                session.add_user_message(user_message)

            # Collect the full response for the conversation history
            full_text = ""

            async for chunk in get_claude_response(
                session.messages, session.blip, force_submit=is_submit
            ):
                if chunk["type"] == "text_delta":
                    full_text += chunk["text"]
                    await websocket.send_json(
                        {"type": "assistant_chunk", "content": chunk["text"]}
                    )

                elif chunk["type"] == "tool_result":
                    if chunk["tool_name"] == "extract_blip_data":
                        await _send_quality_update(websocket, session)

                elif chunk["type"] == "done":
                    # Record the final assistant text in conversation history
                    if full_text:
                        session.messages.append(
                            {"role": "assistant", "content": full_text}
                        )

            # Signal end of response
            await websocket.send_json({"type": "assistant_done"})

            # Handle submission
            if is_submit and not session.submitted:
                session.submitted = True
                record = save_submission(session.blip, session.session_id)
                await websocket.send_json(
                    {
                        "type": "submission_complete",
                        "quality_score": session.blip.quality_score or 0,
                        "submission_id": record["id"],
                    }
                )

    except WebSocketDisconnect:
        logger.info("Session %s disconnected", session_id)
    except Exception:
        logger.exception("Error in session %s", session_id)
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "content": "An unexpected error occurred. Please refresh and try again.",
                }
            )
        except Exception:
            pass


async def _send_quality_update(
    websocket: WebSocket, session: ConversationSession
) -> None:
    """Send current quality scores and blip state to the client."""
    completeness, quality = calculate_scores(session.blip)
    blip_data = session.blip.model_dump(exclude_none=True)
    # Remove score fields from the display data
    blip_data.pop("completeness_score", None)
    blip_data.pop("quality_score", None)

    await websocket.send_json(
        {
            "type": "quality_update",
            "completeness": completeness,
            "quality": quality,
            "blip_data": blip_data,
            "missing_fields": get_missing_fields(session.blip),
            "ring_gaps": get_ring_gaps(session.blip),
        }
    )
