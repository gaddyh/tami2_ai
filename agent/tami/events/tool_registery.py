# notes_agent/tools.py
from agent.linear_flow.tools import ToolRegistry, ToolSpec
from agent.linear_flow.tools import build_tools_reference
from pydantic import BaseModel
from typing import Literal, Optional, Union
from models.base_item import ItemStatus
from models.event_item import EventItem
from agent.tami.events.tools import (
    process_event_tool,
    get_items_tool,
    GetItemsQuery,
    get_candidates_recipient_info,
)

class GetCandidatesRecipientInfoArgs(BaseModel):
    name: Optional[str] = None
    name_hint: Optional[str] = None

# start simple prompt, a few tools only
tools = ToolRegistry(
    tools={
        "process_event": ToolSpec(
            fn=process_event_tool,
            args_model=EventItem,
            description="Create, update or delete an event.",
        ),
        "get_items": ToolSpec(
            fn=get_items_tool,
            args_model=GetItemsQuery,
            description="Get items.",
        ),
        "get_candidates_recipient_info": ToolSpec(
            fn=get_candidates_recipient_info,
            args_model=GetCandidatesRecipientInfoArgs,
            description="Find candidate WhatsApp recipients by name or hint.",
        ),
    }
)

tools_reference = build_tools_reference(tools)
#print("Tools reference:\n", tools_reference)