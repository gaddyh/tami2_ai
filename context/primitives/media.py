from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel

@dataclass
class MediaInfo:
    url: Optional[str]            # meta endpoint: https://graph.facebook.com/v16.0/{media_id}
    mime_type: Optional[str]
    caption: Optional[str]
    sha256: Optional[str]
    media_id: Optional[str]
    download_url: Optional[str] = None   # <-- NEW: short-lived direct URL


class Media(BaseModel):
    mimetype: str
    filename: Optional[str] = None
    data: str