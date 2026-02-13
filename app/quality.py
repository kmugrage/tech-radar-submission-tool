from __future__ import annotations

from app.models import BlipSubmission

# Weights for completeness scoring (sum = 100)
FIELD_WEIGHTS: dict[str, int] = {
    "name": 10,
    "quadrant": 5,
    "ring": 5,
    "description": 25,
    "submitter_name": 5,
    "submitter_contact": 5,
    "why_now": 15,
    "client_references": 10,
    "alternatives_considered": 10,
    "strengths": 5,
    "weaknesses": 5,
}

# Ring-specific evidence checks — each ring totals exactly 40 bonus points
# so the quality denominator (100 + 40 = 140) is the same for every ring.
RING_EVIDENCE: dict[str, list[dict]] = {
    "Adopt": [
        {"field": "client_references", "min_count": 2, "bonus": 20,
         "gap": "Adopt suggests at least 2 client references"},
        {"field": "description", "required": True, "bonus": 10,
         "gap": "A description is essential for an Adopt recommendation"},
        {"field": "strengths", "required": True, "bonus": 10,
         "gap": "List strengths to justify Adopt placement"},
    ],
    "Trial": [
        {"field": "client_references", "min_count": 1, "bonus": 15,
         "gap": "Trial blips benefit from at least 1 client reference"},
        {"field": "description", "required": True, "bonus": 10,
         "gap": "A description is essential for a Trial recommendation"},
        {"field": "alternatives_considered", "required": True, "bonus": 15,
         "gap": "Describe alternatives you considered before recommending Trial"},
    ],
    "Assess": [
        {"field": "description", "required": True, "bonus": 20,
         "gap": "A thorough description is critical for an Assess recommendation"},
        {"field": "why_now", "required": True, "bonus": 20,
         "gap": "Explain why this technology is worth assessing now"},
    ],
    "Hold": [
        {"field": "description", "required": True, "bonus": 10,
         "gap": "Describe why teams should hold on this technology"},
        {"field": "weaknesses", "required": True, "bonus": 15,
         "gap": "Describe weaknesses that justify the Hold recommendation"},
        {"field": "alternatives_considered", "required": True, "bonus": 15,
         "gap": "Suggest alternatives teams should consider instead"},
    ],
}

# Total bonus points per ring (must be equal for fair scoring)
_BONUS_TOTAL = 40


def _field_is_filled(value: object) -> bool:
    """Check if a field has a meaningful value."""
    if value is None:
        return False
    if isinstance(value, str):
        return len(value.strip()) > 0
    if isinstance(value, list):
        return len(value) > 0
    return True


def _ring_bonus(blip: BlipSubmission) -> float:
    """Calculate ring-specific evidence bonus (0–40)."""
    if blip.ring is None:
        return 0.0
    ring_key = getattr(blip.ring, "value", blip.ring)
    checks = RING_EVIDENCE.get(ring_key, [])
    earned = 0.0
    for check in checks:
        value = getattr(blip, check["field"], None)
        if "min_count" in check:
            if isinstance(value, list) and len(value) >= check["min_count"]:
                earned += check["bonus"]
        elif check.get("required"):
            if _field_is_filled(value):
                earned += check["bonus"]
    return earned


def calculate_completeness(blip: BlipSubmission) -> float:
    """Calculate completeness score (0-100) as weighted % of filled fields."""
    earned = 0.0
    for field, weight in FIELD_WEIGHTS.items():
        value = getattr(blip, field, None)
        if _field_is_filled(value):
            earned += weight
    return earned


def calculate_quality(blip: BlipSubmission) -> float:
    """Calculate quality score (0-100).

    Quality = (completeness + ring_bonus) / 140 * 100.
    The denominator is always 140 (100 base + 40 ring bonus) regardless of
    which ring is chosen, so scoring is fair across all rings.
    """
    completeness = calculate_completeness(blip)
    bonus = _ring_bonus(blip)
    return (completeness + bonus) / (100 + _BONUS_TOTAL) * 100


def calculate_scores(blip: BlipSubmission) -> tuple[float, float]:
    """Return (completeness, quality) scores."""
    return calculate_completeness(blip), calculate_quality(blip)


def get_missing_fields(blip: BlipSubmission) -> list[str]:
    """Return a list of field names that are still empty."""
    missing = []
    for field in FIELD_WEIGHTS:
        value = getattr(blip, field, None)
        if not _field_is_filled(value):
            missing.append(field)
    return missing


def get_ring_gaps(blip: BlipSubmission) -> list[str]:
    """Return ring-specific evidence gaps for the current ring."""
    if blip.ring is None:
        return []
    ring_key = getattr(blip.ring, "value", blip.ring)
    checks = RING_EVIDENCE.get(ring_key, [])
    gaps = []
    for check in checks:
        value = getattr(blip, check["field"], None)
        if "min_count" in check:
            if not isinstance(value, list) or len(value) < check["min_count"]:
                gaps.append(check["gap"])
        elif check.get("required"):
            if not _field_is_filled(value):
                gaps.append(check["gap"])
    return gaps
