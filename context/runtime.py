from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum

class EventStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    ERROR = "error"
    DELETED = "deleted"

class EventAction(str, Enum):
    NUDGE = "nudge"
    NOTIFY = "notify"
    FOLLOWUP = "followup"
    SCHEDULED_MESSAGE = "scheduled_message"

class ScheduledRuntime(BaseModel):
    status: EventStatus = EventStatus.PENDING

    next_action_time: Optional[datetime] = None
    next_action_type: Optional[EventAction] = None

    last_sent_time: Optional[datetime] = None
    last_sent_type: Optional[EventAction] = None

    last_error: Optional[str] = None