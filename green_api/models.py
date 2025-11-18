# ledger_models.py
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Any, List, Dict, Literal
from datetime import datetime

class LedgerSpan(BaseModel):
    """Atomic extracted span with optional normalization in extra."""
    value: str = Field(..., min_length=1)
    extra: Optional[Dict[str, Any]] = None

class MessageLedger(BaseModel):
    """ONE consolidated ledger per message (lean version: only ids/actions are kept)."""
    # Provenance
    instance_id: Optional[str] = None
    chat_id: str
    message_id: Optional[str] = None
    provider: Optional[str] = None                      # e.g., "green_api"
    direction: Optional[Literal["inbound","outbound"]] = None
    sender: Optional[str] = None                        # phone/user id if known

    # Original text & time
    original_message: str
    ts: float                                           # raw provider ts if you use it
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())

    # Extracted (lean)
    ids: List[LedgerSpan] = Field(default_factory=list)       # product / packaging / destination / delivery_type / customer / quantity
    actions: List[LedgerSpan] = Field(default_factory=list)   # e.g., {"value":"order","extra":{"subtype":"product_order","orders_count":N}}

    # Optional model metadata
    confidence: Optional[float] = None
    normalized: Optional[Dict[str, Any]] = None

    model_config = {
        "extra": "ignore",
        "populate_by_name": True,
        "validate_assignment": True,
        "use_enum_values": True,
    }
