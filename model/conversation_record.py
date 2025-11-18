from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ConversationParticipant(BaseModel):
    id: str
    display: Optional[str] = None
    role: Literal["user", "system", "agent"] = "user"


class ThreadIndexItem(BaseModel):
    thread_id: str
    title: Optional[str] = None
    status: Literal["active", "completed", "archived", "pending"] = "active"
    last_updated_at: datetime
    last_user_turn_at: Optional[datetime] = None
    context_tags: List[str] = []


class ConversationPrefs(BaseModel):
    preferred_lang: Optional[str] = None
    tz: Optional[str] = None
    quiet_hours: Optional[str] = None         # e.g., "21:00-08:00"
    confirm_style: Optional[Literal["buttons", "text"]] = "buttons"


class ConversationRecord(BaseModel):
    conversation_id: str

    created_at: datetime
    updated_at: datetime
    last_active_at: datetime

    participants: List[ConversationParticipant] = []
    thread_index: List[ThreadIndexItem] = []

    # Short textual roll-up of recent history (LLM/rules-generated)
    summary: Optional[str] = None
    # Token-efficient long-tail compression (optional)
    compressed_tail: Optional[str] = None

    # Pointers useful for deterministic replies across threads
    last_system_prompt_ids: List[str] = []

    # Recent committed side-effects (for idempotency/debug)
    recent_ops: List[str] = []

    # Lightweight metrics/flags (keep it small)
    stats: Dict[str, Any] = Field(default_factory=dict)  # e.g., {"msg_count_7d": 42}

    # User/session preferences that affect routing/policy
    prefs: ConversationPrefs = ConversationPrefs()
