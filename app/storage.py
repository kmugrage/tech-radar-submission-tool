"""JSON file storage for blip submissions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

from app.config import DATA_DIR, SUBMISSIONS_FILE
from app.models import BlipSubmission

# Lock file for concurrent access protection
_LOCK_FILE = SUBMISSIONS_FILE.with_suffix(".lock")


def _ensure_file() -> None:
    """Create the submissions file if it doesn't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SUBMISSIONS_FILE.exists():
        SUBMISSIONS_FILE.write_text("[]", encoding="utf-8")


def load_submissions() -> list[dict]:
    """Load all submissions from disk."""
    _ensure_file()
    content = SUBMISSIONS_FILE.read_text(encoding="utf-8")
    return json.loads(content)


def save_submission(blip: BlipSubmission, session_id: str) -> dict:
    """Append a blip submission to the JSON file.

    Uses file locking to prevent race conditions with concurrent writes.
    Returns the saved record (with id and timestamp).
    """
    _ensure_file()

    record = blip.model_dump(exclude_none=True)
    record["id"] = str(uuid.uuid4())
    record["session_id"] = session_id
    record["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Use file lock to prevent concurrent write race conditions
    lock = FileLock(_LOCK_FILE, timeout=10)
    with lock:
        # Read current submissions inside the lock
        content = SUBMISSIONS_FILE.read_text(encoding="utf-8")
        submissions = json.loads(content)

        submissions.append(record)

        # Atomic write via temp file
        tmp = SUBMISSIONS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(submissions, indent=2), encoding="utf-8")
        tmp.replace(SUBMISSIONS_FILE)

    return record
