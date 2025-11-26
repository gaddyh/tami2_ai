# agent/tami/comms/tools.py
from typing import Optional
from pydantic import BaseModel

from agent.linear_flow.tools import ToolRegistry, ToolSpec, build_tools_reference

from models.scheduled_message import ScheduledMessageItem
from agent.tami.comms.tools import (
    process_scheduled_message,
    get_candidates_recipient_info,
    search_chat_history,
)

# ---- small args models for the other tools ----

class GetCandidatesRecipientInfoArgs(BaseModel):
    name: Optional[str] = None
    name_hint: Optional[str] = None


class SearchChatHistoryArgs(BaseModel):
    query: str
    limit: int = 20


tools = ToolRegistry(
    tools={
        "get_candidates_recipient_info": ToolSpec(
            fn=get_candidates_recipient_info,
            args_model=GetCandidatesRecipientInfoArgs,
            description="Find candidate WhatsApp recipients by name or hint.",
        ),
        "process_scheduled_message": ToolSpec
        (
            fn=process_scheduled_message,
            args_model=ScheduledMessageItem,
            description="Create, update or delete a scheduled WhatsApp message.",
        ),
        "search_chat_history": ToolSpec(
            fn=search_chat_history,
            args_model=SearchChatHistoryArgs,
            description="Search WhatsApp chat history for messages.",
        ),
    }
)

tools_reference = build_tools_reference(tools)
print("Tools reference:\n", tools_reference)
