"""Input sanitization to prevent prompt injection attacks."""

from __future__ import annotations

import re

# Maximum lengths for various input types
MAX_MESSAGE_LENGTH = 10000
MAX_NAME_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 5000
MAX_SHORT_FIELD_LENGTH = 500
MAX_LIST_ITEMS = 20
MAX_LIST_ITEM_LENGTH = 500

# Patterns that could be used for prompt injection
INJECTION_PATTERNS = [
    # System/instruction boundary markers
    r"(?i)\b(end\s+)?(system\s+)?(prompt|instruction|context)\b",
    r"(?i)\b(new|ignore|override|forget|disregard)\s+(all\s+)?(instructions?|rules?|prompts?|everything)\b",
    r"(?i)\b(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\b",
    r"(?i)\bignore\s+(all\s+)?(previous|above|prior|the\s+above)\b",
    # Role/persona manipulation (role markers that could confuse message parsing)
    r"(?i)^(assistant|system|user)\s*:",
    # XML/markdown that could confuse parsing
    r"<\s*/?system\s*>",
    r"<\s*/?instruction\s*>",
    r"<\s*/?prompt\s*>",
    r"<\s*/?\s*user\s*>",
    # Additional jailbreak patterns
    r"(?i)\bDAN\s+(mode|jailbreak)\b",
    r"(?i)\b(forget|disregard)\s+(everything|all)",
]

# Compiled patterns for efficiency
_COMPILED_PATTERNS = [re.compile(p) for p in INJECTION_PATTERNS]


def sanitize_text(text: str, max_length: int = MAX_SHORT_FIELD_LENGTH) -> str:
    """Sanitize text input to prevent prompt injection.

    - Truncates to max_length
    - Removes null bytes and other control characters
    - Flags but does not remove potential injection patterns (logged for review)
    """
    if not text:
        return text

    # Truncate to max length
    text = text[:max_length]

    # Remove null bytes and most control characters (keep newlines, tabs)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # Normalize excessive whitespace (but preserve intentional formatting)
    text = re.sub(r'[ \t]{10,}', '    ', text)  # Collapse long horizontal whitespace
    text = re.sub(r'\n{5,}', '\n\n\n', text)  # Limit consecutive newlines

    return text.strip()


def contains_injection_pattern(text: str) -> bool:
    """Check if text contains potential prompt injection patterns.

    This is for logging/monitoring purposes - we don't block the input,
    but we can flag it for review.
    """
    if not text:
        return False

    for pattern in _COMPILED_PATTERNS:
        if pattern.search(text):
            return True
    return False


def sanitize_user_message(message: str) -> str:
    """Sanitize a user chat message."""
    return sanitize_text(message, MAX_MESSAGE_LENGTH)


def sanitize_blip_name(name: str) -> str:
    """Sanitize a blip/technology name."""
    return sanitize_text(name, MAX_NAME_LENGTH)


def sanitize_description(description: str) -> str:
    """Sanitize a blip description."""
    return sanitize_text(description, MAX_DESCRIPTION_LENGTH)


def sanitize_short_field(value: str) -> str:
    """Sanitize short text fields (why_now, contact, etc.)."""
    return sanitize_text(value, MAX_SHORT_FIELD_LENGTH)


def sanitize_list_field(items: list[str] | None) -> list[str] | None:
    """Sanitize a list of strings (client_references, alternatives, etc.)."""
    if not items:
        return items

    # Limit number of items
    items = items[:MAX_LIST_ITEMS]

    # Sanitize each item
    return [sanitize_text(item, MAX_LIST_ITEM_LENGTH) for item in items]


def sanitize_external_data(text: str) -> str:
    """Sanitize data from external sources (GitHub CSVs, etc.).

    More aggressive sanitization since we don't control the source.
    """
    if not text:
        return text

    # Apply standard sanitization
    text = sanitize_text(text, MAX_SHORT_FIELD_LENGTH)

    # Escape any XML-like tags that could confuse parsing
    text = re.sub(r'<([^>]+)>', r'[\1]', text)

    # Escape common injection boundary markers
    text = re.sub(r'(?i)(end|new)\s+(system\s+)?(prompt|instruction)', r'[\1 \2\3]', text)
    text = re.sub(r'(?i)(ignore|forget|disregard)\s+(all\s+)?(previous|instructions|rules)', r'[\1 \2\3]', text)

    return text
