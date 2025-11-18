# models/decision.py
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum

class DecisionOutcome(str, Enum):
    ROUTE = "route"
    IGNORE = "ignore"


class TargetAgent(str, Enum):
    PERSONAL_ASSISTANT = "personal_assistant"
    MONITOR = "monitor"
    SCHEDULER = "scheduler"


class Decision(BaseModel):
    outcome: DecisionOutcome
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)
    target_agent: Optional[TargetAgent] = None
    idempotency_key_used: Optional[str] = None
    normalized_text: Optional[str] = None
