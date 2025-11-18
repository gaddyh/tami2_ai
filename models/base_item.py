from typing import Optional, Literal
from pydantic import BaseModel


ItemStatus = Literal["open", "completed", "deleted"]

class BaseActionItem(BaseModel):
    # Optional for create, required for update/delete (enforced in tool logic)
    item_id: Optional[str] = None

    user_id: Optional[str] = None
    command: Literal["create", "update", "delete"]
    item_type: Literal["reminder", "task", "event"]  # discriminator

    title: str = ""          # always required semantically
    description: Optional[str] = None

    # Lifecycle status – shared across item types if you want
    status: ItemStatus = "open"

    # Idempotency key
    op_id: Optional[str] = None

    model_config = {"extra": "forbid"}
