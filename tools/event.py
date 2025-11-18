from __future__ import annotations
from typing import Any, Optional, Literal, List, Dict
from tools.base import function_tool, span_attrs, mark_error, redact, summarize, now_iso
from agents import RunContextWrapper
from models.event_item import EventItem, ProcessedEventResult
from tools.base import instrument_io
from tools.process_event import _process_event
from models.app_context import AppCtx

@function_tool(strict_mode=True)
@instrument_io(
    name="tool.process_event",
    meta={"agent": "tami", "operation": "tool", "tool": "process_event", "schema": "EventItem.v1"},
    input_fn=lambda ctx, event: {
        "user_id": ctx.context.user_id,
        # ↓ serialize Pydantic model for the instrumentation layer
        "event": (event.model_dump() if hasattr(event, "model_dump")
                  else event.dict() if hasattr(event, "dict")
                  else event)
    },
    output_fn=summarize,
    redact=True,
)
def process_event(ctx: RunContextWrapper[AppCtx], event: EventItem):
    with span_attrs("tool.process_event", agent="tami", operation="tool", tool="process_event") as s:
        # ↓ serialize before redaction/logging to avoid .items() on a model
        _event_dict = (event.model_dump() if hasattr(event, "model_dump")
                       else event.dict() if hasattr(event, "dict")
                       else event)
        s.update(input={"args": redact(_event_dict)})
        try:
            out = _process_event(ctx, event)
            s.update(output=summarize(out))
            return out
        except Exception as e:
            mark_error(e, kind="ToolError.process_event", span=s)
            raise

@function_tool(strict_mode=True)
@instrument_io(
    name="tool.process_events",
    meta={
        "agent": "tami",
        "operation": "tool",
        "tool": "process_events",
        "schema": "BulkEvents.v1",
    },
    input_fn=lambda ctx, events: {
        "user_id": ctx.context.user_id,
        "count": len(events or []),
        "events_preview": [
            {
                "title": getattr(e, "title", None),
                "start": getattr(e, "start", None),
            }
            for e in (events[:5] if events else [])
        ],
    },
    output_fn=lambda results: {
        "count": len(results or []),
        "ok": sum(1 for r in (results or []) if r.ok),
        "errors": sum(1 for r in (results or []) if not r.ok),
        "slot_taken": sum(1 for r in (results or []) if r.code == "slot_taken"),
    },
    redact=True,
)
def process_events(
    ctx: RunContextWrapper[AppCtx],
    events: List[EventItem],
) -> List[ProcessedEventResult]:
    """
    Bulk-process multiple events using the existing _process_event logic.

    Use when the user provides 2+ events in one message.
    """
    MAX_EVENTS = 20
    if len(events) > MAX_EVENTS:
        raise ValueError(f"Too many events in one call (max {MAX_EVENTS}).")

    results: List[ProcessedEventResult] = []

    with span_attrs(
        "tool.process_events",
        agent="tami",
        operation="tool",
        tool="process_events",
    ) as s:
        try:
            s.update(
                input={
                    "count": len(events),
                    "events_preview": redact(
                        [
                            {
                                "title": getattr(e, "title", None),
                                "start": getattr(e, "start", None),
                            }
                            for e in (events[:5] if events else [])
                        ]
                    ),
                }
            )

            errors_meta: list[dict] = []

            for idx, event in enumerate(events):
                try:
                    out = _process_event(ctx, event)
                    # { ok: bool, item_id: str|None, error: str|None, code: str|None, conflicts?: [...] }

                    results.append(
                        ProcessedEventResult(
                            index=idx,
                            ok=bool(out.get("ok")),
                            item_id=out.get("item_id"),
                            error=out.get("error"),
                            code=out.get("code"),
                            conflicts=out.get("conflicts"),
                        )
                    )

                    # Collect business errors into metadata (not exceptions)
                    if out.get("error"):
                        errors_meta.append(
                            {
                                "index": idx,
                                "code": out.get("code"),
                                "error": out.get("error"),
                            }
                        )

                except Exception as e:
                    # real, unexpected exception
                    mark_error(e, kind="ToolError.process_events_item", span=s)
                    results.append(
                        ProcessedEventResult(
                            index=idx,
                            ok=False,
                            item_id=None,
                            error=str(e),
                            code="exception",
                            conflicts=None,
                        )
                    )

            # After the loop, attach aggregated error info to the span metadata:
            if errors_meta:
                s.update(metadata={
                    "item_errors": errors_meta,
                    "errors_count": len(errors_meta),
                })



            # summarize at batch level; summarize() can be your existing helper
            s.update(
                output=summarize(
                    {
                        "count": len(results),
                        "ok": sum(1 for r in results if r.ok),
                        "errors": sum(1 for r in results if not r.ok),
                        "slot_taken": sum(
                            1 for r in results if r.code == "slot_taken"
                        ),
                    }
                )
            )
            return results

        except Exception as e:
            mark_error(e, kind="ToolError.process_events", span=s)
            raise