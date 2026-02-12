from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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
    name: str
    ring: str
    quadrant: str
    volume: str


class BlipSubmission(BaseModel):
    name: Optional[str] = None
    quadrant: Optional[Quadrant] = None
    ring: Optional[Ring] = None
    description: Optional[str] = None
    client_references: Optional[list[str]] = Field(
        default=None,
        description="Client engagements where this technology was used",
    )
    submitter_name: Optional[str] = None
    submitter_contact: Optional[str] = None
    why_now: Optional[str] = Field(
        default=None,
        description="What has changed that makes this relevant now",
    )
    alternatives_considered: Optional[list[str]] = None
    strengths: Optional[list[str]] = None
    weaknesses: Optional[list[str]] = None

    # Resubmission fields
    is_resubmission: bool = False
    previous_appearances: Optional[list[HistoricalBlip]] = None
    resubmission_rationale: Optional[str] = Field(
        default=None,
        description="One of: 'refresh write-up', 'still important', 'ring change'",
    )

    # Scores (computed)
    completeness_score: Optional[float] = None
    quality_score: Optional[float] = None
