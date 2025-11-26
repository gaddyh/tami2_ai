# evaluation/tami_router_task.py

from typing import Any, Dict
from models.input import In
from agent.tami.graph import build_tami_router_app, handle_tami_turn
from agent.linear_flow.state import LinearAgentState
from datetime import datetime
import time
import json
import uuid

# Build router app once per worker
app = build_tami_router_app()


def to_iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else dt


def extract_tool_plan_from_response(res: dict) -> list[dict]:
    """
    Expected res structure (your handle_tami_turn):
    {
        "planner_output": { "actions": [...], "followup_message": ... },
        "responder_output": "...",
        ...
    }
    We extract only planner actions → tool_plan.
    """
    if not res:
        return []

    planner = res.get("planner_output", {})
    actions = planner.get("actions") or []

    tool_plan = []
    for a in actions:
        tool_name = a.get("tool")
        if not tool_name:
            continue
        tool_plan.append({
            "tool": tool_name,
            "args": a.get("args") or {},
        })
    return tool_plan

EVAL_RUN_ID = uuid.uuid4().hex

async def tami_router_task(*, item, **kwargs) -> Dict[str, Any]:
    raw = item.input
    in_data = raw.get("in", {})
    inp = In(**in_data)

    # -----------------------------
    # Build base LinearAgentState
    # -----------------------------
    state: LinearAgentState = {
        "input_text": inp.text,
        "context": {
            "user_id": inp.user_id,
            "user_name": inp.user_name,
            "thread_id": EVAL_RUN_ID,
            "chat_id": inp.chat_id,
            "source": inp.source,
            "category": inp.category,
            "text": inp.text,
            "input_id": inp.input_id,
            "idempotency_key": inp.idempotency_key,
            "source_ids": inp.source_ids,
            "attachments": inp.attachments,
            "metadata": inp.metadata,
            "reply": inp.reply,
            "locale": inp.locale,
            "tz": inp.tz,
            "current_datetime": to_iso(inp.current_datetime),
            "received_at": to_iso(inp.received_at),
            "redacted": inp.redacted,
        },
    }

    # -----------------------------
    # Run REAL Tami turn
    # -----------------------------
    result = handle_tami_turn(app, inp.thread_id, inp.text, base_state=state)
    graph_state = result.get("state") or {}

    # -----------------------------
    # 1) Try planner_output (old shape)
    # -----------------------------
    tool_plan: list[dict] = []
    actions = []
    followup_msg = ""

    planner = graph_state.get("planner_output")
    if isinstance(planner, dict):
        actions = planner.get("actions") or []
        followup_msg = planner.get("followup_message") or ""

    # -----------------------------
    # 2) If no actions, derive from context.tools.latest
    # -----------------------------
    if not actions:
        ctx = graph_state.get("context") or {}
        tools_meta = ctx.get("tools") or {}
        for tool_name, meta in tools_meta.items():
            if not isinstance(meta, dict):
                continue
            latest = meta.get("latest")
            if not isinstance(latest, dict):
                continue
            args = latest.get("args") or {}
            tool_plan.append({"tool": tool_name, "args": args})
    else:
        for a in actions:
            if not isinstance(a, dict):
                continue
            tool = a.get("tool")
            if not tool:
                continue
            tool_plan.append({"tool": tool, "args": a.get("args") or {}})

    # -----------------------------
    # Assistant message
    # -----------------------------
    if not followup_msg:
        followup_msg = graph_state.get("response") or ""

    return {
        "tool_plan": tool_plan,
        "assistant_message": followup_msg,
    }

