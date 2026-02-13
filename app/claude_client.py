"""Anthropic Claude API integration with tool-use for data extraction."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import anthropic

from app.config import ANTHROPIC_API_KEY, MODEL_NAME
from app.models import BlipSubmission, HistoricalBlip
from app.prompts import build_system_prompt
from app.quality import calculate_scores, get_missing_fields, get_ring_gaps
from app.radar_history import find_matching_blips

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

EXTRACT_BLIP_TOOL: dict[str, Any] = {
    "name": "extract_blip_data",
    "description": (
        "Extract structured blip submission data from the conversation. "
        "Call this tool whenever the user provides substantive information "
        "about their blip, or when they request to submit."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": ["string", "null"]},
            "quadrant": {
                "type": ["string", "null"],
                "enum": [
                    "Techniques",
                    "Tools",
                    "Platforms",
                    "Languages & Frameworks",
                    None,
                ],
            },
            "ring": {
                "type": ["string", "null"],
                "enum": ["Adopt", "Trial", "Assess", "Hold", None],
            },
            "description": {"type": ["string", "null"]},
            "client_references": {
                "type": ["array", "null"],
                "items": {"type": "string"},
            },
            "submitter_name": {"type": ["string", "null"]},
            "submitter_contact": {"type": ["string", "null"]},
            "why_now": {"type": ["string", "null"]},
            "alternatives_considered": {
                "type": ["array", "null"],
                "items": {"type": "string"},
            },
            "strengths": {
                "type": ["array", "null"],
                "items": {"type": "string"},
            },
            "weaknesses": {
                "type": ["array", "null"],
                "items": {"type": "string"},
            },
            "is_resubmission": {"type": ["boolean", "null"]},
            "resubmission_rationale": {
                "type": ["string", "null"],
                "enum": [
                    "refresh write-up",
                    "still important",
                    "ring change",
                    None,
                ],
            },
        },
        "required": [
            "name",
            "quadrant",
            "ring",
            "description",
            "client_references",
            "submitter_name",
            "submitter_contact",
            "why_now",
            "alternatives_considered",
            "strengths",
            "weaknesses",
        ],
        "additionalProperties": False,
    },
}

CHECK_HISTORY_TOOL: dict[str, Any] = {
    "name": "check_radar_history",
    "description": (
        "Check if a technology has appeared in previous Technology Radar "
        "editions. Call this as soon as the user mentions the name of the "
        "technology they want to submit."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The technology name to look up.",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TOOLS = [EXTRACT_BLIP_TOOL, CHECK_HISTORY_TOOL]

# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _build_system(blip: BlipSubmission) -> str:
    """Build the system prompt with the current blip state."""
    completeness, quality = calculate_scores(blip)
    missing = get_missing_fields(blip)
    ring_gaps = get_ring_gaps(blip)
    state_json = blip.model_dump_json(exclude_none=True, indent=2)
    return build_system_prompt(state_json, completeness, quality, missing, ring_gaps)


def _handle_check_history(name: str) -> dict:
    """Execute the check_radar_history tool and return the result."""
    matches = find_matching_blips(name)
    if not matches:
        return {"found": False, "appearances": []}
    return {
        "found": True,
        "appearances": [
            {"volume": m.volume, "ring": m.ring, "quadrant": m.quadrant}
            for m in matches
        ],
    }


def _handle_extract_blip(data: dict, blip: BlipSubmission) -> dict:
    """Merge extracted data into the blip and return a status dict."""
    # Validate through Pydantic so strings like "Trial" are coerced to enums
    validated = BlipSubmission.model_validate(data)
    for key in data:
        value = getattr(validated, key, None)
        if value is not None and hasattr(blip, key):
            setattr(blip, key, value)

    completeness, quality = calculate_scores(blip)
    blip.completeness_score = completeness
    blip.quality_score = quality

    return {
        "status": "ok",
        "completeness_score": completeness,
        "quality_score": quality,
        "missing_fields": get_missing_fields(blip),
        "ring_gaps": get_ring_gaps(blip),
    }


# ---------------------------------------------------------------------------
# Streaming response generator
# ---------------------------------------------------------------------------


async def get_claude_response(
    messages: list[dict],
    blip: BlipSubmission,
    force_submit: bool = False,
) -> AsyncIterator[dict]:
    """Stream Claude's response, handling tool use.

    Yields dicts with one of these shapes:
        {"type": "text_delta", "text": str}
        {"type": "tool_result", "tool_name": str, "data": dict}
        {"type": "done"}
    """
    client = _get_client()
    system = _build_system(blip)

    if force_submit:
        # Append a hint that the user wants to submit now
        submit_hint = {
            "role": "user",
            "content": (
                "[SYSTEM: The user has clicked the Submit button. Call the "
                "extract_blip_data tool with all information gathered so far, "
                "then provide a final summary of the submission including the "
                "quality score and suggestions for future improvement.]"
            ),
        }
        messages = messages + [submit_hint]

    # We may need to loop if Claude calls tools
    while True:
        collected_text = ""
        tool_uses: list[dict] = []

        async with client.messages.stream(
            model=MODEL_NAME,
            max_tokens=2048,
            system=system,
            messages=messages,
            tools=TOOLS,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    if hasattr(event.content_block, "type"):
                        if event.content_block.type == "tool_use":
                            tool_uses.append(
                                {
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "input_json": "",
                                }
                            )
                elif event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        collected_text += event.delta.text
                        yield {"type": "text_delta", "text": event.delta.text}
                    elif hasattr(event.delta, "partial_json"):
                        if tool_uses:
                            tool_uses[-1]["input_json"] += event.delta.partial_json

        # If no tool calls, we're done
        if not tool_uses:
            yield {"type": "done"}
            return

        # Process tool calls
        # First, build the assistant message with all content blocks
        assistant_content: list[dict] = []
        if collected_text:
            assistant_content.append({"type": "text", "text": collected_text})
        for tu in tool_uses:
            try:
                tool_input = json.loads(tu["input_json"]) if tu["input_json"] else {}
            except json.JSONDecodeError:
                tool_input = {}
            assistant_content.append(
                {
                    "type": "tool_use",
                    "id": tu["id"],
                    "name": tu["name"],
                    "input": tool_input,
                }
            )

        messages.append({"role": "assistant", "content": assistant_content})

        # Build tool results
        tool_results = []
        for tu in tool_uses:
            try:
                tool_input = json.loads(tu["input_json"]) if tu["input_json"] else {}
            except json.JSONDecodeError:
                tool_input = {}

            if tu["name"] == "check_radar_history":
                result = _handle_check_history(tool_input.get("name", ""))
                yield {
                    "type": "tool_result",
                    "tool_name": "check_radar_history",
                    "data": result,
                }
            elif tu["name"] == "extract_blip_data":
                result = _handle_extract_blip(tool_input, blip)
                yield {
                    "type": "tool_result",
                    "tool_name": "extract_blip_data",
                    "data": result,
                }
            else:
                result = {"error": f"Unknown tool: {tu['name']}"}

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": json.dumps(result),
                }
            )

        messages.append({"role": "user", "content": tool_results})

        # Rebuild system prompt with updated blip state
        system = _build_system(blip)

        # Loop to get Claude's follow-up response after tool results
