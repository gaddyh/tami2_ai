from pydantic import BaseModel, Field
from typing import Optional, Literal, Annotated

# models/scheduled_message_item.py
from typing import Optional, Literal, Annotated
from pydantic import BaseModel, Field

class ScheduledMessageItem(BaseModel):
    item_id: Optional[str] = None
    command: Literal["create", "update", "delete"]
    item_type: Literal["message"] = "message"
    message: str
    scheduled_time: str  # ISO8601
    sender_name: str
    recipient_name: str
    recipient_chat_id: Annotated[str, Field(pattern=r".+@(c|g)\.us")]
    status: Optional[str] = None
