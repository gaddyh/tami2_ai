from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class MediaItem(BaseModel):
    type: Literal["image", "audio", "file"]
    url: str
    mime: Optional[str] = None
    size: Optional[int] = None


class ReplyTo(BaseModel):
    id: str
    text: Optional[str] = None


class ChatInfo(BaseModel):
    chat_id: str
    is_group: bool
    participants: List[str] = []
    user_is_sender: bool


class SenderInfo(BaseModel):
    id: str
    display: Optional[str] = None
    role: Literal["user", "system", "agent"]


class TransportInfo(BaseModel):
    provider: str
    message_id: Optional[str] = None
    reply_to_id: Optional[str] = None
    buttons: List[dict] = []
    reactions: List[dict] = []


class ContentInfo(BaseModel):
    text: Optional[str] = ""
    media: List[MediaItem] = []
    reply_to: Optional[ReplyTo] = None


class SemanticsInfo(BaseModel):
    intent_hint: Optional[str] = None
    lang_guess: Optional[str] = None
    priority: Optional[Literal["normal", "high"]] = "normal"
    confidentiality: Optional[Literal["public", "private"]] = "public"


class PolicyHints(BaseModel):
    tool_budget: int = 1
    allow_search: bool = False
    confirmation_required: bool = False


class SystemContext(BaseModel):
    tz: str
    now_iso: datetime
    state_line: Optional[str] = None
    last_system_prompt_ids: List[str] = []

from pydantic import BaseModel
from typing import Optional

class AccountInfo(BaseModel):
    # Your WhatsApp account that RECEIVED this message (or sent it, for echoes)
    account_id: str                     # your internal id for the connected WA account
    provider_user_id: str               # WA JID / phone (e.g., "9725XXXXXX@c.us")
    display: Optional[str] = None       # "Gaddy", "Tami Biz", etc.
    provider_instance_id: Optional[str] = None  # GreenAPI instance id
    business: Optional[bool] = None     # WA Business account?

class InputEvent(BaseModel):
    event_id: str
    conversation_id: str
    thread_id: Optional[str] = None
    causation_id: Optional[str] = None
    source: Literal["user", "transport", "trigger", "background"]
    timestamp: datetime

    account: AccountInfo
    chat: ChatInfo
    sender: SenderInfo
    transport: TransportInfo
    content: ContentInfo
    semantics: Optional[SemanticsInfo] = SemanticsInfo()
    policy_hints: PolicyHints = PolicyHints()
    system_context: SystemContext
