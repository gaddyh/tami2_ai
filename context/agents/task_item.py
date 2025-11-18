from context.agents.base_item import BaseActionItem
from typing import Literal, Optional, List, Dict, Any
from pydantic import Field
from pydantic import BaseModel

class TaskItem(BaseActionItem):
    item_type: Literal["task"] = "task"
    due: Optional[str] = None            # ISO8601 due date
    completed: Optional[bool] = False
    parent_id: Optional[str] = None      # If set, this task is a subtask of another
    context: Optional[str] = None
    location: Optional[str] = None
    waiting_on: Optional[str] = None
    blocked_by: Optional[str] = None
    notes: Optional[str] = None
    list_id: Optional[str] = None
    position: Optional[int] = None

# ✱ Add below TaskItem (new args schema for the bulk tool)
class BulkTasksAction(BaseModel):
    command: Literal["bulk_update", "bulk_delete"] = Field(..., description="Bulk operation to perform")
    item_ids: List[str] = Field(..., min_items=1, description="Explicit task IDs to affect")
    patch: Optional[Dict[str, Any]] = Field(default=None, description="Fields to patch when command=bulk_update")
    dry_run: bool = Field(default=False, description="If true, do not mutate; just report what would change")
    limit: int = Field(default=100, gt=0, le=1000, description="Safety cap on number of items to change in one call")
