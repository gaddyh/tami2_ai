# notes_agent/models.py
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from agent.linear_flow.tools import ToolCallPlan

class LinearAgentPlan(BaseModel):
    """
    Structured plan the runtime expects from the LLM for a single step.
    """

    actions: List[ToolCallPlan] = Field(
        default_factory=list,
        description=(
            "Ordered list of tool calls the runtime should execute now. "
            "Each item has 'tool' (string tool name) and 'args' (object with arguments). "
            "If no tools are needed, return an empty list."
        ),
    )

    followup_message: Optional[str] = Field(
        default=None,
        description=(
            "Short Hebrew clarification question for the user. "
            "If this is not null, the runtime will INTERRUPT and ask this question "
            "instead of executing tools. Use only when more information is required."
        ),
    )

    model_config = {"extra": "forbid"}

# linear_flow/models.py
from pydantic import BaseModel, Field

class LinearAgentResponse(BaseModel):
    """
    Final response the runtime expects from the responder LLM.
    """
    response: str = Field(
        ...,
        description="Hebrew final user-facing message.",
    )

    model_config = {"extra": "forbid"}
