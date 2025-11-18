
from pydantic import BaseModel
from datetime import datetime

class ReminderBase(BaseModel):
    text: str
    time: datetime

class ReminderUpdate(ReminderBase):
    id: str

class ReminderDelete(ReminderBase):
    id: str

class Reminder(ReminderBase):
    id: str
    user_id: str