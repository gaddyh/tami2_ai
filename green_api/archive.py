# archive.py
from __future__ import annotations
import hashlib, json, logging, time
from typing import Any, Dict, Optional
from db.base import db

logger = logging.getLogger(__name__)

def make_doc_id(instance_id: Optional[str], chat_id: str, message_id: Optional[str], ts: float) -> str:
    base = f"{(instance_id or 'default').strip()}:{chat_id.strip()}"
    return f"{base}:{(message_id or str(int(ts))).strip()}"

def _sha1(obj: Dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

def save_message_archive(
    *,
    instance_id: Optional[str],
    chat_id: str,
    message_id: Optional[str],
    provider: Optional[str],
    direction: Optional[str],      # "inbound" | "outbound"
    sender: Optional[str],
    ts: float,
    content: Dict[str, Any],       # {"text":..., "asr_text":..., "ocr_text":..., "attachments":[...] }
    classification: Optional[Dict[str, Any]] = None,  # your LLM JSON or None
    processing: Optional[Dict[str, Any]] = None,      # {"ok":True, "model":"gpt-4o-mini", "latency_ms":...}
) -> str:
    """Idempotent upsert of a message archive document."""
    now = int(time.time() * 1000)
    doc_id = make_doc_id(instance_id, chat_id, message_id, ts)

    doc = {
        "instance_id": instance_id,
        "chat_id": chat_id,
        "message_id": message_id,
        "provider": provider,
        "direction": direction,
        "sender": sender,
        "ts": ts,
        "content": content,
        "classification": classification,   # may be None if you save pre-LLM and update later
        "processing": processing,
    }
    doc["hash"] = _sha1({
        "content": content,
        "classification": classification,
        "sender": sender,
        "ts": ts,
    })
    doc["updated_at_ms"] = now

    # Use set(merge=True) so you can first write raw, then update with classification.
    db.collection("messages").document(doc_id).set(doc, merge=True)

    # optional per-chat mirror
    # db.collection("chats").document(chat_id).collection("messages").document(doc_id).set(doc, merge=True)

    logger.info("[archive] saved messages/%s (merge)", doc_id)
    return doc_id
