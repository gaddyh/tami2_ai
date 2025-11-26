from typing import Dict, Any
from agent.linear_flow.tools import ToolResult
from agent.linear_flow.state import LinearAgentState

def update_context_with_tool_result(
    context: Dict[str, Any],
    tool_result: ToolResult,
    *,
    max_history: int = 10,
) -> Dict[str, Any]:
    """
    Update RUNTIME CONTEXT with a single tool_result.

    Semantics:
    - Successful calls (error is None):
        - Go into tools[tool_name].history (bounded)
        - Update tools[tool_name].latest
        - Increment meta["count"]
    - Failed calls (error is not None):
        - Do NOT touch .latest (so "latest" stays a usable snapshot)
        - Store in tools[tool_name].last_error
        - Increment meta["error_count"]
    """

    tools = context.setdefault("tools", {})

    tool_name = tool_result["tool"]
    record = {
        "args": tool_result["args"],
        "result": tool_result["result"],
        "error": tool_result["error"],
        "timestamp": tool_result["timestamp"],
    }

    tool_ns = tools.setdefault(
        tool_name,
        {
            "history": [],
            "latest": None,
            "last_error": None,
            "meta": {"count": 0, "error_count": 0},
        },
    )

    if record["error"] is None:
        # Successful call → goes into history + latest
        tool_ns["history"].insert(0, record)

        if max_history and len(tool_ns["history"]) > max_history:
            tool_ns["history"] = tool_ns["history"][:max_history]

        tool_ns["latest"] = record
        tool_ns["meta"]["count"] += 1
    else:
        # Failed call → don't break latest snapshot
        tool_ns["last_error"] = record
        tool_ns["meta"]["error_count"] = tool_ns["meta"].get("error_count", 0) + 1

    return context

from agent.linear_flow.state import LinearAgentState

def add_message(role: str, content: str, state: LinearAgentState, messages_key="messages") -> LinearAgentState:
    target_agent = state.get("target_agent")
    if not target_agent:
        # Fail fast – you REALLY don't want untagged messages floating around
        raise ValueError("add_message called without state['target_agent'] set")

    if messages_key not in ["messages", "llm_messages"]:
        raise ValueError("add_message called with invalid messages_key")

    msg = {
        "role": role,
        "content": content,
        "target_agent": target_agent,
    }

    if role == "system":
        state.setdefault("llm_messages", []).append(msg)
    else:
        state.setdefault(messages_key, []).append(msg)

    return state
