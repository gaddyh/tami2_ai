from typing import List, Optional
from context.scheduled_event import ScheduledEvent
from context.runtime import ScheduledRuntime, EventStatus
from db.base import db
from datetime import datetime
from firebase_admin import firestore
from pydantic import BaseModel
from context.runtime import EventAction
from datetime import timedelta

class TriggerableScheduledEvent(BaseModel):
    event: ScheduledEvent
    runtime: ScheduledRuntime

class ScheduledEventStore:
    def __init__(self):
        self.collection = db.collection("scheduled_events")

    def save(self, event: ScheduledEvent) -> str:
        if not event.user_id:
            raise ValueError("ScheduledEvent must have user_id before saving")

        if event.id:
            doc_ref = self.collection.document(event.id)
        else:
            doc_ref = self.collection.document()
            event.id = doc_ref.id

        triggerable_event = TriggerableScheduledEvent(
            event=event, runtime=ScheduledRuntime()
        )
        triggerable_event.runtime = self.calculate_runtime(triggerable_event)
        doc_ref.set(triggerable_event.model_dump())
        return event.id

    def get(self, event_id: str) -> Optional[ScheduledEvent]:
        doc = self.collection.document(event_id).get()
        if doc.exists:
            return TriggerableScheduledEvent(**doc.to_dict()).event
        return None

    def list_all(self) -> List[ScheduledEvent]:
        return [
            TriggerableScheduledEvent(**doc.to_dict()).event
            for doc in self.collection.stream()
        ]

    def delete(self, event_id: str):
        self.collection.document(event_id).delete()

    def find_upcoming(self, from_time: datetime, to_time: datetime) -> List[ScheduledEvent]:
        query = (
            self.collection
            .where("event.target_time", ">=", from_time)
            .where("event.target_time", "<=", to_time)
        )
        return [TriggerableScheduledEvent(**doc.to_dict()).event for doc in query.stream()]

    def find_by_user(self, user_id: str) -> List[ScheduledEvent]:
        query = self.collection.where("event.user_id", "==", user_id)
        return [TriggerableScheduledEvent(**doc.to_dict()).event for doc in query.stream()]

    def load_recent(self, limit: int = 10) -> List[ScheduledEvent]:
        query = (
            self.collection
            .order_by("event.created_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [TriggerableScheduledEvent(**doc.to_dict()).event for doc in query.stream()]

    def get_with_runtime(self, event_id: str) -> Optional[TriggerableScheduledEvent]:
        doc = self.collection.document(event_id).get()
        if doc.exists:
            return TriggerableScheduledEvent(**doc.to_dict())
        return None

    def find_triggerable(self, trigger_window: datetime, limit: int = 100) -> List[TriggerableScheduledEvent]:
        query = (
            self.collection
            .where("runtime.status", "==", EventStatus.PENDING)
            .where("runtime.next_action_time", "<=", trigger_window)
            .order_by("runtime.next_action_time")
            .limit(limit)
        )
        return [TriggerableScheduledEvent(**doc.to_dict()) for doc in query.stream()]

    def update_runtime(self, event_id: str, runtime: ScheduledRuntime):
        self.collection.document(event_id).update({"runtime": runtime.model_dump()})

    def calculate_runtime(self, triggerable: TriggerableScheduledEvent):
        if triggerable.event.nudge_minutes_before:
            triggerable.runtime.next_action_time = triggerable.event.target_time - timedelta(minutes=triggerable.event.nudge_minutes_before)
            triggerable.runtime.next_action_type = EventAction.NUDGE
        else:
            triggerable.runtime.next_action_time = triggerable.event.target_time
            triggerable.runtime.next_action_type = EventAction.NOTIFY
        return triggerable.runtime