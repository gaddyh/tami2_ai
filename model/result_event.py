from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime

class ToolOutput(BaseModel):
    tool: Optional[str] = None
    message_sent: Optional[dict] = None  # or a structured model if you want
    extra: Optional[dict] = None


class ResultEvent(BaseModel):
    event_id: str
    conversation_id: str
    thread_id: str
    causation_id: str
    op_id: Optional[str] = None
    timestamp: datetime

    status: Literal["success", "failed", "noop"] = "success"
    human_summary: Optional[str] = None

    affects_state: bool = False
    state_patch: Optional[dict] = None

    outputs: Optional[ToolOutput] = None
