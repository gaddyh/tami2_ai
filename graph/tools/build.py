from typing import List, Optional, Literal
from pydantic import BaseModel

from models.task_item import TaskItem, TaskPatch, BulkTasksAction
from models.event_item import EventItem
from models.reminder_item import ReminderItem
from models.scheduled_message import ScheduledMessageItem
from models.base_item import ItemStatus
from models.task_item import TaskFocus

# ---------- Tool argument models ----------

class GetItemsArgs(BaseModel):
    """Arguments for get_items: fetch reminders/tasks/events/messages/action_items."""
    item_type: Literal["reminders", "tasks", "events", "scheduled_messages", "action_items"]
    status: ItemStatus = "open"
    focus: Optional[TaskFocus] = None
    from_date: Optional[str] = None  # ISO8601 string or YYYY-MM-DD
    to_date: Optional[str] = None    # ISO8601 string or YYYY-MM-DD

    model_config = {"extra": "forbid"}


class ProcessEventArgs(BaseModel):
    """Arguments for process_event: operate on a single event."""
    event: EventItem


class ProcessEventsArgs(BaseModel):
    """Arguments for process_events: bulk operation on multiple events."""
    events: List[EventItem]


class ProcessTaskArgs(BaseModel):
    """Arguments for process_task: operate on a single task."""
    task: TaskItem


class ProcessReminderArgs(BaseModel):
    """Arguments for process_reminder: operate on a single reminder."""
    reminder: ReminderItem


class ProcessScheduledMessageArgs(BaseModel):
    """Arguments for process_scheduled_message: operate on a single scheduled message."""
    message: ScheduledMessageItem


class WebSearchArgs(BaseModel):
    """Arguments for web_search tool."""
    query: str


# ---------- Tool registry ----------

TOOL_MODELS = {
    # Events
    "process_event": (
        ProcessEventArgs,
        "Create, update or delete a single calendar event.",
    ),
    "process_events": (
        ProcessEventsArgs,
        "Bulk create or update multiple calendar events.",
    ),

    # Tasks
    "process_task": (
        ProcessTaskArgs,
        "Create or update a single task item.",
    ),
    "process_tasks": (
        BulkTasksAction,   # flat args: command, item_ids, patch, etc.
        "Bulk update or delete multiple tasks.",
    ),

    # Reminders
    "process_reminder": (
        ProcessReminderArgs,
        "Create, update or delete a reminder.",
    ),

    # Scheduled messages
    "process_scheduled_message": (
        ProcessScheduledMessageArgs,
        "Create, update or delete a scheduled WhatsApp message.",
    ),

    # Items listing
    "get_items": (
        GetItemsArgs,
        "Fetch reminders, tasks, events, scheduled messages or action items for the user.",
    ),

    # Web search
    "web_search": (
        WebSearchArgs,
        "Perform a Tavily web search and return summarized results with metrics & spans.",
    ),
}


def build_tools():
    tools = []
    for name, (model, description) in TOOL_MODELS.items():
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    # Pydantic v2:
                    "parameters": model.model_json_schema(),
                    # If you're still on Pydantic v1, use:
                    # "parameters": model.schema(),
                    "strict": False,
                },
            }
        )
    return tools

TOOL_IMPLS = {
}
TOOLS = build_tools()
