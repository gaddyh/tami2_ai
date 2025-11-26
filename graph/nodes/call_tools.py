import json
from typing import List, Dict, Any

from pydantic import ValidationError

from graph.state import TamiState
from graph.tools.build import TOOL_MODELS, TOOL_IMPLS  # adjust import paths


def call_tools_node(state: TamiState) -> TamiState:
    #print("[TamiGraph] call_tools_node")
    #print("[TamiGraph] state:", state)

    messages = state.get("messages", [])
    if not messages:
        return state

    last_msg = messages[-1]
    tool_calls: List[Dict[str, Any]] = last_msg.get("tool_calls", [])

    tool_messages: List[Dict[str, Any]] = []

    for tc in tool_calls:
        func = tc.get("function", {})
        name = func.get("name")
        raw_args_json = func.get("arguments") or "{}"

        try:
            raw_args = json.loads(raw_args_json)
            print("name:", name)
            print("raw_args:", raw_args)
        except json.JSONDecodeError:
            raw_args = {}

        # Default result in case of problems
        result: Any

        impl = TOOL_IMPLS.get(name)
        model_entry = TOOL_MODELS.get(name)

        if impl is None:
            result = {"error": f"Tool '{name}' not implemented."}
        elif model_entry is None:
            # No schema registered: pass raw args
            try:
                result = impl(**raw_args)
            except Exception as e:
                result = {"error": str(e)}
        else:
            model_cls = model_entry[0]
            try:
                args_obj = model_cls(**raw_args)
            except ValidationError as ve:
                result = {
                    "error": "Invalid arguments for tool.",
                    "details": ve.errors(),
                }
            else:
                try:
                    # You can choose whether impl takes the object or unpacked dict
                    # result = impl(args_obj)
                    result = impl(**args_obj.model_dump())
                except Exception as e:
                    result = {"error": str(e)}

        # Ensure content is a string for the tool message
        if isinstance(result, str):
            content = result
        else:
            content = json.dumps(result, ensure_ascii=False)

        tool_messages.append(
            {
                "role": "tool",
                "name": name,
                "tool_call_id": tc["id"],
                "content": content,
            }
        )

    state["messages"] = messages + tool_messages
    return state
