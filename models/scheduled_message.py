from pydantic import BaseModel, Field
from typing import Optional, Literal, Annotated
from models.event_item import Recurrence

class ScheduledMessageItem(BaseModel):
    """
    Represents a scheduled WhatsApp message that Tami-Comms will create,
    update, or delete. Includes the resolved sender/recipient details and
    the absolute scheduled time.
    """

    item_id: Optional[str] = Field(
        default=None,
        description=(
            "Unique ID of the scheduled message. "
            "Required for update/delete. "
            "Ignored for create (system will generate one)."
        ),
    )

    command: Literal["create", "update", "delete"] = Field(
        description="Operation to perform: create a new scheduled message, update an existing one, or delete it."
    )

    item_type: Literal["message"] = Field(
        default="message",
        description="Must always be 'message'. Reserved for future extension."
    )

    message: str = Field(
        description="The actual message text that will be sent via WhatsApp."
    )

    scheduled_time: str = Field(
        description=(
            "Absolute datetime when the message should be sent "
            "(ISO8601 with timezone offset). Must be ≥ current_datetime."
        )
    )

    sender_name: Optional[str] = Field(
        default=None,
        description="Human-readable name of the sender."
    )

    recipient_name: Optional[str] = Field(
        default=None,
        description=(
            "Name of the final chosen recipient. "
            "For self-reminders, should be identical to sender_name."
        )
    )

    recipient_chat_id: Annotated[
        str,
        Field(
            pattern=r".+@(c|g)\.us",
            description=(
                "WhatsApp JID of the recipient: phone@c.us for private chats "
                "or chatid@g.us for groups. MUST match the WhatsApp pattern. "
                "Do NOT use 'SELF' here — set sender_name == recipient_name instead."
            ),
        ),
    ]

    status: Optional[str] = Field(
        default=None,
        description=(
            "Optional status of the scheduled message (e.g. 'open', 'sent', "
            "'canceled'). The backend may populate this."
        ),
    )

    recurrence: Optional[Recurrence] = Field(
        default=None,
        description=(
            "Optional recurrence rule. Example: "
            "{'freq': 'daily', 'interval': 1} or "
            "{'freq':'weekly','interval':1,'by_day':['SU']}."
        ),
    )

