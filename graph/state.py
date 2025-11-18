# graph/state.py
from typing import TypedDict, Optional, List, Dict, Any

class TamiState(TypedDict, total=False):
    input_text: str
    context: Dict[str, Any]
    history: List[Dict[str, Any]]        # ← NEW: prior user/assistant messages
    messages: List[Dict[str, Any]]
    final_output: Optional[str]
    tool_calls_used: int
