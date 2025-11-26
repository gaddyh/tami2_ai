from langfuse import get_client, Evaluation
from models.input import In
from models.decision import TargetAgent
from evaluation.utility import extract_tool_call_and_output
from datetime import datetime, timezone
from shared.time import to_user_timezone
from graph.nodes.tami_llm import tami_llm_node
langfuse = get_client()
from typing import Dict, Any
import json
from graph.prompt import TAMI_SYSTEM_PROMPT
async def tami_task(*, item, **kwargs):
    raw = item.input  # whatever you put into dataset.input

    in_data = raw["in"]
    target_agent_name = raw.get("target_agent", "PERSONAL_ASSISTANT")

    # Hydrate your Pydantic model
    inp = In(**in_data)

    # Map string to your TargetAgent enum
    target_agent = TargetAgent[target_agent_name]

    # Call your real agent
    turn = await run_agent(inp, target_agent=target_agent)

    # Now choose what the "output" of the experiment is.
    # For a tool-based evaluation, you'd typically return
    # the *structured tool call* you want to evaluate.
    tool_call = extract_tool_call_and_output(turn)  # your function

    return tool_call  # this becomes `output` in evaluators


from graph.build import build_tami_app
from graph.state import TamiState

tami_graph_app = build_tami_app()

async def tami2_task(*, item, **kwargs):
    raw = item.input  # whatever you put into dataset.input

    in_data = raw["in"]

    # Hydrate your Pydantic model
    inp = In(**in_data)
    ctx = {
                "user_name":inp.user_name,
                "default_tz":inp.tz,
                "current_datetime":inp.current_datetime or to_user_timezone(datetime.now(timezone.utc), inp.tz).isoformat(),
            }
    state1: TamiState = {
        "input_text": inp.text,
        "context": ctx,
    }
    out1 = tami_graph_app.invoke(state1)
    print("out1 raw 1:", out1)
    #print("Reply 1:", out1["final_output"]) 

    # Now choose what the "output" of the experiment is.
    # For a tool-based evaluation, you'd typically return
    # the *structured tool call* you want to evaluate.
    tool_call = extract_tool_call_and_output(out1)  # your function

    return tool_call  # this becomes `output` in evaluators

def tami_llm_task(item=None, **kwargs):
    input_data = item.input or {}
    expected_output = item.expected_output  # only used by evaluators, that's fine

    # Extract dataset-provided "now"
    eval_now = input_data.get("evaluation_now")
    default_tz = input_data.get("tz", "Asia/Jerusalem")

    user_messages = list(input_data.get("messages", []))

    # TEMP: debug logging
    print("=== tami_llm_task input ===")
    print(user_messages, eval_now)

    # -------------------------
    # 1) SYSTEM MESSAGE #1
    # -------------------------
    system_msg = {
        "role": "system",
        "content": TAMI_SYSTEM_PROMPT,
    }

    # -------------------------
    # 2) SYSTEM MESSAGE #2  (CONTEXT JSON)
    # -------------------------
    context_msg = {
        "role": "system",
        "content": (
            "CONTEXT (Json):\n"
            "{\n"
            f'  "current_datetime": "{eval_now}",\n'
            f'  "default_tz": "{default_tz}"\n'
            "}"
        ),
    }

    # Build initial state
    state: TamiState = {
        "messages": [system_msg, context_msg] + user_messages
    }

    # Run the LLM node once
    try:
        state = tami_llm_node(state)
        print("=== tami_llm_task output ===")
        #print(state)
    except Exception as e:
        print(f"LLM node failed: {e}")
        return {"__raw_output": str(e)}

    # ---------- NEW: prefer tool_calls ----------
    messages = state.get("messages", [])
    tool_plan = extract_tool_plan_from_messages(messages)

    if tool_plan:
        # Shape this to match your dataset expected_output
        # (adjust keys if needed: tool_plan vs tool, etc.)
        last_msg = messages[-1] if messages else {}
        assistant_text = last_msg.get("content") or ""

        parsed = {
            "tool_plan": tool_plan,
            "should_return_to_llm": False,
            "assistant_message": assistant_text,
        }
        return parsed

    # ---------- FALLBACK: parse final_output JSON ----------
    raw = state.get("final_output")

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"__raw_output": raw}
    elif isinstance(raw, dict):
        parsed = raw
    else:
        parsed = {"__raw_output": raw}

    return parsed



def extract_tool_plan_from_messages(messages):
    last = messages[-1] if messages else {}
    tool_calls = last.get("tool_calls") or []
    plan = []
    for tc in tool_calls:
        plan.append({
            "tool": tc["function"]["name"],
            "args": json.loads(tc["function"]["arguments"] or "{}"),
        })
    return plan

