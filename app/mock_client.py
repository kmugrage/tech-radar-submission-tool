"""Mock Claude client for dev mode — no API key required.

Simulates the coaching conversation by parsing user messages with simple
keyword matching and generating plausible follow-up questions. Also calls
the extract_blip_data and check_radar_history tool handlers so the quality
meter and duplicate detection work exactly as they do in production.
"""

from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator

from app.models import BlipSubmission, Quadrant, Ring
from app.quality import calculate_scores, get_missing_fields, get_ring_gaps
from app.radar_history import find_matching_blips

# Maps user-facing ring/quadrant strings to enum values
_RING_MAP = {k.lower(): v for v in Ring for k in (v.value, v.name)}
_QUAD_MAP = {
    "techniques": Quadrant.TECHNIQUES,
    "tools": Quadrant.TOOLS,
    "platforms": Quadrant.PLATFORMS,
    "languages & frameworks": Quadrant.LANGUAGES_FRAMEWORKS,
    "languages and frameworks": Quadrant.LANGUAGES_FRAMEWORKS,
    "languages-and-frameworks": Quadrant.LANGUAGES_FRAMEWORKS,
    "frameworks": Quadrant.LANGUAGES_FRAMEWORKS,
    "languages": Quadrant.LANGUAGES_FRAMEWORKS,
}

# Tracks which field the mock just asked about, keyed by session (blip id).
# When the user's next message doesn't match any keyword extraction, we
# assign their answer to this field.
_pending_field: dict[int, str] = {}


def _extract_fields_from_text(text: str, blip: BlipSubmission) -> dict:
    """Do a rough keyword extraction from the user message.

    This is intentionally simple — just enough to drive the quality meter
    during dev testing.
    """
    lower = text.lower()
    changes: dict = {}

    # Ring detection
    for keyword, ring in _RING_MAP.items():
        if keyword in lower:
            changes["ring"] = ring
            break

    # Quadrant detection
    for keyword, quad in _QUAD_MAP.items():
        if keyword in lower:
            changes["quadrant"] = quad
            break

    # Name detection
    if blip.name is None:
        quoted = re.search(r'"([^"]+)"', text) or re.search(r"'([^']+)'", text)
        if quoted:
            changes["name"] = quoted.group(1)
        else:
            # Strip filler phrases, then use whatever's left as the name.
            filler = re.sub(
                r"(?i)^(i'?d? ?like to submit|i want to submit|let'?s do|"
                r"how about|submit|what about|i'?m submitting)\s*",
                "",
                text,
            ).strip().rstrip(".,!?")
            if filler:
                changes["name"] = filler

    # Client reference detection
    if "client" in lower or "production" in lower or "project" in lower:
        refs = blip.client_references or []
        if text[:120] not in refs:
            refs = refs + [text[:120]]
            changes["client_references"] = refs

    # Description: if it's a longer message and we don't have one yet
    if len(text) > 80 and blip.description is None:
        changes["description"] = text

    # Submitter name
    if blip.submitter_name is None:
        name_match = re.search(
            r"(?:my name is|i'm|I am)\s+(\w+(?:\s+\w+)?)", text, re.IGNORECASE
        )
        if name_match:
            changes["submitter_name"] = name_match.group(1)

    # Contact
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if email_match:
        changes["submitter_contact"] = email_match.group(0)

    # --- Pending field fallback ---
    # If the mock previously asked about a specific field and the keyword
    # extraction above didn't fill it, assign the user's text as the answer.
    blip_id = id(blip)
    pending = _pending_field.pop(blip_id, None)
    if pending and pending not in changes:
        current_val = getattr(blip, pending, None)
        if current_val is None:
            # Fields that are lists get the text as a single-item list
            if pending in ("alternatives_considered", "strengths", "weaknesses",
                           "client_references"):
                existing = getattr(blip, pending) or []
                changes[pending] = existing + [text.strip()]
            elif pending == "submitter_name":
                changes["submitter_name"] = text.strip()
            elif pending == "submitter_contact":
                changes["submitter_contact"] = text.strip()
            else:
                changes[pending] = text.strip()

    return changes


def _pick_response(blip: BlipSubmission, user_text: str, is_submit: bool) -> tuple[str, str | None]:
    """Generate an appropriate mock coaching response.

    Returns (response_text, pending_field_name). The pending_field_name is
    the blip field this response is asking about, so the next user message
    can be assigned to it as a fallback.
    """
    if is_submit:
        c, q = calculate_scores(blip)
        missing = get_missing_fields(blip)
        gaps = get_ring_gaps(blip)
        parts = [
            f"Thanks for your submission! Here's a summary:\n\n"
            f"**{blip.name or 'Unnamed'}** — "
            f"{blip.ring.value if blip.ring else 'No ring'} / "
            f"{blip.quadrant.value if blip.quadrant else 'No quadrant'}\n\n"
            f"Completeness: {c:.0f}%\n"
            f"Quality: {q:.0f}%\n"
        ]
        if gaps:
            parts.append("\nTo strengthen this submission in the future:\n")
            for gap in gaps:
                parts.append(f"  - {gap}\n")
        if missing:
            parts.append(f"\nStill missing: {', '.join(missing)}")
        return "".join(parts), None

    missing = get_missing_fields(blip)
    gaps = get_ring_gaps(blip)

    # Determine what to ask about next
    if blip.name is None:
        return (
            "Thanks for starting a submission! What technology or technique "
            "would you like to submit? Please give me the name.",
            "name",
        )

    if blip.ring is None:
        return (
            f"Great — **{blip.name}** is an interesting choice. "
            "Which ring would you recommend?\n\n"
            "- **Adopt**: We believe the industry should strongly consider this\n"
            "- **Trial**: Worth pursuing — we've seen it work in production\n"
            "- **Assess**: Worth exploring to understand how it will affect you\n"
            "- **Hold**: Proceed with caution",
            "ring",
        )

    if blip.quadrant is None:
        return (
            f"Got it — {blip.name} for the **{blip.ring.value}** ring. "
            "Which quadrant does this belong in?\n\n"
            "- **Techniques** (processes, architectural patterns)\n"
            "- **Tools** (software applications and utilities)\n"
            "- **Platforms** (cloud, infrastructure, runtime environments)\n"
            "- **Languages & Frameworks**",
            "quadrant",
        )

    if blip.description is None:
        return (
            f"Now for the most important part — the description. "
            f"For a **{blip.ring.value}** recommendation, I'd suggest writing "
            f"at least a paragraph that explains:\n\n"
            f"- What {blip.name} is and what problem it solves\n"
            f"- Your experience using it (client projects, outcomes)\n"
            f"- Why you're recommending this ring placement\n\n"
            f"Go ahead — the more detail, the better the submission!",
            "description",
        )

    # Ring-specific coaching
    if blip.ring in (Ring.ADOPT, Ring.TRIAL):
        refs = blip.client_references or []
        needed = 2 if blip.ring == Ring.ADOPT else 1
        if len(refs) < needed:
            return (
                f"For a **{blip.ring.value}** recommendation, I'll need at least "
                f"{needed} client reference{'s' if needed > 1 else ''} where "
                f"{blip.name} was used in production. Can you describe a client "
                f"project where you used it? What was the outcome?",
                "client_references",
            )

    if not blip.alternatives_considered and any(
        "alternatives" in g.lower() for g in gaps
    ):
        return (
            f"What alternatives to {blip.name} did you consider? "
            f"Knowing what you compared it against helps the TAB "
            f"understand your recommendation.",
            "alternatives_considered",
        )

    if blip.weaknesses is None and blip.ring in (Ring.ADOPT, Ring.HOLD):
        return (
            f"What are the known weaknesses or limitations of {blip.name}? "
            f"Being upfront about drawbacks actually strengthens your submission.",
            "weaknesses",
        )

    if blip.why_now is None:
        return (
            f"Why is now the right time to feature {blip.name} on the radar? "
            f"What's changed recently that makes it relevant?",
            "why_now",
        )

    if blip.submitter_name is None:
        return (
            "We're getting close! Before you submit, can you tell me your "
            "name so the TAB can follow up if needed?",
            "submitter_name",
        )

    if blip.submitter_contact is None:
        return (
            "And what's the best way to reach you? (email or Slack handle)",
            "submitter_contact",
        )

    # Everything is filled — encourage submission
    c, q = calculate_scores(blip)
    return (
        f"Your submission is looking solid! Completeness: {c:.0f}%, "
        f"Quality: {q:.0f}%.\n\n"
        f"Feel free to add more detail to any section, or click "
        f"**Submit Blip** when you're ready.",
        None,
    )


async def get_mock_response(
    messages: list[dict],
    blip: BlipSubmission,
    force_submit: bool = False,
) -> AsyncIterator[dict]:
    """Mock replacement for get_claude_response.

    Parses the user's message, updates blip fields, checks radar history,
    and generates coaching responses — all without calling the Claude API.
    """
    # Find the latest user message
    user_text = ""
    for msg in reversed(messages):
        if msg["role"] == "user" and isinstance(msg["content"], str):
            user_text = msg["content"]
            break

    # Extract structured fields from user text
    changes = _extract_fields_from_text(user_text, blip)

    # Check radar history if we just learned the name
    if "name" in changes and blip.name is None:
        name = changes["name"]
        matches = find_matching_blips(name)
        if matches:
            yield {
                "type": "tool_result",
                "tool_name": "check_radar_history",
                "data": {
                    "found": True,
                    "appearances": [
                        {"volume": m.volume, "ring": m.ring, "quadrant": m.quadrant}
                        for m in matches
                    ],
                },
            }

    # Apply extracted fields to blip
    if changes:
        for key, value in changes.items():
            if hasattr(blip, key):
                setattr(blip, key, value)

        completeness, quality = calculate_scores(blip)
        blip.completeness_score = completeness
        blip.quality_score = quality

        yield {
            "type": "tool_result",
            "tool_name": "extract_blip_data",
            "data": {
                "status": "ok",
                "completeness_score": completeness,
                "quality_score": quality,
                "missing_fields": get_missing_fields(blip),
                "ring_gaps": get_ring_gaps(blip),
            },
        }

    # Generate response text
    response, pending = _pick_response(blip, user_text, force_submit)

    # Record which field this response is asking about
    blip_id = id(blip)
    if pending:
        _pending_field[blip_id] = pending
    else:
        _pending_field.pop(blip_id, None)

    # Add duplicate detection info if applicable
    if "name" in changes and blip.name:
        matches = find_matching_blips(blip.name)
        if matches:
            vols = ", ".join(
                f"**{m.volume}** ({m.ring} ring)" for m in matches[:3]
            )
            more = f" and {len(matches) - 3} more" if len(matches) > 3 else ""
            dup_msg = (
                f"I noticed **{blip.name}** has appeared in previous radar "
                f"editions: {vols}{more}.\n\n"
                f"Since this is a resubmission, could you tell me your reason?\n\n"
                f"1. **The write-up needs a refresh** — same ring, but the "
                f"landscape has changed\n"
                f"2. **Still important, should appear again** — it remains "
                f"highly relevant\n"
                f"3. **The ring should change** — you'd like to move it to a "
                f"different ring\n"
                f"4. **Cancel this submission**\n\n"
            )
            response = dup_msg + response

    # Stream the response word-by-word for a realistic feel
    words = response.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == 0 else " " + word
        yield {"type": "text_delta", "text": chunk}
        await asyncio.sleep(0.02)  # Simulate typing delay

    yield {"type": "done"}
