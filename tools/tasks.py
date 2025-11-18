from __future__ import annotations
from typing import Any, Dict
from tools.base import function_tool, span_attrs, mark_error, summarize, now_iso
from models.task_item import BulkTasksAction, TaskItem
from store.task_item_store import TaskStore
from agents import RunContextWrapper
from models.app_context import AppCtx
Json = Dict[str, Any]
from observability.obs import instrument_io
from tools.task import _task_to_patch

def _process_tasks(ctx: RunContextWrapper[AppCtx], action: BulkTasksAction) -> dict:
    """
    Bulk update/delete TASKs by explicit IDs.
    Returns:
      {
        ok: bool,
        count: int,
        results: [{item_id, ok, error=None|str, code=None|str}],
        error: None|str,
        code: None|str
      }
    """
    try:
        user_id = ctx.context.user_id
        if not user_id:
            return {
                "ok": False,
                "count": 0,
                "results": [],
                "error": "missing_user_id",
                "code": "validation_error",
            }

        # Safety: enforce limit
        limit = action.limit or len(action.item_ids)
        ids = action.item_ids[:limit]

        normalized_patch: dict[str, Any] | None = None

        # If bulk_update, validate the patch using TaskItem schema
        if action.command == "bulk_update":
            raw_patch = action.patch

            if raw_patch is None:
                return {
                    "ok": False,
                    "count": 0,
                    "results": [],
                    "error": "missing_patch",
                    "code": "validation_error",
                }

            # Normalize: allow either dict or Pydantic model
            if isinstance(raw_patch, dict):
                normalized_patch = raw_patch
            elif hasattr(raw_patch, "model_dump"):
                # Pydantic-style object
                normalized_patch = raw_patch.model_dump(exclude_unset=True)
            else:
                return {
                    "ok": False,
                    "count": 0,
                    "results": [],
                    "error": "invalid_patch_fields",
                    "code": "validation_error",
                }

            if not normalized_patch:
                # structurally empty patch
                return {
                    "ok": False,
                    "count": 0,
                    "results": [],
                    "error": "missing_patch",
                    "code": "validation_error",
                }

            try:
                # Build a pseudo TaskItem to ensure patch keys are valid
                _ = TaskItem(
                    command="update",
                    item_id="__validation__",
                    **normalized_patch,  # type: ignore[arg-type]
                )
            except Exception:
                return {
                    "ok": False,
                    "count": 0,
                    "results": [],
                    "error": "invalid_patch_fields",
                    "code": "validation_error",
                }

        if action.dry_run:
            return {
                "ok": True,
                "count": len(ids),
                "results": [{"item_id": i, "ok": True} for i in ids],
                "error": None,
                "code": None,
            }

        store = TaskStore()
        results: list[dict[str, Any]] = []

        if action.command == "bulk_delete":
            for item_id in ids:
                try:
                    ok = store.delete(user_id=user_id, item_id=item_id)
                    if not ok:
                        results.append(
                            {
                                "item_id": item_id,
                                "ok": False,
                                "error": "not_found",
                                "code": "not_found",
                            }
                        )
                    else:
                        results.append({"item_id": item_id, "ok": True})
                except Exception as e:
                    results.append(
                        {
                            "item_id": item_id,
                            "ok": False,
                            "error": "unhandled_exception",
                            "code": "internal_error",
                        }
                    )

        elif action.command == "bulk_update":
            assert normalized_patch is not None  # for type checkers

            for item_id in ids:
                try:
                    # Build TaskItem so we can reuse _task_to_patch
                    t = TaskItem(
                        command="update",
                        item_id=item_id,
                        **normalized_patch,  # type: ignore[arg-type]
                    )
                    patch = _task_to_patch(t)
                    ok = store.update(user_id=user_id, item_id=item_id, changes=patch)
                    if not ok:
                        results.append(
                            {
                                "item_id": item_id,
                                "ok": False,
                                "error": "not_found",
                                "code": "not_found",
                            }
                        )
                    else:
                        results.append({"item_id": item_id, "ok": True})
                except Exception as e:
                    results.append(
                        {
                            "item_id": item_id,
                            "ok": False,
                            "error": "unhandled_exception",
                            "code": "internal_error",
                        }
                    )

        else:
            return {
                "ok": False,
                "count": 0,
                "results": [],
                "error": "unknown_command",
                "code": "bad_request",
            }

        return {
            "ok": all(r.get("ok") for r in results) if results else True,
            "count": sum(1 for r in results if r.get("ok")),
            "results": results,
            "error": None,
            "code": None,
        }

    except Exception as e:
        mark_error(e, kind="ToolError.process_tasks", span=s)
        return {
            "ok": False,
            "count": 0,
            "results": [],
            "error": "unhandled_exception",
            "code": "internal_error",
        }


@function_tool(strict_mode=True)
@instrument_io(
    name="tool.process_tasks",
    meta={"agent": "tami", "operation": "tool", "tool": "process_tasks", "schema": "BulkTasksAction.v1"},
    input_fn=lambda ctx, action: {"user_id": ctx.context.user_id, "action": action},
    output_fn=summarize,
    redact=True,
)
def process_tasks(ctx: RunContextWrapper[AppCtx], action: BulkTasksAction):
    with span_attrs("tool.process_tasks", agent="tami", operation="tool", tool="process_tasks") as s:
        s.update(input={"action": action})
        try:
            out = _process_tasks(ctx, action)
            s.update(output=summarize(out)); return out
        except Exception as e:
            mark_error(e, kind="ToolError.process_tasks", span=s); raise
