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

# agent/linear_flow/models.py  (or wherever LinearAgentResponse lives)

from pydantic import BaseModel, ConfigDict, model_validator
from typing import List, Optional, Dict, Any
class LinearAgentResponse(BaseModel):
    response: str
    is_followup_question: bool = Field(False, description="Set to True if the response is a followup question.")

    needs_person_resolution: Optional[bool] = Field(False, description="Set to True if the response requires person resolution.")
    person_resolution_items: Optional[List[Dict[str, Any]]] = Field(None, description="List of person resolution items if needs_person_resolution is True.")    

    model_config = ConfigDict(extra="forbid")