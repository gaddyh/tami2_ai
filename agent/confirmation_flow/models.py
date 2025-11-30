# agent/confirmation_flow/models.py (for example)
from typing import Any, Dict, Optional, Literal
from pydantic import BaseModel

class ConfirmationInitialResult(BaseModel):
    status: Literal["done", "ask_user", "cannot_resolve"]
    question: Optional[str] = None
    selected_item: Optional[Dict[str, Any]] = None
