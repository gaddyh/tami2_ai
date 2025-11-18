# graph/state.py
from typing import TypedDict, Optional, List, Dict, Any
MAX_MESSAGES_FOR_MODEL = 60

class TamiState(TypedDict, total=False):
    input_text: str
    context: Dict[str, Any]
    messages: List[Dict[str, Any]]
    final_output: Optional[str]
    tool_calls_used: int
