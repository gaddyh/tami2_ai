
from dataclasses import dataclass

from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional


class LastTaskEntry(BaseModel):
    index: int          # 1-based index shown to the user
    item_id: str        # stable DB id
    title: str          # short label for debugging / optional use


class LastTasksListing(BaseModel):
    generated_at: datetime
    items: List[LastTaskEntry]

@dataclass
class AppCtx:
    user_id: str
    user_name: str
    thread_id: str
    default_tz: str
    current_datetime: str
    last_tasks_listing: Optional[LastTasksListing] = None