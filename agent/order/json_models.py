FORMATTER_JSON_SCHEMA = {
    "name": "formatter_payload",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "customer_span": {"type": ["string", "null"]},
            "destination_span": {"type": ["string", "null"]},
            "transportation_span": {"type": ["string", "null"]},
            "notes_span": {"type": ["string", "null"]},
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "product_span": {"type": ["string", "null"]},
                        "packaging_span": {"type": ["string", "null"]},
                        "quantity_span": {"type": ["string", "null"]},
                    },
                    "required": [
                        "product_span",
                        "packaging_span",
                        "quantity_span",
                    ]
                }
            }
        },
        "required": [
            "customer_span",
            "destination_span",
            "transportation_span",
            "notes_span",
            "line_items"
        ]
    }
}

from typing import Optional, List
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    product_span: Optional[str] = Field(None)
    product_matched: Optional[str] = Field(None)
    product_id_matched: Optional[str] = Field(None)
    packaging_span: Optional[str] = Field(None)
    quantity_span: Optional[str] = Field(None)


class FormatterPayload(BaseModel):
    original_text: Optional[str] = Field(None)
    customer_span: Optional[str] = Field(None)
    customer_matched: Optional[str] = Field(None)
    customer_id: Optional[int] = Field(None)
    destination_span: Optional[str] = Field(None)
    destination_matched: Optional[str] = Field(None)
    transportation_span: Optional[str] = Field(None)
    transportation_matched: Optional[str] = Field(None)
    notes_span: Optional[str] = Field(None)
    line_items: List[LineItem]
