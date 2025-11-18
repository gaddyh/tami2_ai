from enum import Enum
from pydantic import BaseModel
from typing import Optional

class EffortFocus(str, Enum):
    UNDERSTANDING_INTENT = "understanding_intent"
    CHOOSING_TOOL = "choosing_tool"
    INTERPRETING_TOOL_RESULTS = "interpreting_tool_results"
    COMPLEX_REASONING = "complex_reasoning"
    FORMATTING_OUTPUT = "formatting_output"

class TamiOutput(BaseModel):
    final_output: str
    trace_id: Optional[str] = None
    #thought_focus: EffortFocus
    #thought_summary: str  # 1 short sentence in Hebrew, no step-by-step reasoning
