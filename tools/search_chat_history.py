# tools/search_chat_history.py
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from datetime import datetime as DT, timezone as TZ
from tools.base import function_tool, instrument_io, summarize
from agents import RunContextWrapper
from observability.obs import span_attrs
from observability.telemetry import mark_error
from models.app_context import AppCtx
from tools.chat_formatter import format_messages_for_llm, FormatOpts, DEFAULT_TZ

# External dependency: your Green API client
from green_api.chats_history import get_last_messages_for_user

MAX_LIMIT = 200

# -------------------------
# Chat ID normalization
# -------------------------

_RE_JID_PERSONAL = re.compile(r"^\d{6,}@c\.us$")
_RE_JID_GROUP    = re.compile(r"^[0-9A-Za-z._-]{6,}@g\.us$")
_RE_RAW_NUMBER   = re.compile(r"^\+?\d{6,}$")

def _classify_chat_input(chat: str) -> str:
    s = (chat or "").strip()
    if _RE_JID_PERSONAL.match(s): return "jid_personal"
    if _RE_JID_GROUP.match(s):    return "jid_group"
    if _RE_RAW_NUMBER.match(s):   return "raw"
    return "invalid"

def _normalize_israel_number(raw: str) -> str:
    """
    Normalize Israeli mobile formats to E.164 (without '+'), e.g.:
      '0521234567' -> '972521234567'
      '+972521234567' -> '972521234567'
    """
    s = raw.lstrip("+").strip()
    if s.startswith("0") and len(s) >= 9:
        return "972" + s[1:]
    return s

def _normalize_chat_id(chat: str) -> str:
    s = (chat or "").strip()
    cls = _classify_chat_input(s)
    if cls == "invalid":
        raise ValueError("invalid_chat_identifier")
    if cls == "raw":
        digits = _normalize_israel_number(s)
        return f"{digits}@c.us"
    return s  # jid_personal / jid_group pass-through

# -------------------------
# Tool
# -------------------------

def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, **payload}

def _fail(code: str, msg: Optional[str] = None, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = {"ok": False, "error": code}
    if msg:
        base["message"] = msg
    if extra:
        base.update(extra)
    return base

@function_tool(strict_mode=True)
@instrument_io(
    name="tool.search_chat_history",
    meta={"agent": "tami", "operation": "tool", "tool": "search_chat_history", "schema": "SearchChatHistory.v1"},
    input_fn=lambda ctx, chat_id, limit=50: {
        "user_id": getattr(getattr(ctx, "context", None), "user_id", None),
        "chat_id_preview": (chat_id or "")[:4] + "…" if chat_id else "",
        "limit": limit,
    },
    output_fn=summarize,
    redact=True,
)
def search_chat_history(
    ctx: RunContextWrapper[AppCtx],
    chat_id: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Fetch the last N messages of a specific chat by JID or raw number.
    - Accepts ONLY a valid chat identifier (JID or phone). Names are invalid.
    - When you only have a name, first call get_candidate_recipient_chat_ids(name).

    Returns { ok, chat_history: [str], meta: {...} } or { ok: False, error, ... }.
    """
    return _search_chat_history(ctx=ctx, chat_id=chat_id, limit=limit)
      

def _search_chat_history(
    ctx: RunContextWrapper[AppCtx],
    chat_id: str,
    limit: int = 50,
    *,
    tz: str = DEFAULT_TZ,
    self_ids: Optional[List[str]] = None,
    contact_names: Optional[Dict[str, str]] = None,
    show_day_separators: bool = True,
    keep_reactions: bool = False,
    preserve_query_in_links: bool = True,
    group_display_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch last N WhatsApp messages and format for LLM consumption.

    Returns:
      {
        ok: bool,
        chat_history: [str],
        meta: {
          chat_id, limit_requested, limit_applied,
          fetched_raw, visible_count, tz, start_iso, end_iso, has_more
        },
        error?: str, message?: str
      }
    """
    t0 = DT.now(TZ.utc)
    masked = (chat_id or "")[:4] + "…"

    with span_attrs("tool.search_chat_history", agent="tami", operation="tool", tool="search_chat_history") as s:
        s.update(input={"chat_id_preview": masked, "limit": limit, "tz": tz})

        user_id = getattr(getattr(ctx, "context", None), "user_id", None)
        if not user_id:
            s.update(output={"error": "missing_user_id"})
            return _fail("missing_user_id", "ctx.context.user_id is required", {"chat_history": []})

        try:
            normalized_chat_id = _normalize_chat_id(chat_id)
            id_class = _classify_chat_input(chat_id)
        except ValueError as e:
            s.update(output={"error": "invalid_chat_identifier"})
            return _fail(
                "invalid_chat_identifier",
                "Input looks like a name or placeholder, not a JID/number.",
                {
                    "hint": "Call get_candidate_recipient_chat_ids(name) first and pass its chat_id here.",
                    "chat_history": []
                },
            )

        try:
            limit_int = max(1, min(int(limit), MAX_LIMIT))
        except Exception:
            limit_int = 50

        # Fetch
        try:
            raw_messages: List[Dict[str, Any]] = get_last_messages_for_user(user_id, normalized_chat_id, limit_int)
        except Exception as e:
            mark_error(e, kind="ToolError.search_chat_history.fetch", span=s)
            return _fail("fetch_failed", str(e), {"chat_history": []})

        # Format
        opts = FormatOpts(
            tz=tz,
            self_ids=set(self_ids or []),
            contact_names=contact_names or {},
            group_display_name=group_display_name,
            show_day_separators=show_day_separators,
            keep_reactions=keep_reactions,
            preserve_query_in_links=preserve_query_in_links,
            you_label="You",
        )

        try:
            lines, meta = format_messages_for_llm(raw_messages, opts)
        except Exception as e:
            mark_error(e, kind="ToolError.search_chat_history.format", span=s)
            return _fail("format_failed", str(e), {"chat_history": []})

        has_more = len(raw_messages) == limit_int
        out_meta = {
            "chat_id": normalized_chat_id,
            "limit_requested": limit,
            "limit_applied": limit_int,
            "fetched_raw": len(raw_messages),
            "visible_count": meta["visible_count"],
            "tz": meta["tz"],
            "start_iso": meta["start_iso"],
            "end_iso": meta["end_iso"],
            "has_more": has_more,
        }

        header = f"— last {out_meta['visible_count']} (of {out_meta['fetched_raw']}) up to {out_meta['end_iso'] or 'n/a'} {tz} —"
        if not lines or not lines[0].startswith("— "):
            lines.insert(0, header)

        t1 = DT.now(TZ.utc)
        duration_ms = int((t1 - t0).total_seconds() * 1000)

        s.update(output=summarize({
            "meta": {**out_meta, "duration_ms": duration_ms, "class": id_class},
            "preview": lines[:2],
        }))

        return _ok({
            "chat_history": lines,
            "meta": out_meta,
        })
