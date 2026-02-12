from __future__ import annotations

from app.models import BlipSubmission, Ring

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

# Ring-specific evidence requirements that add quality bonus points
RING_EVIDENCE: dict[str, dict] = {
    Ring.ADOPT: {
        "client_references": {"min_count": 2, "bonus": 20},
        "description": {"min_length": 200, "bonus": 15},
        "weaknesses": {"required": True, "bonus": 10},
    },
    Ring.TRIAL: {
        "client_references": {"min_count": 1, "bonus": 15},
        "description": {"min_length": 150, "bonus": 15},
        "alternatives_considered": {"required": True, "bonus": 10},
    },
    Ring.ASSESS: {
        "description": {"min_length": 100, "bonus": 15},
        "why_now": {"required": True, "bonus": 15},
    },
    Ring.HOLD: {
        "description": {"min_length": 100, "bonus": 15},
        "weaknesses": {"required": True, "bonus": 15},
        "alternatives_considered": {"required": True, "bonus": 10},
    },
}


def _field_is_filled(value: object) -> bool:
    """Check if a field has a meaningful value."""
    if value is None:
        return False
    if isinstance(value, str):
        return len(value.strip()) > 0
    if isinstance(value, list):
        return len(value) > 0
    return True


def calculate_completeness(blip: BlipSubmission) -> float:
    """Calculate completeness score (0-100) as weighted % of filled fields."""
    earned = 0.0
    for field, weight in FIELD_WEIGHTS.items():
        value = getattr(blip, field, None)
        if _field_is_filled(value):
            earned += weight
    return earned


def _ring_bonus(blip: BlipSubmission) -> tuple[float, float]:
    """Calculate earned and max ring-specific bonus points."""
    if blip.ring is None:
        return 0.0, 0.0

    requirements = RING_EVIDENCE.get(blip.ring, {})
    earned = 0.0
    maximum = 0.0

    for field, req in requirements.items():
        bonus = req["bonus"]
        maximum += bonus
        value = getattr(blip, field, None)

        if "min_count" in req and isinstance(value, list):
            if len(value) >= req["min_count"]:
                earned += bonus
        elif "min_length" in req and isinstance(value, str):
            if len(value) >= req["min_length"]:
                earned += bonus
        elif "required" in req and _field_is_filled(value):
            earned += bonus

    return earned, maximum


def calculate_quality(blip: BlipSubmission) -> float:
    """Calculate quality score (0-100).

    Quality = completeness scaled into the base portion, plus ring-specific
    bonus points. The result is normalized so 100 means both full
    completeness and all ring bonuses met.
    """
    completeness = calculate_completeness(blip)
    bonus_earned, bonus_max = _ring_bonus(blip)

    total_possible = 100.0 + bonus_max
    raw = completeness + bonus_earned
    if total_possible == 0:
        return 0.0
    return min(100.0, (raw / total_possible) * 100.0)


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
    """Return human-readable descriptions of unmet ring-specific evidence."""
    if blip.ring is None:
        return []

    requirements = RING_EVIDENCE.get(blip.ring, {})
    gaps = []

    for field, req in requirements.items():
        value = getattr(blip, field, None)
        label = field.replace("_", " ").title()

        if "min_count" in req:
            count = len(value) if isinstance(value, list) else 0
            needed = req["min_count"]
            if count < needed:
                gaps.append(f"{label}: need at least {needed}, have {count}")
        elif "min_length" in req:
            length = len(value) if isinstance(value, str) else 0
            needed = req["min_length"]
            if length < needed:
                gaps.append(
                    f"{label}: need at least {needed} characters, have {length}"
                )
        elif "required" in req:
            if not _field_is_filled(value):
                gaps.append(f"{label}: required for {blip.ring.value} ring")

    return gaps
