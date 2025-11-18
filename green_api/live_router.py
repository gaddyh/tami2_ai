# green_live_router.py
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db.base import db
from green_api.ledger_item import extract_ledger_from_message  # keep your path
from agent.order.core import extract_orders_from_message

MONITORED_CHATS = {"120363049228849607@g.us"}
#MONITORED_CHATS = {"972546610653-1492611986@g.us", "120363049228849607@g.us"}
#MONITORED_CHATS = {"dummy"}

green_live_router = APIRouter()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

ERROR_INVALID_INSTANCE = "INVALID_INSTANCE"
ERROR_UNEXPECTED = "UNEXPECTED_ERROR"

EXPECTED_TOKEN = os.getenv("GREEN_WEBHOOK_TOKEN", "")

def _err(status: int, code: str, message: str, extra: dict | None = None) -> JSONResponse:
    payload = {"ok": False, "error": {"code": code, "message": message}}
    if extra:
        payload["error"].update(extra)
    return JSONResponse(status_code=status, content=payload)

def _ok(data: dict) -> JSONResponse:
    return JSONResponse(status_code=200, content={"ok": True, "data": data})

# -----------------------------------------------------------------------------
# In-proc message store (now also keeps message_id)
# -----------------------------------------------------------------------------
MESSAGES_BY_CHAT: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

def save_text_message(
    chat_id: str, text: str, ts: float | int | None = None, message_id: Optional[str] = None
) -> None:
    if not (chat_id and text is not None):
        return
    MESSAGES_BY_CHAT[chat_id].append({
        "text": text,
        "ts": float(ts or time.time()),
        "message_id": message_id,
    })

# -----------------------------------------------------------------------------
# Deduping
# -----------------------------------------------------------------------------
DEDUPE_TTL = 24 * 3600
_seen: Dict[str, float] = {}

def _seen_before(key: str) -> bool:
    now = time.time()
    for k, exp in list(_seen.items())[:64]:
        if exp <= now:
            _seen.pop(k, None)
    if key in _seen and _seen[key] > now:
        return True
    _seen[key] = now + DEDUPE_TTL
    return False

def _dedupe_key(data: dict, message_id: Optional[str]) -> str:
    t = (data.get("typeWebhook") or data.get("event", {}).get("typeWebhook") or "").lower()
    return f"{t}:{message_id or ''}"

# -----------------------------------------------------------------------------
# Minimal extraction
# -----------------------------------------------------------------------------
# replace this line:
# TEXT_TYPES = {"textMessage", "extendedTextMessage", "quotedMessage"}
# with:
TEXT_TYPES = {
    "textMessage", "extendedTextMessage", "quotedMessage",
    "imageMessage", "videoMessage", "documentMessage", "fileMessage"  # <-- media can carry caption
}

def _first_present_text(*vals):
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v
    return None

def _extract_minimal_fields(payload: dict) -> Tuple[
    Optional[str], Optional[str], Optional[float], Optional[str], Optional[str], Optional[str], Optional[str]
]:
    ev = payload.get("event") or payload
    md = (ev.get("messageData") or {})
    t = (md.get("typeMessage") or "").strip()

    instance_id = str((ev.get("instanceData") or {}).get("idInstance") or "") or None
    chat_id = (ev.get("senderData") or {}).get("chatId") or None
    ts_raw = md.get("timestamp") or ev.get("timestamp") or time.time()
    try:
        ts = float(ts_raw)
    except Exception:
        ts = float(time.time())

    message_id = (
        ev.get("idMessage")
        or md.get("idMessage")
        or md.get("stanzaId")
        or md.get("key", {}).get("id")
        or None
    )

    twh = (ev.get("typeWebhook") or payload.get("typeWebhook") or "").lower()
    direction = "inbound" if "incoming" in twh else ("outbound" if "outgoing" in twh else None)

    sender = (ev.get("senderData") or {}).get("sender") or (ev.get("senderData") or {}).get("senderName") or None

    # robust text extraction (now includes media captions, incl. fileMessageData)
    def _first_present_text(*vals):
        for v in vals:
            if isinstance(v, str) and v.strip():
                return v
        return None

    text: Optional[str] = None
    if t in TEXT_TYPES:
        # 1) canonical paths
        text = _first_present_text(
            (md.get("textMessageData") or {}).get("textMessage"),
            (md.get("extendedTextMessageData") or {}).get("text"),
        )
        # 2) quotedMessage type still may carry current reply text
        if text is None and t == "quotedMessage":
            text = _first_present_text(
                (md.get("extendedTextMessageData") or {}).get("text"),
                (md.get("textMessageData") or {}).get("textMessage"),
            )
        # 3) nested message block
        if text is None:
            message_block = md.get("message") or {}
            text = _first_present_text(
                (message_block.get("extendedTextMessageData") or {}).get("text"),
                (message_block.get("textMessageData") or {}).get("textMessage"),
                message_block.get("conversation"),
            )
        # 4) media captions (add fileMessageData here!)
        if text is None:
            for k in ("imageMessageData", "videoMessageData", "documentMessageData", "fileMessageData"):
                cap = (md.get(k) or {}).get("caption")
                if isinstance(cap, str) and cap.strip():
                    text = cap
                    break

    return instance_id, chat_id, ts, (text or None), message_id, direction, sender


# -----------------------------------------------------------------------------
# Reply + media extraction (handles quoted + current, recursive + multiple key names)
# -----------------------------------------------------------------------------
def _extract_reply_and_media(payload: dict) -> Tuple[Optional[str], Optional[str], List[str]]:
    def _dig(d: Any, *path: str) -> Any:
        cur = d
        for p in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(p)
        return cur

    def _first_present(*vals):
        for v in vals:
            if v:
                return v
        return None

    def _collect_media_urls(block: Any, urls: List[str], depth: int = 0) -> None:
        """Recursively collect media URLs from any dict/list shape."""
        if depth > 6:
            return
        if isinstance(block, dict):
            # explicit fields Green-API/WA use across variants
            candidate_keys = (
                "downloadUrl", "url", "urlFile", "fileUrl", "mediaUrl",
                "canonicalUrl", "matchedText",
            )
            for k in candidate_keys:
                val = block.get(k)
                if isinstance(val, str) and val.startswith(("http://", "https://")):
                    urls.append(val)
            # also parse caption/text for embedded URLs
            for k in ("caption", "text", "title", "description", "conversation"):
                s = block.get(k)
                if isinstance(s, str):
                    import re
                    for m in re.findall(r"https?://\S+", s):
                        urls.append(m.rstrip(").,;"))
            # recurse into nested message/contexts
            for v in block.values():
                _collect_media_urls(v, urls, depth + 1)
        elif isinstance(block, list):
            for it in block:
                _collect_media_urls(it, urls, depth + 1)

    ev = payload.get("event") or payload
    md = (ev.get("messageData") or {})

    # --- quoted block (replies) ---
    quoted_block = _first_present(
        _dig(md, "extendedTextMessageData", "quotedMessage"),
        _dig(md, "quotedMessage"),
        _dig(md, "contextInfo", "quotedMessage"),
    )

    quoted_text: Optional[str] = None
    quoted_message_id: Optional[str] = _first_present(
        _dig(md, "extendedTextMessageData", "stanzaId"),
        _dig(md, "quotedMessageId"),
        _dig(md, "contextInfo", "stanzaId"),
        _dig(ev, "quotedMessageId"),
    )

    if isinstance(quoted_block, dict):
        quoted_text = _first_present(
            quoted_block.get("textMessage"),
            _dig(quoted_block, "extendedTextMessageData", "text"),
            quoted_block.get("conversation"),
            quoted_block.get("caption"),
            _dig(quoted_block, "documentMessageData", "fileName"),
        )
        quoted_message_id = _first_present(
            quoted_message_id,
            quoted_block.get("stanzaId"),
            _dig(quoted_block, "key", "id"),
            quoted_block.get("idMessage"),
        )

    # --- collect media from CURRENT message and QUOTED message (recursive) ---
    media_urls: List[str] = []
    _collect_media_urls(md, media_urls)
    if isinstance(quoted_block, dict):
        _collect_media_urls(quoted_block, media_urls)

    # dedupe preserve order
    seen, deduped = set(), []
    for u in media_urls:
        if u and u not in seen:
            seen.add(u)
            deduped.append(u)

    return quoted_text, quoted_message_id, deduped

# -----------------------------------------------------------------------------
# Firestore persist (also stores reply/media)
# -----------------------------------------------------------------------------
def _save_extracted_orders(
    *,
    instance_id: str,
    chat_id: str,
    ts: float,
    message_id: Optional[str],
    direction: Optional[str],
    sender: Optional[str],
    payload: Dict[str, Any],
    original_text: str,
    quoted_text: Optional[str],
    quoted_message_id: Optional[str],
    media_urls: List[str],
) -> None:
    try:
        doc_ref = db.collection("orders_ledger").document()
        payload_dict = payload.model_dump(mode="python", exclude_none=True)
        payload_dict["line_items"] = [
          li.model_dump(mode="python", exclude_none=True) for li in (payload.line_items or [])
        ]

        to_save = {
            "instance_id": instance_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "direction": direction,
            "sender": sender,
            "ts": ts,
            "original_text": original_text,
            "orders_payload": payload_dict,
            "quoted_text": quoted_text,
            "quoted_message_id": quoted_message_id,
            "media_urls": media_urls or [],
            "created_at": time.time(),
        }
        if hasattr(db, "set_document"):
            db.set_document(doc_ref, to_save)
        else:
            doc_ref.set(to_save)
    except Exception as e:
        logger.exception("[orders] Firestore persist failed: %s", e)

# -----------------------------------------------------------------------------
# Async orders worker
# -----------------------------------------------------------------------------
async def _orders_worker(
    *,
    instance_id: str,
    chat_id: str,
    ts: float,
    text: str,
    message_id: Optional[str],
    direction: Optional[str],
    sender: Optional[str],
    quoted_text: Optional[str],
    quoted_message_id: Optional[str],
    media_urls: List[str],
) -> None:
    try:
        # upgrade quoted text from cache if possible
        full_quoted = quoted_text
        if chat_id and quoted_message_id:
            for m in reversed(MESSAGES_BY_CHAT.get(chat_id, [])):
                if m.get("message_id") == quoted_message_id:
                    full_quoted = m.get("text") or full_quoted
                    break

        payload = await extract_orders_from_message(
            text=text,
        )
        if payload:
            _save_extracted_orders(
                instance_id=instance_id,
                chat_id=chat_id,
                ts=ts,
                message_id=message_id,
                direction=direction,
                sender=sender,
                payload=payload,
                original_text=text,
                quoted_text=full_quoted,
                quoted_message_id=quoted_message_id,
                media_urls=media_urls,
            )
        else:
            logger.info("[orders] extractor returned None (send to Sheets likely failed)")
    except Exception as e:
        logger.exception("[orders] worker failed: %s", e)

# -----------------------------------------------------------------------------
# FastAPI route
# -----------------------------------------------------------------------------
@green_live_router.post("/green_live")
async def green_live(req: Request):
    try:
        auth_header = req.headers.get("authorization") or ""
        if EXPECTED_TOKEN:
            if not auth_header.lower().startswith("bearer "):
                return _err(401, ERROR_UNEXPECTED, "Missing or invalid Authorization header")
            token = auth_header.split(" ", 1)[1]
            if token != EXPECTED_TOKEN:
                return _err(403, ERROR_UNEXPECTED, "Forbidden")
        data = await req.json()
    except Exception:
        return _err(400, ERROR_UNEXPECTED, "Invalid JSON payload")

    instance_id, chat_id, ts, text, message_id, direction, sender = _extract_minimal_fields(data)
    if not instance_id:
        return _err(400, ERROR_INVALID_INSTANCE, "Missing instance id")

    if _seen_before(_dedupe_key(data, message_id)):
        return _ok({"duplicate": True})
    
    # extract reply/media once here

    if chat_id and chat_id in MONITORED_CHATS:
        q_text, q_id, m_urls = _extract_reply_and_media(data)
        snippet = (text or q_text or (m_urls[0] if m_urls else ""))
        save_text_message(chat_id, snippet, ts, message_id=message_id)
        logger.info("[saved] chat=%s ts=%s text=%r", chat_id, ts, snippet[:120])
        asyncio.create_task(
            _orders_worker(
                instance_id=instance_id,
                chat_id=chat_id,
                ts=ts or time.time(),
                text=(text or ""),  # empty string okay; extractor will short-circuit
                message_id=message_id,
                direction=direction,
                sender=sender,
                quoted_text=q_text,
                quoted_message_id=q_id,
                media_urls=m_urls,
            )
        )


    return _ok({"queued": True, "instance_id": instance_id, "chat_id": chat_id, "message_id": message_id})
