#models/user.py
from __future__ import annotations
from pydantic import BaseModel, Field, validator
from typing import Dict, List, Literal, Optional, Union
from datetime import datetime, timezone
from models.app_context import LastTasksListing

class GreenApiInstance(BaseModel):
    token: Optional[str] = None
    id: Optional[int] = None

# --- Small typed value objects used by the prompt ---
class EventSummary(BaseModel):
    title: str
    start_time: datetime
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    start_human: Optional[str] = None  # optional preformatted

class TaskSummary(BaseModel):
    title: str
    completed_at: Optional[datetime] = None
    completed_human: Optional[str] = None  # optional preformatted

class RecentChat(BaseModel):
    chat_id: str
    chat_name: str
    last_message_snippet: Optional[str] = None
    last_message_time: Optional[datetime] = None

# --- Runtime: add fields your Jinja block reads directly ---
class UserRuntime(BaseModel):
    contacts: Dict[str, Dict[str, Optional[str]]] = Field(default_factory=dict)
    # Keep original spelling to avoid migration breakage
    prefered_contacts: Dict[str, Dict[str, Optional[str]]] = Field(default_factory=dict)

    # Data surfaced to the prompt
    next_events: List[EventSummary] = Field(default_factory=list)
    recent_completed_tasks: List[TaskSummary] = Field(default_factory=list)
    recent_chats: List[RecentChat] = Field(default_factory=list)
    open_tasks_count: Optional[int] = None

    greenApiInstance: Optional[GreenApiInstance] = Field(default_factory=GreenApiInstance)

    last_tasks_listing: Optional[LastTasksListing] = None

# --- Config: flags mirrored in the prompt (keep preferences for raw access) ---
class UserConfig(BaseModel): 
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Time the user was created. auto-generated."
    )
    status: Literal["trial", "active", "inactive"] = "trial"
    name: str
    timezone: str
    language: str
    preferences: dict = Field(default_factory=dict)

    # Mirrors of common toggles
    digest_enabled: bool = False
    digest_time: str = "07:30"
    auto_notify_enabled: bool = False
    web_search_enabled: bool = True

class User(BaseModel):
    user_id: str
    config: UserConfig
    runtime: UserRuntime

# TODO: Redis
userContextDict: Dict[str, User] = {}
