from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from models.base_item import BaseActionItem

TaskFocus = Literal["none", "working", "next", "waiting", "scheduled"]

class TaskItem(BaseActionItem):
    item_type: Literal["task"] = "task"

    # When is it due (parsed elsewhere to aware datetime)
    due: Optional[str] = None

    # Focus / attention state (AI+UX)
    focus: TaskFocus = "none"

    parent_id: Optional[str] = None
    context: Optional[str] = None
    location: Optional[str] = None

    waiting_on: Optional[str] = None   # free-text or contact alias
    blocked_by: Optional[str] = None   # why it’s blocked

    notes: Optional[str] = None
    list_id: Optional[str] = None
    position: Optional[int] = None     # ordering within list

    model_config = {"extra": "forbid"}


# Only the fields you actually allow to change in bulk
class TaskPatch(BaseModel):
    due: Optional[str] = None
    completed: Optional[bool] = None
    parent_id: Optional[str] = None
    context: Optional[str] = None
    location: Optional[str] = None
    waiting_on: Optional[str] = None
    blocked_by: Optional[str] = None
    notes: Optional[str] = None
    list_id: Optional[str] = None
    position: Optional[int] = None

    model_config = {"extra": "forbid"}

class BulkTasksAction(BaseModel):
    command: Literal["bulk_update", "bulk_delete"] = Field(..., description="Bulk operation to perform")
    item_ids: List[str] = Field(..., min_length=1, description="Explicit task IDs to affect")  # use min_length
    patch: Optional[TaskPatch] = Field(default=None, description="Fields to patch when command=bulk_update")
    dry_run: bool = Field(default=False, description="If true, do not mutate; just report what would change")
    limit: int = Field(default=100, gt=0, le=1000, description="Safety cap on number of items to change in one call")

    model_config = {"extra": "forbid"}
