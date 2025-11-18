from dataclasses import dataclass
from typing import Any
from context.primitives.sender import SenderInfo
from context.primitives.replies_info import ContentInfo
from enum import Enum

class MessageDirection(str, Enum):
    INCOMING = "incoming"  # Someone else sent it
    OUTGOING = "outgoing"  # You sent it
    SELF = "self"          # You to yourself
    ECHO = "echo"          # You to yourself
    UNKOWN = "unknown"     # Unknown direction

@dataclass
class RawMessage:
    sender: SenderInfo
    content: ContentInfo
    chat_id: str
    direction: MessageDirection
    message_data: Any
    idempotency_key: str