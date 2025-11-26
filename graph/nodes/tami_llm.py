from graph.state import TamiState
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv(".venv/.env")
client = OpenAI()  # assumes OPENAI_API_KEY in env
from graph.tools.build import TOOLS
from typing import Dict, Any

def tami_llm_node(state: TamiState) -> TamiState:
    """
    Call OpenAI Chat once, allowing tool calls.
    """
    messages = state.get("messages", [])

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.0,
    )

    # TEMP: debug logging
    print("=== tami_llm_node output ===")
    #print(resp)
    choice = resp.choices[0].message
    print("choice:", choice)
    assistant_msg: Dict[str, Any] = {
        "role": "assistant",
        "content": choice.content,
    }

    # Attach tool_calls if present
    tool_calls = getattr(choice, "tool_calls", None)
    if tool_calls:
        assistant_msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,  # usually "function"
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,  # JSON string
                },
            }
            for tc in tool_calls
        ]

    messages.append(assistant_msg)
    state["messages"] = messages


    # TEMP: debug logging
    #print("=== tami_llm_node output ===")
    #print(resp)     
    # If there are no tool calls, this is the final answer for the user
    if not tool_calls:
        state["final_output"] = choice.content or ""

    return state
