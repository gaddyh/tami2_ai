from dataclasses import dataclass
from typing import Optional
from context.primitives.media import MediaInfo
from context.primitives.location import LocationInfo
from context.primitives.sender import SharedContactInfo, ReferralInfo

@dataclass
class ButtonReplyInfo:
    payload: str
    text: str

from dataclasses import dataclass
from typing import Optional

@dataclass
class ReplyContextInfo:
    quoted_message_id: Optional[str]
    quoted_sender_phone: Optional[str]

    # Enriched fields (optional, filled if found in MESSAGE_INDEX)
    original_type: Optional[str] = None       # "text", "image", "video", etc.
    original_text: Optional[str] = None       # text.body if original was text
    original_media_id: Optional[str] = None   # media id (if original was media)
    original_mime_type: Optional[str] = None  # e.g. "image/jpeg"
    original_caption: Optional[str] = None    # caption if any
    original_media_url: Optional[str] = None  # resolved download URL (short-lived!)

@dataclass
class ListReplyInfo:
    payload: str
    title: str
    description: Optional[str] = None

@dataclass
class ContentInfo:
    type: str
    text: Optional[str] = None
    media: Optional[MediaInfo] = None
    location: Optional[LocationInfo] = None
    button_reply: Optional[ButtonReplyInfo] = None
    list_reply: Optional[ListReplyInfo] = None
    reply_context: Optional[ReplyContextInfo] = None
    contact: Optional[SharedContactInfo] = None
    referral: Optional[ReferralInfo] = None