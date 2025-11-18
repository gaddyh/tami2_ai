from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime

class ThreadEntities(BaseModel):
    datetime: Optional[datetime] = None
    location: Optional[str] = None
    people: List[str] = []
    task_ids: List[str] = []
    reminder_ids: List[str] = []
    event_ids: List[str] = []


class ThreadRecord(BaseModel):
    thread_id: str
    conversation_id: str
    title: Optional[str] = None
    status: Literal["active", "completed", "archived", "pending"] = "active"
    created_at: datetime
    updated_at: datetime

    entities: ThreadEntities = ThreadEntities()
    last_user_turn_at: Optional[datetime] = None
    last_system_prompt_ids: List[str] = []
    related_ops: List[str] = []
    summary: Optional[str] = None
    context_tags: List[str] = []
