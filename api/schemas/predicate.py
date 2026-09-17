"""Structured output contract for closed-set model selection."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class CandidateSelectionStatus(str, Enum):
    SELECT = "SELECT"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    NO_MATCH = "NO_MATCH"


class CandidateSelection(BaseModel):
    """The model may return only option identifiers supplied by the server."""

    status: CandidateSelectionStatus
    selected_candidate_id: Optional[str] = None
    alternative_candidate_ids: List[str] = Field(default_factory=list, max_length=4)
    question_text: Optional[str] = Field(default=None, max_length=1000)
    reasoning_points: List[str] = Field(default_factory=list, max_length=6)
    applied_gir_keys: List[str] = Field(default_factory=list, max_length=10)
    cited_chapter_notes: List[str] = Field(default_factory=list, max_length=10)

