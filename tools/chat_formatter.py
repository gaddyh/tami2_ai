# chat_formatter.py
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime as DT

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None

DEFAULT_TZ = "Asia/Jerusalem"

# -------------------------
# Public API
# -------------------------

@dataclass(frozen=True)
class FormatOpts:
    tz: str = DEFAULT_TZ
    self_ids: Set[str] = frozenset()
    contact_names: Dict[str, str] = None  # provided by caller if needed
    group_display_name: Optional[str] = None
    show_day_separators: bool = True
    keep_reactions: bool = False
    preserve_query_in_links: bool = True
    you_label: str = "You"

def format_messages_for_llm(
    raw: List[Dict[str, Any]],
    opts: Optional[FormatOpts] = None,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Returns (lines, meta) where meta includes:
      - tz, start_iso, end_iso, visible_count, raw_count
    """
    opts = opts or FormatOpts()
    tzinfo = _tzinfo_or_fail(opts.tz)

    msgs = _dedupe_last_wins(raw)

    filtered: List[Dict[str, Any]] = []
    for m in msgs:
        if _is_reaction(m) and not opts.keep_reactions:
            continue
        t = _text_of(m)
        sig = _visible_signal(m, t)
        if not t and not sig:
            continue
        m["_visible_text"] = t
        m["_visible_signal"] = sig
        m["_ts"] = _coerce_ts(m.get("timestamp"))
        filtered.append(m)

    filtered.sort(key=lambda m: m["_ts"])

    id_to_idx: Dict[str, int] = {}
    for i, m in enumerate(filtered, start=1):
        mid = m.get("idMessage")
        if mid:
            id_to_idx[mid] = i

    id_to_core: Dict[str, Dict[str, Any]] = {
        m.get("idMessage", f"idx-{i}"): {
            "text": m["_visible_text"],
            "signal": m["_visible_signal"],
            "sender": _display_name(m, opts),
            "typeMessage": (m.get("typeMessage") or "").lower(),
        }
        for i, m in enumerate(filtered, start=1)
    }

    lines: List[str] = []
    current_date_key: Optional[str] = None

    for i, m in enumerate(filtered, start=1):
        dt = DT.fromtimestamp(m["_ts"], tzinfo)
        if opts.show_day_separators:
            k = dt.strftime("%Y-%m-%d")
            if k != current_date_key:
                lines.append(f"— {k} —")
                current_date_key = k
            ts_str = dt.strftime("%H:%M")
        else:
            ts_str = dt.strftime("%Y-%m-%d %H:%M") if i == 1 else dt.strftime("%H:%M")

        author = _display_name(m, opts)
        body = m["_visible_text"] or m["_visible_signal"] or ""
        body = body.replace("\n", " · ")

        if _has_link(body) and body.strip().lower().startswith(("http://", "https://")):
            url = _first_url(body)
            if url:
                body = f"[link: {_short(url, 120)}]"

        q = m.get("quotedMessage") or {}
        stanza_id = q.get("stanzaId")

        if stanza_id and stanza_id in id_to_idx:
            ref_idx = id_to_idx[stanza_id]
            ref = id_to_core.get(stanza_id, {})
            ref_author = ref.get("sender", "Unknown")
            ref_excerpt = (ref.get("text") or "").replace("\n", " ").strip()

            if not ref_excerpt:
                sig = ref.get("signal") or _signal_from_type(ref.get("typeMessage"))
                ref_excerpt = sig or "[no text]"

            if ref_excerpt.lower().startswith(("[link:", "http://", "https://")):
                url_in_ref = _first_url(ref.get("text") or "")
                if url_in_ref:
                    ref_excerpt = f"[link: {_short(url_in_ref, 120)}]"

            if len(ref_excerpt) > 120:
                ref_excerpt = ref_excerpt[:117] + "…"

            line = f"[#{i} | {ts_str} | {author}] ↪️ reply to #{ref_idx} ({ref_author}: \"{ref_excerpt}\"): {body}"
        elif stanza_id:
            part = (q.get("participant") or "Unknown")
            line = f"[#{i} | {ts_str} | {author}] ↪️ reply to (out-of-range:{stanza_id}, sender:{part}): {body}"
        else:
            line = f"[#{i} | {ts_str} | {author}]: {body}"

        lines.append(line)

    start_iso, end_iso = _collect_window([m["_ts"] for m in filtered], tzinfo)

    meta = {
        "tz": opts.tz,
        "raw_count": len(raw),
        "visible_count": len(filtered),
        "start_iso": start_iso,
        "end_iso": end_iso,
    }
    return lines, meta

# -------------------------
# Internals
# -------------------------

_LINK_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)

def _first_url(text: str) -> Optional[str]:
    m = _LINK_RE.search(text or "")
    return m.group(0) if m else None

def _short(s: str, n: int = 80) -> str:
    s2 = (s or "").strip().replace("\n", " ")
    if len(s2) <= n:
        return s2
    return s2[: n - 1] + "…"

def _has_link(text: str) -> bool:
    return bool(_LINK_RE.search(text or ""))

def _signal_from_type(tm_lower: str) -> Optional[str]:
    tm = (tm_lower or "").lower()
    if tm == "imagemessage":
        return "[image]"
    if tm in ("audiomessage", "videonote"):
        return "[audio]"
    if tm == "documentmessage":
        return "[file]"
    if tm == "stickermessage":
        return "[sticker]"
    return None

def _visible_signal(m: Dict[str, Any], text: str) -> Optional[str]:
    tm = (m.get("typeMessage") or "").lower()
    if tm == "imagemessage":
        cap = (m.get("caption") or "").strip()
        return f"[image{': ' + _short(cap, 32) if cap else ''}]"
    if tm in ("audiomessage", "videonote"):
        return "[audio]"
    if tm == "documentmessage":
        fname = (m.get("fileName") or "").strip()
        return f"[file{': ' + _short(fname, 32) if fname else ''}]"
    if tm == "stickermessage":
        return "[sticker]"
    if _has_link(text):
        url = _first_url(text)
        if url:
            return f"[link: {_short(url, 120)}]"
    return None

def _is_reaction(m: Dict[str, Any]) -> bool:
    return (m.get("typeMessage") or "").lower() == "reactionmessage"

def _text_of(m: Dict[str, Any]) -> str:
    ext = m.get("extendedTextMessage") or {}
    t = ext.get("text") or m.get("textMessage") or ""
    return str(t).strip()

def _display_name(m: Dict[str, Any], opts: FormatOpts) -> str:
    name = (m.get("senderName") or "").strip()
    if name:
        return name
    sid = (m.get("senderId") or "").strip()
    cn = opts.contact_names or {}
    if sid and sid in opts.self_ids:
        return opts.you_label
    if sid and sid in cn:
        return cn[sid]
    fallback = (m.get("senderContactName") or "").strip() or sid
    if not fallback:
        chat = (m.get("chatId") or "").strip()
        if chat.endswith("@g.us") and opts.group_display_name:
            return opts.you_label
        return chat or "Unknown"
    return fallback

def _tzinfo_or_fail(tz: str):
    if ZoneInfo is None:
        raise RuntimeError("zoneinfo_unavailable")
    try:
        return ZoneInfo(tz)
    except Exception:
        raise RuntimeError(f"invalid_timezone:{tz}")

def _dedupe_last_wins(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for m in raw:
        mid = m.get("idMessage")
        if mid:
            by_id[mid] = m
    return list(by_id.values())

def _coerce_ts(v: Any) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0

def _collect_window(ts_list: List[int], tzinfo) -> Tuple[Optional[str], Optional[str]]:
    if not ts_list:
        return None, None
    start = min(ts_list)
    end = max(ts_list)
    return (
        DT.fromtimestamp(start, tzinfo).isoformat(),
        DT.fromtimestamp(end, tzinfo).isoformat(),
    )
