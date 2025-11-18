# obs.py (Langfuse v3-compatible)
from __future__ import annotations

import time
import inspect
from functools import wraps
from contextlib import contextmanager
from typing import Any, Callable, ParamSpec, TypeVar, Optional, Mapping
from observability.langfuse_client import langfuse

def _agent_meta(inp: In, target_agent: Optional[TargetAgent] = None, **_):
    return {
        "agent": getattr(target_agent, "value", str(target_agent or "unknown")),
        "operation": "route",
    }

def _agent_input(inp: In, target_agent: Optional[TargetAgent] = None, **_):
    return {
        "user_id": inp.user_id,
        "thread_id": inp.thread_id,
        "text": inp.text or "",
        "reply_parent_id": getattr(getattr(inp, "reply", None), "parent_message_id", None),
    }

def _agent_output(out: AgentResult):
    return out  # will be safely dumped

def _dump(obj: Any) -> Any:
    try:
        md = getattr(obj, "model_dump", None)
        if callable(md): return md()
        d = getattr(obj, "dict", None)
        if callable(d): return d()
        return obj
    except Exception:
        return obj

def _maybe_redact(v: Any, *, redact: bool) -> Any:
    if not redact or not isinstance(v, Mapping): return v
    try:
        return {k: ("***" if k in SENSITIVE else val) for k, val in v.items()}
    except Exception:
        return v

P = ParamSpec("P")
T = TypeVar("T")

def _safe_update_current_span(*, metadata: Optional[dict[str, Any]] = None,
                              status_message: Optional[str] = None,
                              level: Optional[str] = None) -> None:
    try:
        langfuse.update_current_span(metadata=metadata or {},
                                     status_message=status_message,
                                     level=level)
    except Exception:
        # Never let observability crash business logic
        pass

def _safe_span_update(span, *, metadata: dict[str, Any]) -> None:
    try:
        span.update(metadata=metadata)
    except Exception:
        pass

def instrument_io(
    *,
    # span name (static) or builder(args, kwargs) -> str
    name: str | Callable[..., str],
    # metadata to set on span at start (static dict) or builder(args, kwargs) -> dict
    meta: Optional[dict] | Callable[..., Mapping[str, Any]] = None,
    # input extractor: (args, kwargs) -> dict | Any
    input_fn: Optional[Callable[..., Any]] = None,
    # output extractor: (result) -> dict | Any
    output_fn: Optional[Callable[[Any], Any]] = None,
    redact: bool = False,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorate a function so each call becomes a span, with safe input/output logging.
    """
    def deco(fn: Callable[P, T]) -> Callable[P, T]:
        is_async = inspect.iscoroutinefunction(fn)

        def _name(*args, **kwargs) -> str:
            return name(*args, **kwargs) if callable(name) else name

        def _meta(*args, **kwargs) -> Mapping[str, Any]:
            if callable(meta): return dict(meta(*args, **kwargs))
            return dict(meta or {})

        async def _async(*args: P.args, **kwargs: P.kwargs) -> T:  # type: ignore[misc]
            n = _name(*args, **kwargs)
            t0 = time.perf_counter()
            with langfuse.start_as_current_span(name=n) as s:
                _safe_span_update(s, metadata=_meta(*args, **kwargs))
                try:
                    if input_fn is not None:
                        iv = _dump(input_fn(*args, **kwargs))
                        langfuse.update_current_span(input=_maybe_redact(iv, redact=redact))
                    out = await fn(*args, **kwargs)
                    if output_fn is not None:
                        ov = _dump(output_fn(out))
                        langfuse.update_current_span(output=_maybe_redact(ov, redact=redact))
                    _safe_update_current_span(metadata={"status": "ok", "duration.ms": int((time.perf_counter()-t0)*1000)})
                    return out
                except Exception as e:
                    _safe_update_current_span(
                        metadata={"status": "error", "error.kind": type(e).__name__, "duration.ms": int((time.perf_counter()-t0)*1000)},
                        status_message=str(e), level="ERROR"
                    )
                    # also mark with your helper to keep conventions
                    mark_error(e, kind="InstrumentedIOError", span=s)
                    raise

        def _sync(*args: P.args, **kwargs: P.kwargs) -> T:
            n = _name(*args, **kwargs)
            t0 = time.perf_counter()
            with langfuse.start_as_current_span(name=n) as s:
                _safe_span_update(s, metadata=_meta(*args, **kwargs))
                try:
                    if input_fn is not None:
                        iv = _dump(input_fn(*args, **kwargs))
                        langfuse.update_current_span(input=_maybe_redact(iv, redact=redact))
                    out = fn(*args, **kwargs)
                    if output_fn is not None:
                        ov = _dump(output_fn(out))
                        langfuse.update_current_span(output=_maybe_redact(ov, redact=redact))
                    _safe_update_current_span(metadata={"status": "ok", "duration.ms": int((time.perf_counter()-t0)*1000)})
                    return out
                except Exception as e:
                    _safe_update_current_span(
                        metadata={"status": "error", "error.kind": type(e).__name__, "duration.ms": int((time.perf_counter()-t0)*1000)},
                        status_message=str(e), level="ERROR"
                    )
                    mark_error(e, kind="InstrumentedIOError", span=s)
                    raise

        return wraps(fn)(_async if is_async else _sync)
    return deco

def instrument(agent: str, operation: str, **defaults: Any) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Example:
      @instrument(agent="tasks", operation="handle", schema_version="tasks.v1")
      def tasks_agent(...): ...
    Works for both sync and async functions.
    """
    def deco(fn: Callable[P, T]) -> Callable[P, T]:
        name = f"{agent}.{operation}"
        base_meta = {"agent": agent, "operation": operation, **defaults}

        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                t0 = time.perf_counter()
                with langfuse.start_as_current_span(name=name) as span:
                    _safe_span_update(span, metadata=base_meta)
                    try:
                        out = await fn(*args, **kwargs)
                        dur_ms = int((time.perf_counter() - t0) * 1000)
                        _safe_update_current_span(metadata={"status": "ok", "duration.ms": dur_ms})
                        return out
                    except Exception as e:
                        dur_ms = int((time.perf_counter() - t0) * 1000)
                        _safe_update_current_span(
                            metadata={"status": "error",
                                      "error.kind": type(e).__name__,
                                      "duration.ms": dur_ms},
                            status_message=str(e),
                            level="ERROR",
                        )
                        raise
            return wrapper  # type: ignore[misc]
        else:
            @wraps(fn)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                t0 = time.perf_counter()
                with langfuse.start_as_current_span(name=name) as span:
                    _safe_span_update(span, metadata=base_meta)
                    try:
                        out = fn(*args, **kwargs)
                        dur_ms = int((time.perf_counter() - t0) * 1000)
                        _safe_update_current_span(metadata={"status": "ok", "duration.ms": dur_ms})
                        return out
                    except Exception as e:
                        dur_ms = int((time.perf_counter() - t0) * 1000)
                        _safe_update_current_span(
                            metadata={"status": "error",
                                      "error.kind": type(e).__name__,
                                      "duration.ms": dur_ms},
                            status_message=str(e),
                            level="ERROR",
                        )
                        raise
            return wrapper  # type: ignore[misc]
    return deco


@contextmanager
def span_attrs(name: str, as_type: str = "span", **attrs: Any):
    """
    Lightweight nested observation with fixed metadata.
    For LLM calls, pass as_type="generation" and model="gpt-4o".
    """
    t0 = time.perf_counter()

    # Pull out model if provided so it becomes a first-class field
    model = attrs.pop("model", None)

    with langfuse.start_as_current_observation(
        name=name,
        as_type=as_type,
        model=model,
    ) as s:
        # remaining attrs go to metadata
        if attrs:
            _safe_span_update(s, metadata=dict(attrs))

        try:
            yield s
            dur_ms = int((time.perf_counter() - t0) * 1000)
            s.update(metadata={"status": "ok", "duration.ms": dur_ms})
        except Exception as e:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            s.update(
                metadata={
                    "status": "error",
                    "error.kind": type(e).__name__,
                    "duration.ms": dur_ms,
                },
                status_message=str(e),
                level="ERROR",
            )
            raise


# obs_io.py
from typing import Any, Optional
from observability.langfuse_client import langfuse

SENSITIVE_FIELDS = {"text", "message", "note", "content", "body"}

def _safe_dump(obj: Any) -> Any:
    try:
        # Pydantic v2
        md = getattr(obj, "model_dump", None)
        if callable(md):
            return md()
        # Pydantic v1
        dict_ = getattr(obj, "dict", None)
        if callable(dict_):
            return dict_()
        return obj
    except Exception:
        return obj

def _redact(val: Any) -> Any:
    if not isinstance(val, dict):
        return val
    try:
        return {k: ("***" if k in SENSITIVE_FIELDS else v) for k, v in val.items()}
    except Exception:
        return val

def safe_update_current_span_io(*, input: Optional[Any] = None,
                                output: Optional[Any] = None,
                                redact: bool = False) -> None:
    try:
        payload = {}
        if input is not None:
            v = _safe_dump(input)
            payload["input"] = _redact(v) if redact else v
        if output is not None:
            v = _safe_dump(output)
            payload["output"] = _redact(v) if redact else v
        if payload:
            langfuse.update_current_span(**payload)
    except Exception:
        pass

# obs_io.py (continued)
from contextlib import contextmanager
from observability.obs import span_attrs  # your file
from observability.telemetry import mark_error

@contextmanager
def span_step(name: str, *, kind: str, redact_input=False, **attrs):
    with span_attrs(name, **attrs) as s:
        try:
            yield s
        except Exception as e:
            # single place to mark + rethrow
            mark_error(e, kind=kind, span=s)
            raise
