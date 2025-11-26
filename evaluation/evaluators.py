import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from langfuse import Evaluation
from zoneinfo import ZoneInfo


def _normalize_tool_name(name: Any) -> Any:
    """Strip SDK/LLM prefixes like 'functions.' so scores compare apples to apples."""
    if isinstance(name, str) and name.startswith("functions."):
        return name.split(".", 1)[1]
    return name


def _coerce_mapping_like(value: Any) -> Dict[str, Any]:
    """
    Best-effort helper: turn Agent SDK objects, LLM JSON strings or dict-like
    objects into a plain dict that we can inspect.
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

    # pydantic v1/v2 models
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
    """
    Normalize args into a dict. If we cannot parse them, keep a raw copy
    under __raw_arguments for debugging.
    """
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


def _extract_tool_plan(output: Any) -> List[Dict[str, Any]]:
    """
    Returns a list of {tool, args} dicts from:
      - legacy Agent SDK style: {"tool": "...", "args": {...}}
      - old JSON style:        {"tool_plan": [{...}, {...}]}
      - NEW router style:      {"actions": [{...}, {...}], "followup_message": ...}
      - optional wrapper:      {"planner_output": { ... one of the above ... }}
    """
    obj = _coerce_mapping_like(output)
    plan: List[Dict[str, Any]] = []

    if not obj:
        return plan

    # Optional wrapper: planner_output
    if "planner_output" in obj and isinstance(obj["planner_output"], (dict, str)):
        inner = _coerce_mapping_like(obj["planner_output"])
        inner_plan = _extract_tool_plan(inner)
        if inner_plan:
            return inner_plan

    # 1) Old JSON style – explicit tool_plan list
    tool_plan = obj.get("tool_plan")
    if isinstance(tool_plan, list):
        for raw_entry in tool_plan:
            entry = raw_entry if isinstance(raw_entry, dict) else _coerce_mapping_like(raw_entry)
            tool = _normalize_tool_name(entry.get("tool"))
            if not tool:
                continue
            plan.append({"tool": tool, "args": _coerce_args(entry.get("args"))})
        if plan:
            return plan

    # 2) NEW router style – actions list
    actions = obj.get("actions")
    if isinstance(actions, list):
        for raw_entry in actions:
            entry = raw_entry if isinstance(raw_entry, dict) else _coerce_mapping_like(raw_entry)
            tool = _normalize_tool_name(entry.get("tool"))
            if not tool:
                continue
            plan.append({"tool": tool, "args": _coerce_args(entry.get("args"))})
        if plan:
            return plan

    # 3) Simple single-tool shape: {"tool": "...", "args": {...}}
    tool = _normalize_tool_name(obj.get("tool"))
    if tool:
        plan.append({"tool": tool, "args": _coerce_args(obj.get("args"))})

    return plan


def _first_tool_call(output: Any) -> Optional[Dict[str, Any]]:
    plan = _extract_tool_plan(output)
    return plan[0] if plan else None


def _expected_no_tool(expected_output: Any) -> bool:
    if not isinstance(expected_output, dict):
        return False
    tool = expected_output.get("tool", None)
    return tool in (None, "", "none")


def _is_plain_text_response(output: Any) -> bool:
    obj = _coerce_mapping_like(output)
    if not obj:
        return False

    # If we wrapped a non-JSON answer in {"__raw_output": "..."}
    if "__raw_output" in obj:
        return True

    tool_plan = obj.get("tool_plan")
    tool = obj.get("tool")

    # Nothing tool-like in there → treat as plain text
    if (tool is None) and (tool_plan is None or tool_plan == []):
        return True

    return False


def schema_valid_evaluator(*, input, output, expected_output=None, metadata=None, **kwargs):
    # Case 1: dataset says "no tool expected"
    if _expected_no_tool(expected_output):
        # Plain-text answer with no tool calls is valid
        if _is_plain_text_response(output):
            return Evaluation(
                name="schema_valid",
                value=1.0,
                comment=None,
            )
        # If there *is* a tool call when none expected → fail
        first_call = _first_tool_call(output)
        if first_call:
            return Evaluation(
                name="schema_valid",
                value=0.0,
                comment=f"tool call present ({first_call.get('tool')!r}) but no tool expected",
            )
        # Fallback: nothing recognizable
        return Evaluation(
            name="schema_valid",
            value=0.0,
            comment="no tool expected but output not recognized as plain text",
        )

    # Case 2: normal tool-based item
    first_call = _first_tool_call(output)
    ok = first_call is not None
    return Evaluation(
        name="schema_valid",
        value=1.0 if ok else 0.0,
        comment=None if ok else "output does not contain a tool plan entry",
    )


def tool_match_evaluator(*, input, output, expected_output=None, **kwargs):
    if not isinstance(expected_output, dict):
        return Evaluation(
            name="tool_match",
            value=None,
            comment="missing or invalid expected_output",
        )

    actual_call = _first_tool_call(output)
    actual_tool = actual_call.get("tool") if actual_call else None
    expected_tool = expected_output.get("tool")

    # If no tool is expected (plain text)
    if expected_tool in (None, "", "none"):
        value = 1.0 if actual_tool is None else 0.0
        comment = None if value == 1.0 else f"unexpected tool call: {actual_tool!r}"
        return Evaluation(name="tool_match", value=value, comment=comment)

    # Normal tool case
    value = 1.0 if actual_tool == expected_tool else 0.0
    comment = None
    if value == 0.0:
        comment = f"tool mismatch: actual={actual_tool!r}, expected={expected_tool!r}"

    return Evaluation(name="tool_match", value=value, comment=comment)


IGNORED_FIELDS_BY_TOOL = {
    "process_reminder": {"item_type"},
    "process_task": {"item_type"},
    "process_event": {"item_type"},
}


def _normalize_title(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    s = value.strip()
    # Example normalization: ignore leading 'ה'
    if s.startswith("ה"):
        s = s[1:].strip()
    return s


def _extract_inner_args(tool_name: str, root: dict) -> dict:
    """
    Support both:
      {"args": {"event": {...}}}
    and:
      {"args": {...}}  # flat
    """
    if not isinstance(root, dict):
        return {}

    if tool_name == "process_reminder":
        if "reminder" in root and isinstance(root["reminder"], dict):
            return root["reminder"]
        return root  # flat

    if tool_name == "process_task":
        if "task" in root and isinstance(root["task"], dict):
            return root["task"]
        return root  # flat

    if tool_name == "process_event":
        if "event" in root and isinstance(root["event"], dict):
            return root["event"]
        return root  # flat

    return root


def args_match_evaluator(*, input, output, expected_output=None, **kwargs):
    if _expected_no_tool(expected_output):
        # Nothing to compare – a plain-text answer is fine
        return Evaluation(name="args_match", value=1.0, comment=None)

    if not isinstance(expected_output, dict):
        return Evaluation(
            name="args_match",
            value=0.0,
            comment="no or invalid expected_output",
        )

    # Expected
    expected_tool = expected_output.get("tool")
    expected_args_root = expected_output.get("args") or {}

    # Actual
    actual_call = _first_tool_call(output)
    actual_tool = actual_call.get("tool") if actual_call else None
    actual_args_root = actual_call.get("args") if actual_call else {}

    READ_ONLY_TOOLS = {"get_items", "search_chat_history", "web_search"}
    READ_ONLY_ITEM_TYPES = {"tasks", "events", "reminders", "scheduled_messages"}  # optional

    if expected_tool in READ_ONLY_TOOLS:
        # Minimal arg check: item_type (if given), nothing else.
        exp_item_type = expected_args_root.get("item_type")
        act_item_type = actual_args_root.get("item_type")

        # If exp_item_type is defined, it must match.
        if exp_item_type and act_item_type != exp_item_type:
            return Evaluation(
                name="args_match",
                value=0.0,
                comment=f"item_type mismatch: expected={exp_item_type!r}, actual={act_item_type!r}",
            )

        # If statuses exist (e.g. pending tasks), check them too
        exp_status = expected_args_root.get("status")
        act_status = actual_args_root.get("status")

        if exp_status and act_status != exp_status:
            return Evaluation(
                name="args_match",
                value=0.0,
                comment=f"status mismatch: expected={exp_status!r}, actual={act_status!r}",
            )

        # All good
        return Evaluation(name="args_match", value=1.0, comment=None)

    tool_name = actual_tool or expected_tool or ""
    if not tool_name:
        return Evaluation(
            name="args_match",
            value=0.0,
            comment="no tool name available for args_match",
        )

    ignored = IGNORED_FIELDS_BY_TOOL.get(tool_name, set())

    expected = _extract_inner_args(tool_name, expected_args_root)
    actual = _extract_inner_args(tool_name, actual_args_root)

    mismatches = {}

    for k, exp_val in expected.items():
        if k in ignored:
            continue

        act_val = actual.get(k, None)

        # special handling for titles
        if k == "title":
            if _normalize_title(exp_val) != _normalize_title(act_val):
                mismatches[k] = {"expected": exp_val, "actual": act_val}
            continue

        if act_val != exp_val:
            mismatches[k] = {"expected": exp_val, "actual": act_val}

    if mismatches:
        return Evaluation(
            name="args_match",
            value=0.0,
            comment=f"{tool_name} fields mismatch: {mismatches}",
        )

    return Evaluation(name="args_match", value=1.0, comment=None)


def _parse_iso_to_aware(s: str, tz_str: str) -> datetime:
    """
    Parse ISO-like string into a timezone-aware datetime in tz_str.
    - If string has 'Z', treat as UTC.
    - If string has offset, convert to tz_str.
    - If no offset, assume local time in tz_str.
    """
    if s.endswith("Z"):
        # fromisoformat doesn't like 'Z', normalize to +00:00
        s = s[:-1] + "+00:00"

    dt = datetime.fromisoformat(s)

    tz = ZoneInfo(tz_str)

    if dt.tzinfo is None:
        # treat as local time in tz_str
        return dt.replace(tzinfo=tz)

    # convert to target tz
    return dt.astimezone(tz)


def time_semantics_evaluator(*, input, output, expected_output=None, metadata=None, **kwargs):
    if _expected_no_tool(expected_output):
        # No time-based tool in this test
        return Evaluation(name="time_semantics", value=1.0, comment=None)

    if not isinstance(expected_output, dict):
        return Evaluation(
            name="time_semantics",
            value=0.0,
            comment="no or invalid expected_output",
        )

    if not isinstance(input, dict):
        return Evaluation(name="time_semantics", value=0.0, comment="input not dict")

    in_obj = input.get("in") or {}
    tz_str = in_obj.get("tz") or "Asia/Jerusalem"

    # What tool and args did we ACTUALLY use?
    call = _first_tool_call(output)
    if not call:
        return Evaluation(
            name="time_semantics",
            value=0.0,
            comment="no tool call detected",
        )

    tool = call.get("tool")
    actual_root = call.get("args") or {}
    expected_root = expected_output.get("args") or {}

    # Extract expected/actual datetime strings per tool
    if tool == "process_reminder":
        actual = _extract_inner_args(tool, actual_root)
        expected = _extract_inner_args(tool, expected_root)
        act_str = actual.get("datetime")
        exp_str = expected.get("datetime")
    elif tool == "process_task":
        actual = _extract_inner_args(tool, actual_root)
        expected = _extract_inner_args(tool, expected_root)
        act_str = actual.get("due")
        exp_str = expected.get("due")
    elif tool == "process_event":
        actual = _extract_inner_args(tool, actual_root)
        expected = _extract_inner_args(tool, expected_root)
        act_str = actual.get("datetime")
        exp_str = expected.get("datetime")
    elif tool == "process_scheduled_message":
        actual = _extract_inner_args(tool, actual_root)
        expected = _extract_inner_args(tool, expected_root)
        act_str = actual.get("scheduled_time")
        exp_str = expected.get("scheduled_time")
    else:
        # non time-based tool: don't penalize
        return Evaluation(
            name="time_semantics",
            value=1.0,
            comment=f"tool {tool!r} not time-based, skipped",
        )

    if not act_str or not exp_str:
        return Evaluation(
            name="time_semantics",
            value=0.0,
            comment="missing datetime/due in expected or actual",
        )

    try:
        act_dt = _parse_iso_to_aware(act_str, tz_str)
        exp_dt = _parse_iso_to_aware(exp_str, tz_str)
    except Exception as e:
        return Evaluation(name="time_semantics", value=0.0, comment=f"parse error: {e}")

    if act_dt == exp_dt:
        return Evaluation(
            name="time_semantics",
            value=1.0,
            comment="datetime match",
        )

    return Evaluation(
        name="time_semantics",
        value=0.0,
        comment=f"datetime mismatch: expected={exp_dt}, actual={act_dt}",
    )


def _get_actual_text(output: Any) -> str:
    """
    Extract the plain-text answer from the LLM result.
    Priority:
    1) __raw_output (our wrapper for plain text)
    2) assistant_message (if you ever use it here)
    3) response (new responder JSON: {"response": "..."})
    """
    obj = _coerce_mapping_like(output)
    if not obj:
        return ""

    raw = obj.get("__raw_output")
    if isinstance(raw, str):
        return raw

    msg = obj.get("assistant_message")
    if isinstance(msg, str):
        return msg

    resp = obj.get("response")
    if isinstance(resp, str):
        return resp

    return ""


def raw_output_includes_evaluator(*, input, output, expected_output=None, **kwargs):
    """
    Check that the actual plain-text answer contains ALL required substrings.

    expected_output["__raw_output"] can be:
      - a single string  -> must appear in actual text
      - a list of strings -> all must appear in actual text
    """
    if not isinstance(expected_output, dict):
        return Evaluation(
            name="raw_output_includes",
            value=0,
            comment="no or invalid expected_output",
        )

    expected = expected_output.get("__raw_output")
    if expected is None:
        # nothing to check for this item
        return Evaluation(
            name="raw_output_includes",
            value=1,
            comment="no __raw_output in expected_output",
        )

    actual = _get_actual_text(output)

    # Normalize: string -> [string], list[str] -> list
    if isinstance(expected, str):
        required = [expected]
    elif isinstance(expected, list):
        required = [s for s in expected if isinstance(s, str)]
    else:
        return Evaluation(
            name="raw_output_includes",
            value=0,
            comment="__raw_output must be string or list[str]",
        )

    missing = [s for s in required if s not in actual]

    if missing:
        return Evaluation(
            name="raw_output_includes",
            value=0.0,
            comment=f"missing substrings: {missing}",
        )

    return Evaluation(
        name="raw_output_includes",
        value=1.0,
        comment=None,
    )


OVERSCORE_METRICS = [
    "schema_valid",
    "tool_match",
    "args_match",
    "time_semantics",
    "output_match",
    "raw_output_includes",
]


def overall_evaluator(*, input, output, expected_output=None, metadata=None, **kwargs):
    """
    Per-item overall score in [0,1].

    It calls the other evaluators locally, averages their numeric values,
    and returns a single Evaluation named 'overall'.

    Langfuse will then show:
      - per-item 'overall'
      - run-level ∅ overall (api)
    """

    sub_evals = [
        schema_valid_evaluator(
            input=input, output=output, expected_output=expected_output, metadata=metadata, **kwargs
        ),
        tool_match_evaluator(
            input=input, output=output, expected_output=expected_output, metadata=metadata, **kwargs
        ),
        args_match_evaluator(
            input=input, output=output, expected_output=expected_output, metadata=metadata, **kwargs
        ),
        time_semantics_evaluator(
            input=input, output=output, expected_output=expected_output, metadata=metadata, **kwargs
        ),
        raw_output_includes_evaluator(
            input=input, output=output, expected_output=expected_output, metadata=metadata, **kwargs
        ),
    ]

    vals = [ev.value for ev in sub_evals if isinstance(ev.value, (int, float))]

    if not vals:
        return Evaluation(
            name="overall",
            value=None,
            comment="no numeric sub-scores for overall",
        )

    value = sum(vals) / len(vals)

    return Evaluation(
        name="overall",
        value=value,
        comment=None,
    )
