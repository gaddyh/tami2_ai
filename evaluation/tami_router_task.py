# evaluation/tami_router_task.py

from typing import Any, Dict
from models.input import In
from agent.tami.graph import build_tami_router_app, handle_tami_turn
from agent.linear_flow.state import LinearAgentState
from datetime import datetime
import time
import json
import uuid
from shared import time as shared_time


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
        tool_plan.append(
            {
                "tool": tool_name,
                "args": a.get("args") or {},
            }
        )
    return tool_plan


EVAL_RUN_ID = uuid.uuid4().hex


def tami_router_task(*, item, **kwargs) -> Dict[str, Any]:
    raw = item.input
    in_data = raw.get("in", {})
    inp = In(**in_data)

    # -----------------------------
    # Build base LinearAgentState
    # -----------------------------
    now = shared_time.to_user_timezone(inp.current_datetime, inp.tz)
    iso_with_weekday = f"{now.isoformat()} ({now.strftime('%A')})"

    state: LinearAgentState = {
        "input_text": inp.text,
        "context": {
            "user_id": inp.user_id,
            "user_name": inp.user_name,
            "thread_id": inp.user_id,
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
            "current_datetime": inp.current_datetime,
            "received_at": to_iso(inp.received_at),
            "redacted": inp.redacted,
        },
    }

    # -----------------------------
    # Run REAL Tami turn
    # -----------------------------
    start = time.time()
    result = handle_tami_turn(app, inp.thread_id, inp.text, base_state=state)
    end = time.time()
    print(f"Tami turn took {end - start:.2f}s\n\n")

    graph_state = result.get("state") or {}
    print("=== Tami Turn Output ===")
    #print("graph_state:", graph_state)
    #print("result:", result)

    status = result.get("status")

    # -----------------------------
    # TOOL METADATA (for plan + debug)
    # -----------------------------
    ctx = graph_state.get("context") or {}
    tools_meta = ctx.get("tools") or {}

    print("=== Tool Results ===")
    if not tools_meta:
        print("(no tools metadata)")
    else:
        for tool_name, meta in tools_meta.items():
            if not isinstance(meta, dict):
                continue
            latest = meta.get("latest")
            last_error = meta.get("last_error")
            print(f"- {tool_name}:")
            if isinstance(latest, dict):
                print("  latest args:", latest.get("args"))
                print("  latest result:", latest.get("result"))
                print("  latest error:", latest.get("error"))
            if isinstance(last_error, dict):
                print("  last_error args:", last_error.get("args"))
                print("  last_error result:", last_error.get("result"))
                print("  last_error error:", last_error.get("error"))

    # -----------------------------
    # TOOL PLAN (best-effort)
    # -----------------------------
    tool_plan: list[dict] = []
    actions: list[dict] = []

    planner = graph_state.get("planner_output")
    if isinstance(planner, dict):
        actions = planner.get("actions") or []

    if not actions:
        # Derive from tools metadata: prefer latest, fall back to last_error
        for tool_name, meta in tools_meta.items():
            if not isinstance(meta, dict):
                continue

            latest = meta.get("latest")
            last_error = meta.get("last_error")

            rec = None
            if isinstance(latest, dict):
                rec = latest
            elif isinstance(last_error, dict):
                rec = last_error

            if not rec:
                continue

            args = rec.get("args") or {}
            tool_plan.append({"tool": tool_name, "args": args})
    else:
        # Planner explicitly gave us actions
        for a in actions:
            if not isinstance(a, dict):
                continue
            tool = a.get("tool")
            if not tool:
                continue
            tool_plan.append({"tool": tool, "args": a.get("args") or {}})

    # -----------------------------
    # Assistant message (response / followup)
    # -----------------------------
    response = None
    followup = None

    if status == "ok":
        # Normal completed turn: read from graph_state
        response = graph_state.get("response")
        followup = graph_state.get("followup_message")
    elif status == "interrupt":
        # Followup interrupt: question lives on the Interrupt payload
        intr = result.get("interrupt")
        if intr is not None:
            value = getattr(intr, "value", {}) or {}
            followup = value.get("question")

    if followup:
        assistant_message = f"[FOLLOWUP] {followup}"
    else:
        assistant_message = response or ""

    print("=== Responder Output ===")
    print("response:", response)
    print("followup_message:", followup)

    return {
        "tool_plan": tool_plan,
        "assistant_message": assistant_message,
    }
