"""FastAPI application with WebSocket endpoint for blip submission conversations."""

from __future__ import annotations

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import DEV_MODE
from app.conversation import ConversationSession
from app.quality import calculate_scores, get_missing_fields, get_ring_gaps
from app.radar_history import load_history
from app.storage import save_submission

if DEV_MODE:
    from app.mock_client import get_mock_response as get_claude_response
else:
    from app.claude_client import get_claude_response

logger = logging.getLogger(__name__)

app = FastAPI(title="TW Tech Radar Blip Submission Tool")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory session store
sessions: dict[str, ConversationSession] = {}

_DEV_BANNER = (
    "[DEV MODE — using mock responses, no API key needed]\n\n"
    if DEV_MODE
    else ""
)

WELCOME_MESSAGE = (
    f"{_DEV_BANNER}"
    "Welcome to the Technology Radar blip submission tool! I'll help you "
    "craft a strong submission for the next radar edition.\n\n"
    "To get started, tell me about the technology or technique you'd like "
    "to submit. You can include as much or as little detail as you'd like — "
    "I'll ask follow-up questions to help strengthen your submission.\n\n"
    "You can click **Submit Blip** at any time to finalize your submission."
)


@app.on_event("startup")
async def startup() -> None:
    """Pre-load radar history on startup."""
    try:
        count = len(load_history())
        logger.info("Loaded %d historical radar blips", count)
    except Exception:
        logger.warning(
            "Could not load radar history — duplicate detection will be unavailable",
            exc_info=True,
        )


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    index = STATIC_DIR / "index.html"
    return HTMLResponse(index.read_text(encoding="utf-8"))


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    if session_id not in sessions:
        sessions[session_id] = ConversationSession(session_id)
    session = sessions[session_id]

    # Send welcome
    await websocket.send_json(
        {"type": "assistant_message", "content": WELCOME_MESSAGE}
    )
    await _send_quality_update(websocket, session)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action", "message")
            user_message = data.get("message", "").strip()

            if action == "reset":
                session.reset()
                await websocket.send_json(
                    {"type": "assistant_message", "content": WELCOME_MESSAGE}
                )
                await _send_quality_update(websocket, session)
                continue

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
