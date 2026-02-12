from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Import length limits from sanitization module
from app.sanitization import (
    MAX_NAME_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_SHORT_FIELD_LENGTH,
    MAX_LIST_ITEMS,
    MAX_LIST_ITEM_LENGTH,
    sanitize_text,
)


class Quadrant(str, Enum):
    TECHNIQUES = "Techniques"
    TOOLS = "Tools"
    PLATFORMS = "Platforms"
    LANGUAGES_FRAMEWORKS = "Languages & Frameworks"


class Ring(str, Enum):
    ADOPT = "Adopt"
    TRIAL = "Trial"
    ASSESS = "Assess"
    HOLD = "Hold"


class HistoricalBlip(BaseModel):
    name: str = Field(max_length=MAX_NAME_LENGTH)
    ring: str = Field(max_length=50)
    quadrant: str = Field(max_length=50)
    volume: str = Field(max_length=100)


class BlipSubmission(BaseModel):
    name: Optional[str] = Field(default=None, max_length=MAX_NAME_LENGTH)
    quadrant: Optional[Quadrant] = None
    ring: Optional[Ring] = None
    description: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    client_references: Optional[list[str]] = Field(
        default=None,
        description="Client engagements where this technology was used",
        max_length=MAX_LIST_ITEMS,
    )
    submitter_name: Optional[str] = Field(default=None, max_length=MAX_SHORT_FIELD_LENGTH)
    submitter_contact: Optional[str] = Field(default=None, max_length=MAX_SHORT_FIELD_LENGTH)
    why_now: Optional[str] = Field(
        default=None,
        description="What has changed that makes this relevant now",
        max_length=MAX_SHORT_FIELD_LENGTH,
    )
    alternatives_considered: Optional[list[str]] = Field(
        default=None, max_length=MAX_LIST_ITEMS
    )
    strengths: Optional[list[str]] = Field(default=None, max_length=MAX_LIST_ITEMS)
    weaknesses: Optional[list[str]] = Field(default=None, max_length=MAX_LIST_ITEMS)

    # Resubmission fields
    is_resubmission: bool = False
    previous_appearances: Optional[list[HistoricalBlip]] = None
    resubmission_rationale: Optional[str] = Field(
        default=None,
        description="One of: 'refresh write-up', 'still important', 'ring change'",
        max_length=MAX_SHORT_FIELD_LENGTH,
    )

    # Scores (computed)
    completeness_score: Optional[float] = None
    quality_score: Optional[float] = None

    @field_validator('name', 'submitter_name', 'submitter_contact', 'why_now', 'resubmission_rationale', mode='before')
    @classmethod
    def sanitize_short_fields(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return sanitize_text(v, MAX_SHORT_FIELD_LENGTH)

    @field_validator('description', mode='before')
    @classmethod
    def sanitize_description(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return sanitize_text(v, MAX_DESCRIPTION_LENGTH)

    @field_validator('client_references', 'alternatives_considered', 'strengths', 'weaknesses', mode='before')
    @classmethod
    def sanitize_list_fields(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        # Limit items and sanitize each
        return [sanitize_text(item, MAX_LIST_ITEM_LENGTH) for item in v[:MAX_LIST_ITEMS]]
