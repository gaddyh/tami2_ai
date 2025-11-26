# tami/router_graph.py

import json
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from openai import OpenAI

from agent.linear_flow.state import LinearAgentState
from agent.tami.router_prompt import ROUTER_SYSTEM_PROMPT

from agent.tami.tasks.main import build_tasks_agent_graph
from agent.tami.events.main import build_events_agent_graph
from agent.tami.comms.main import build_comms_agent_graph

client = OpenAI()  # or reuse your existing client


def llm_route(input_text: str) -> Literal["tasks", "events", "comms"]:
    """
    Call the router LLM and return one of: "tasks" | "events" | "comms".
    Falls back to "tasks" on any error.
    """
    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",  # or whatever you're using
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": input_text},
            ],
        )
        content = resp.choices[0].message.content
        data = json.loads(content)

        target = data.get("target_agent", "tasks")
        if target not in ("tasks", "events", "comms"):
            target = "tasks"
        return target  # type: ignore[return-value]

    except Exception:
        # conservative fallback
        return "tasks"  # type: ignore[return-value]


def route_node(state: LinearAgentState) -> LinearAgentState:
    """
    Router node that uses the LLM to choose target_agent.
    """
    text = state.get("input_text", "") or ""

    target = llm_route(text)
    state["target_agent"] = target

    # optional: keep routing explanation in context for debugging
    # (only if you want it)
    # state.setdefault("context", {})["routing_reason"] = data.get("reason")

    return state
