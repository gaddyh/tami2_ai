# state.py
from typing import TypedDict, List, Dict, Any, Optional

class LinearAgentState(TypedDict, total=False):
    input_text: str
    context: Dict[str, Any]
    tool_results: List[Dict[str, Any]]
    status: Optional[str]

    llm_messages: List[Dict[str, Any]]
    messages: List[Dict[str, Any]]
    
    # Planner LLM output
    actions: List[Dict[str, Any]]
    followup_message: Optional[str]

    # Responder LLM output
    response: Optional[str]
    is_followup_question: Optional[bool]

    target_agent: Optional[str]
    needs_person_resolution: Optional[bool]
    person_resolution_items: Optional[List[Dict[str, Any]]]
    