from models.base_item import BaseActionItem
from typing import Literal, Optional
from models.event_item import Recurrence

class ReminderItem(BaseActionItem):
    item_type: Literal["reminder"] = "reminder"
    datetime: str  # when the reminder should trigger
    recurrence: Optional[Recurrence] = None
