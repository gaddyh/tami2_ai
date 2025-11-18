from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from pydantic import Field

class ScheduledMessage(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier (auto-generated). Do not provide.")
    user_id: Optional[str] = Field(None, description="User ID (internal use only). Do not provide.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Time the event was created. auto-generated.")

    text: str = Field(..., description="The message to send. add the sender's name to the end of the message.")
    target_time: datetime = Field(..., description="Exact date and time the message is scheduled to happen (ISO format).")
    chat_id: str = Field(..., description="The chat id, the message is for. Must start with international prefix: 972546610653 and not 0546610653")
    chat_name: str = Field(..., description="The chat name, the message is for.")