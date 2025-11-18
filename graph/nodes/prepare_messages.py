from graph.state import TamiState
from graph.prompt import TAMI_SYSTEM_PROMPT

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
    Later you can also inject SQLite chat history here.
    """
    user_text = state.get("input_text", "")
    context = state.get("context", {})
    history = state.get("history", [])

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

    state["messages"] = [system_msg, context_msg, *history, user_msg]
    state["tool_calls_used"] = 0

    #print("[TamiGraph] messages:", state["messages"])
    return state
