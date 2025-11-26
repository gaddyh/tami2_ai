from typing import Literal, Optional, Union
from pydantic import BaseModel
from models.base_item import ItemStatus
from models.task_item import TaskFocus

class GetItemsQuery(BaseModel):
    item_type: Literal["task"]
    status: Union[ItemStatus, Literal["all"]] = "open"
    focus: Optional[TaskFocus] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: int = 100

    model_config = {
        "extra": "forbid",
    }
