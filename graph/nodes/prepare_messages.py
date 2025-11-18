from graph.state import TamiState
from graph.prompt import TAMI_SYSTEM_PROMPT
from graph.state import MAX_MESSAGES_FOR_MODEL
import json

def parse_tami_json(content: str) -> dict:
    """
    Safely parse LLM JSON output with protection against formatting issues.
    """
    if not content:
        return {"tool_plan": [], "should_return_to_llm": False, "assistant_message": ""}

    content = content.strip()

    # Some models wrap JSON in backticks
    if content.startswith("```"):
        content = content.strip("`")
        # Remove potential prefix like ```json
        content = content.replace("json", "", 1).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        print("⚠️ Failed to decode JSON:", e)
        print("Content was:", content)
        # Graceful fallback
        return {
            "tool_plan": [],
            "should_return_to_llm": False,
            "assistant_message": content  # fallback to raw string
        }

def prepare_messages_node(state: TamiState) -> TamiState:
    """
    Build the OpenAI chat messages array for this run.
    """
    user_text = state.get("input_text", "") or ""
    context = state.get("context", {}) or {}

    system_msg = {
        "role": "system",
        "content": TAMI_SYSTEM_PROMPT.strip(),
    }

    context_msg = {
        "role": "system",
        "content": f"Context (JSON): {context!r}",
    }

    user_msg = {
        "role": "user",
        "content": user_text,
    }

    # 1) Take previous messages, but *drop* old system/context
    # Assume previous state["messages"] already included them, so filter by role
    prev = state.get("messages", []) or []
    history = [m for m in prev if m.get("role") != "system"]

    # 2) Trim history to last N
    if len(history) > MAX_MESSAGES_FOR_MODEL:
        history = history[-MAX_MESSAGES_FOR_MODEL:]

    # 3) Add the new user message to history
    history.append(user_msg)
    if len(history) > MAX_MESSAGES_FOR_MODEL:
        history = history[-MAX_MESSAGES_FOR_MODEL:]

    # 4) Build the final messages list for the model (and persist it)
    state["messages"] = [system_msg, context_msg, *history]
    state["tool_calls_used"] = 0

    return state
