from __future__ import annotations
from typing import Any, Dict
from tools.base import mark_error, summarize, _fail, _ok, _validate
from observability.obs import instrument_io, span_attrs, mark_error
from models.task_item import TaskItem
from models.app_context import AppCtx
Json = Dict[str, Any]
from store.task_item_store import TaskStore

def _drop_nones(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}

def _task_to_payload(task: TaskItem, user_id: str) -> Dict[str, Any]:
    data = task.model_dump(exclude_unset=True)
    data["user_id"] = user_id
    data.pop("command", None)

    # default status for new tasks
    if "status" not in data:
        data["status"] = "open"

    if isinstance(data.get("due"), str) and not data["due"].strip():
        data["due"] = None

    return {k: v for k, v in data.items() if v is not None}


def _task_to_patch(task: TaskItem) -> Dict[str, Any]:
    """For update: build partial patch (schema-agnostic)."""
    data = task.model_dump(exclude_unset=True)
    # Never patch these directly
    for k in ("command", "item_id", "user_id", "item_type"):
        data.pop(k, None)
    # Ignore empty/blank due strings
    if isinstance(data.get("due"), str) and not data["due"].strip():
        data["due"] = None
    return _drop_nones(data)

def _process_task(user_id: str, task: TaskItem) -> dict:
    """
    Create/update/delete a TASK (Firestore-only MVP).
    Returns: { ok: bool, item_id: str|None, error: str|None, code: str|None }
    """
    try:
        if not user_id:
            return _fail("missing_user_id", code="validation_error")

        # basic validation
        err = _validate(task)
        if err:
            return _fail(err, code="validation_error")

        store = TaskStore()

        if task.command == "create":
            payload = _task_to_payload(task, user_id=user_id)
            item_id = store.create(payload)
            return _ok(item_id)

        if task.command == "update":
            if not task.item_id:
                return _fail("missing_item_id", code="validation_error")
            patch = _task_to_patch(task)
            ok = store.update(user_id=user_id, item_id=task.item_id, changes=patch)
            if not ok:
                return _fail("not_found", code="not_found")
            return _ok(task.item_id)

        if task.command == "delete":
            if not task.item_id:
                return _fail("missing_item_id", code="validation_error")
            ok = store.delete(user_id=user_id, item_id=task.item_id)
            if not ok:
                return _fail("not_found", code="not_found")
            return _ok(task.item_id)
        
        if task.command == "complete":
            if not task.item_id:
                return _fail("missing_item_id", code="validation_error")
            ok = store.update(user_id=user_id, item_id=task.item_id, changes={"status": "completed"})
            if not ok:
                return _fail("not_found", code="not_found")
            return _ok(task.item_id)


        return _fail("unknown_command")

    except Exception as e:
        mark_error(e, kind="ToolError.process_task"); raise
        return _fail("unhandled_exception", code="internal_error")



@instrument_io(
        name="tool.process_task",
        meta={"agent": "tami", "operation": "tool", "tool": "process_task", "schema": "TaskItem.v1"},
        input_fn=lambda user_id, task: {"user_id": user_id, "task": task},
        output_fn=summarize,
        redact=True,
    )   
def process_task(user_id: str, task: TaskItem) -> dict:
    with span_attrs("tool.process_task", agent="tami", operation="tool", tool="process_task") as s:
        s.update(input={"task": task})
        try:
            out = _process_task(user_id, task)
            s.update(output=summarize(out)); return out
        except Exception as e:
            mark_error(e, kind="ToolError.process_task", span=s); raise
