from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def _normalize_tool_name(name: Any) -> Any:
    if isinstance(name, str) and name.startswith("functions."):
        return name.split(".", 1)[1]
    return name


def _coerce_mapping_like(value: Any) -> Dict[str, Any]:
    """
    Convert common structured objects (dicts, JSON strings, Pydantic models)
    into a plain dict for downstream processing.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            dumped = value.dict()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    return {}


def _coerce_args(value: Any) -> Dict[str, Any]:
    """Parse args payloads (dict, JSON string, model) into a dict."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {"__raw_arguments": value}
        return parsed if isinstance(parsed, dict) else {"__raw_arguments": value}
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            dumped = value.dict()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    return {"__raw_arguments": value}


def _normalize_plan_list(plan: Any) -> List[Dict[str, Any]]:
    """Return a list of {tool, args} dicts extracted from plan entries."""
    normalized: List[Dict[str, Any]] = []
    if not isinstance(plan, list):
        return normalized
    for entry in plan:
        entry_dict = entry if isinstance(entry, dict) else _coerce_mapping_like(entry)
        tool = _normalize_tool_name(entry_dict.get("tool"))
        if not tool:
            continue
        normalized.append({"tool": tool, "args": _coerce_args(entry_dict.get("args"))})
    return normalized


def _extract_from_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Handle LLM JSON outputs that contain tool_plan / tool / args."""
    if not payload:
        return None

    plan = _normalize_plan_list(payload.get("tool_plan"))
    if plan:
        first = plan[0]
        out: Dict[str, Any] = {
            "tool_plan": plan,
            "tool": first.get("tool"),
            "args": first.get("args", {}),
        }
        if "result" in payload:
            out["result"] = payload["result"]
        if "assistant_message" in payload:
            out["assistant_message"] = payload["assistant_message"]
        if "should_return_to_llm" in payload:
            out["should_return_to_llm"] = payload["should_return_to_llm"]
        return out

    tool = _normalize_tool_name(payload.get("tool"))
    if tool:
        args = _coerce_args(payload.get("args"))
        out: Dict[str, Any] = {
            "tool": tool,
            "args": args,
            "tool_plan": [{"tool": tool, "args": args}],
        }
        if "result" in payload:
            out["result"] = payload["result"]
        if "assistant_message" in payload:
            out["assistant_message"] = payload["assistant_message"]
        if "should_return_to_llm" in payload:
            out["should_return_to_llm"] = payload["should_return_to_llm"]
        return out

    return None


def extract_tool_call_and_output(turn: Any) -> Dict[str, Any]:
    """
    Unified helper for the new LLM JSON responses that expose tool_plan entries directly.

    Input `turn` is expected to be either:
      - the raw LLM JSON (with tool_plan/tool/args), or
      - a wrapper dict with 'final_output' or 'output' containing that JSON.
    """
    payload = _coerce_mapping_like(turn)
    extracted = _extract_from_payload(payload)
    if extracted:
        return extracted

    # Fallback: sometimes the actual response is nested under 'final_output'/'output'
    final_output = payload.get("final_output") or payload.get("output")
    extracted = _extract_from_payload(_coerce_mapping_like(final_output))
    if extracted:
        return extracted

    return {
        "tool": None,
        "args": {},
        "result": None,
        "tool_plan": [],
    }


def extract_tool_call_from_turn(turn: Any) -> Optional[Dict[str, Any]]:
    """
    Return the first tool call ({tool, args}) found in a new-style LLM JSON
    response. This is what you should feed into your evaluators.
    """
    payload = extract_tool_call_and_output(turn)
    plan = payload.get("tool_plan") if isinstance(payload, dict) else None
    if isinstance(plan, list) and plan:
        entry = plan[0]
        if isinstance(entry, dict):
            tool = entry.get("tool")
            if tool:
                return {"tool": tool, "args": entry.get("args", {})}

    tool = _normalize_tool_name(payload.get("tool")) if isinstance(payload, dict) else None
    if tool:
        return {"tool": tool, "args": payload.get("args", {})}

    return None

import json
from datetime import datetime
from typing import Dict, Any


def evaluation_to_dict(ev) -> Dict[str, Any]:
    """Convert langfuse.Evaluation → plain dict."""
    return {
        "name": ev.name,
        "value": ev.value,
        "comment": ev.comment,
        "timestamp": getattr(ev, "timestamp", None),
        "metadata": getattr(ev, "metadata", None),
    }

import os

def write_result_to_pretty_json_per_item(result: dict, dirpath: str = "eval_results") -> str:
    """
    Writes one evaluation result to eval_results/<item_id>.json (pretty-printed).
    Creates the directory if needed.
    Returns the path used.
    """
    os.makedirs(dirpath, exist_ok=True)

    item_id = result["item_id"] or "unknown_item"
    safe_id = item_id.replace("/", "_")
    filepath = os.path.join(dirpath, f"{safe_id}.json")

    evals = {
        name: evaluation_to_dict(ev)
        for name, ev in result["evaluations"].items()
    }

    entry = {
        "item_id": result["item_id"],
        "input": result["input"],
        "expected_output": result["expected_output"],
        "task_result": result["task_result"],
        "evaluations": evals,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)

    print(f"\nWrote pretty JSON → {filepath}")
    return filepath
