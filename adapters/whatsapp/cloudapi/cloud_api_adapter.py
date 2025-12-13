import os
import logging
import httpx
from dotenv import load_dotenv
from adapters.whatsapp.whatsapp_adapter import WhatsAppAdapter
from context.primitives.sender import SenderInfo
from context.primitives.replies_info import ContentInfo, ButtonReplyInfo, ListReplyInfo, ReplyContextInfo
from context.primitives.location import LocationInfo
from context.primitives.sender import SharedContactInfo, ReferralInfo
from context.primitives.media import MediaInfo
from context.message.raw_message import RawMessage, MessageDirection
from typing import Optional
import base64
import re
import unicodedata
import uuid
from adapters.whatsapp.cloudapi.message_index import MESSAGE_INDEX

load_dotenv(".venv/.env")

logger = logging.getLogger(__name__)

# ===== Confirmation marker (must match your prompt) =====
CONFIRM_MARK = "==yes_no_buttons_placeholder=="
CONFIRM_MARK_RE = re.compile(rf"(?:\r?\n)?{re.escape(CONFIRM_MARK)}\s*$")

def _has_confirm_mark(text: str) -> bool:
    return bool(CONFIRM_MARK_RE.search(text or ""))

def _strip_confirm_mark(text: str) -> str:
    return CONFIRM_MARK_RE.sub("", text or "").rstrip()

def _digits_only(phone_or_jid: str) -> str:
    # 360dialog wants bare E.164 digits for "to"
    return "".join(ch for ch in (phone_or_jid or "") if ch.isdigit())

def _normalize_spaces_no_diacritics(s: str) -> str:
    t = " ".join((s or "").strip().split())
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))

import re

def sanitize_param(value) -> str:
    if value is None:
        return ""
    value = str(value)
    value = re.sub(r"[\n\t]+", " ", value)
    value = re.sub(r" {5,}", "    ", value)
    return value.strip()


class CloudAPIAdapter(WhatsAppAdapter):
    def __init__(self):
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")

    async def _resolve_media_download_url(self, media_id: str) -> str | None:
        """GET /{media_id} -> {'url': ...}; short-lived. Only call when you truly need it."""
        token = getattr(self, "graph_token", None)
        if not token or not media_id:
            return None
        try:
            meta_url = f"https://graph.facebook.com/v16.0/{media_id}"
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(meta_url, headers={"Authorization": f"Bearer {token}"})
                r.raise_for_status()
                return r.json().get("url")
        except Exception:
            logger.exception("Failed to resolve media URL (media_id=%s)", media_id)
            return None

    async def parse_incoming(self, data: dict) -> Optional[RawMessage]:
        try:
            entries = data.get("entry", [])
            if not entries:
                return None

            changes = entries[0].get("changes", [])
            if not changes:
                return None

            message_direction = self.detect_direction(data)
            if message_direction != MessageDirection.INCOMING:
                return None

            # prevent loopback (some stacks echo our own sends as messages)
            value = changes[0].get("value", {})
            messages = value.get("messages", [])
            if messages:
                from_user = messages[0].get("from")
                # Typically 'from' is the end-user MSISDN, not our phone_number_id.
                # Keep this as a guard in case your infra echoes.
                if from_user and from_user == getattr(self, "phone_number_id", None):
                    logger.info("Ignoring message from self (loopback)")
                    return None

            return await self.init_message_context(message_direction, data)

        except Exception:
            logger.exception("Error parsing incoming CloudAPI message")
            return None

    async def init_message_context(self, message_direction: str, data: dict) -> RawMessage:
        print("init_message_context")
        try:
            change = data.get("entry", [{}])[0].get("changes", [{}])[0]
            value = change.get("value", {})
            contact = value.get("contacts", [{}])[0]
            message = value.get("messages", [{}])[0]

            metadata = value.get("metadata", {})
            phone_number_id = (metadata.get("phone_number_id") or "").strip()
            print("phone_number_id", phone_number_id)

            sender_phone = (contact.get("wa_id") or message.get("from") or "").strip()
            sender_name = ((contact.get("profile") or {}).get("name") or "").strip()
            chat_id = sender_phone
            if not chat_id:
                logger.warning("Incoming message without resolvable chat_id; dropping. payload_id=%s", message.get("id"))
                return None

            sender = SenderInfo(
                phone=sender_phone,
                name=sender_name,
                chatId=chat_id,
                isSelfSender=False
            )
            print("sender", sender)

            msg_type = message.get("type")
            content = ContentInfo(type=msg_type)

            if msg_type == "text":
                content.text = message.get("text", {}).get("body", "")

            elif msg_type in ["image", "video", "audio", "document"]:
                media = message.get(msg_type, {}) or {}
                media_id = media.get("id")
                mime_type = media.get("mime_type")
                caption = media.get("caption")
                sha256 = media.get("sha256")

                # Keep the metadata endpoint; resolve to actual download URL only when needed.
                media_meta_url = f"https://graph.facebook.com/v16.0/{media_id}" if media_id else None

                content.media = MediaInfo(
                    url=media_meta_url,
                    mime_type=mime_type,
                    caption=caption,
                    sha256=sha256,
                    media_id=media_id
                )

                if media_id:
                    content.media.download_url = await self._resolve_media_download_url(media_id)

            elif msg_type == "location":
                loc = message.get("location", {}) or {}
                content.location = LocationInfo(
                    latitude=float(loc.get("latitude", 0.0)),
                    longitude=float(loc.get("longitude", 0.0)),
                    name=loc.get("name"),
                    address=loc.get("address")
                )

            elif msg_type == "interactive":
                interactive = message.get("interactive", {}) or {}
                itype = interactive.get("type")
                if itype == "button_reply":
                    btn = interactive.get("button_reply", {}) or {}
                    content.button_reply = ButtonReplyInfo(
                        payload=btn.get("id"),
                        text=btn.get("title")
                    )
                elif itype == "list_reply":
                    lst = interactive.get("list_reply", {}) or {}
                    content.list_reply = ListReplyInfo(
                        payload=lst.get("id"),
                        title=lst.get("title"),
                        description=lst.get("description")
                    )

            elif msg_type == "contacts":
                contact_info = message.get("contacts", [{}])[0]
                name = (contact_info or {}).get("name", {}) or {}
                phones = (contact_info or {}).get("phones", [{}]) or [{}]
                content.contact = SharedContactInfo(
                    formatted_name=name.get("formatted_name", ""),
                    first_name=name.get("first_name"),
                    last_name=name.get("last_name"),
                    phone=phones[0].get("phone") if phones else None
                )

            elif msg_type == "sticker":
                logger.info("Sticker message received — currently unsupported.")
                return None

            else:
                logger.warning(f"Unhandled message type: {msg_type}")
                return None

            # ---- Hydrate quoted reply context from our local index (set in webhook) ----
            ctx = (message or {}).get("context") or {}
            if ctx:
                quoted_id = ctx.get("id")
                quoted_from = ctx.get("from")
                rc = ReplyContextInfo(
                    quoted_message_id=quoted_id,
                    quoted_sender_phone=quoted_from
                )

                if quoted_id:
                    orig = MESSAGE_INDEX.get(quoted_id)
                    if orig:
                        otype = orig.get("type")
                        rc.original_type = otype

                        if otype == "text":
                            rc.original_text = ((orig.get("text") or {}).get("body")
                                                or orig.get("body") or "")
                        elif otype in ("image", "video", "audio", "document"):
                            om = orig.get(otype) or {}
                            omid = om.get("id")
                            rc.original_caption = om.get("caption")
                            rc.original_mime_type = om.get("mime_type")
                            rc.original_media_id = omid
                            # Optional: resolve short-lived download URL (if token present)
                            rc.original_media_url = await self._resolve_media_download_url(omid) if omid else None
                    else:
                        logger.info("Quoted message %s not found in index", quoted_id)

                content.reply_context = rc

            # Optional: referral (ad attribution)
            if "referral" in message:
                ref = message["referral"] or {}
                content.referral = ReferralInfo(
                    source_url=ref.get("source_url"),
                    source_type=ref.get("source_type"),
                    headline=ref.get("headline"),
                    body=ref.get("body"),
                    image_url=ref.get("image_url")
                )

            print("identity", sender)

            return RawMessage(
                sender=sender,
                content=content,
                chat_id=chat_id,
                direction=message_direction,
                message_data=message,
                idempotency_key=message.get("id"),
            )

        except Exception:
            logger.exception("Error building MessageState from CloudAPI data")
            raise

    async def send_confirm_buttons_meta(
    self,
    to_phone: str,
    body_text: str,
    confirmation_id: str | None = None
    ) -> dict:
        """
        Meta WhatsApp Cloud API endpoint:
        POST https://graph.facebook.com/{version}/{PHONE_NUMBER_ID}/messages

        Sends a text + two quick-reply buttons ("כן"/"לא") as an interactive message.

        Notes:
        - `to_phone` must be in international format digits (no '+' or spaces).
        - Uses X-Idempotency-Key with a stable confirmation_id to avoid duplicate sends.
        """
        import uuid
        import httpx
        import logging

        logger = logging.getLogger(__name__)

        # ---- Required config on `self` ----
        phone_number_id = getattr(self, "phone_number_id", None)
        access_token = getattr(self, "access_token", None)
        api_version = getattr(self, "graph_api_version", "v21.0")

        if not phone_number_id or not access_token:
            return {"status": "failed", "error": "missing_phone_number_id_or_token"}

        # Normalize recipient
        to_phone = "".join(ch for ch in (to_phone or "") if ch.isdigit())
        if not to_phone:
            return {"status": "failed", "error": "invalid_recipient"}

        if not confirmation_id:
            confirmation_id = f"cfm_{uuid.uuid4().hex[:8]}"

        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # helps dedupe if client retries
            "X-Idempotency-Key": confirmation_id,
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": f"{confirmation_id}__yes", "title": "כן"}},
                        {"type": "reply", "reply": {"id": f"{confirmation_id}__no",  "title": "לא"}}
                    ]
                }
            }
            # Optional: "recipient_type": "individual"
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                r = await client.post(url, headers=headers, json=payload)
                data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
                if r.status_code >= 400:
                    logger.error("❌ Cloud API error %s: %s", r.status_code, data)
                    return {"status": "failed", "error": data}
                # Typical success returns: {"messages":[{"id":"wamid.HBgM..."}]}
                return {"status": "sent", "response": data}
            except httpx.RequestError as e:
                logger.exception("🌐 HTTPX request failed")
                return {"status": "failed", "error": str(e)}


    async def send_message(self, recipient: str, message: str, reply_to: str | None = None) -> dict:
        print("Sending message to", recipient, "with message:", message)

         # Switch to buttons if final-confirm marker exists
        if _has_confirm_mark(message):
            clean = _strip_confirm_mark(message)
            confirmation_id = f"cfm_{uuid.uuid4().hex[:8]}"
            # Optionally cache: confirmation_id -> payload (recipient, clean text, etc.)
            return await self.send_confirm_buttons_meta(
                to_phone=_digits_only(recipient),
                body_text=clean,
                confirmation_id=confirmation_id
            )
        url = f"https://graph.facebook.com/v16.0/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient.replace("@c.us", ""),
            "type": "text",
            "text": {"body": message}
        }

        if reply_to:
            payload["context"] = {"message_id": reply_to}   
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            return {"status": "sent", "response": response.json()}
        else:
            logger.error(f"Failed to send message: {response.status_code} - {response.text}")
            return {"status": "failed", "error": response.text}

    async def send_template_message(self, recipient: str, parameters: list[str], template_name: str="scheduled_message1", language_code: str="he") -> dict:
        print("Sending template message to", recipient, "with template:", template_name)
        print("Parameters:", parameters)
        url = f"https://graph.facebook.com/v16.0/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        parameters = [
            sanitize_param(parameters[0]),
            sanitize_param(parameters[1]),
            sanitize_param(parameters[2]),
        ]

        payload = {
            "messaging_product": "whatsapp",
            "to": recipient.replace("@c.us", ""),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code
                },
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {
                                "type": "text",
                                "parameter_name": "recipient",
                                "text": parameters[0]
                            },
                            {
                                "type": "text",
                                "parameter_name": "sender",
                                "text": parameters[1]
                            },
                            {
                                "type": "text",
                                "parameter_name": "text",
                                "text": parameters[2]
                            }          
                        ]
                    }
                ]
            }
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                return {"status": "sent", "response": response.json()}
            else:
                logger.error(f"Failed to send template message: {response.status_code} - {response.text}")
                return {"status": "failed", "error": response.text}

    def get_identity(self, webhook_uid: str) -> dict:
        return {
            "phone": self.phone_number_id
        }

    def detect_direction(self, data: dict) -> str:
        try:
            change = data.get("entry", [{}])[0].get("changes", [{}])[0]
            value = change.get("value", {})
            if "messages" in value:
                return MessageDirection.INCOMING
            if "statuses" in value:
                return MessageDirection.OUTGOING
            return MessageDirection.UNKOWN
        except Exception:
            return MessageDirection.UNKOWN

    async def send_image_base64(self, recipient: str, image_base64: str, filename: str = "qr.png", caption: str = None):
        # Step 1: Upload image to get media ID
        media_id = await self._upload_image(image_base64, filename)
        if not media_id:
            return {"status": "failed", "error": "Upload failed"}

        # Step 2: Send the image using media ID
        url = f"https://graph.facebook.com/v16.0/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient.replace("@c.us", ""),
            "type": "image",
            "image": {
                "id": media_id
            }
        }
        if caption:
            payload["image"]["caption"] = caption

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            return {"status": "sent", "response": response.json()}
        else:
            logger.error(f"Failed to send image: {response.status_code} - {response.text}")
            return {"status": "failed", "error": response.text}

    async def _upload_image(self, image_base64: str, filename: str) -> str:
        url = f"https://graph.facebook.com/v16.0/{self.phone_number_id}/media"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        image_bytes = base64.b64decode(image_base64)
        files = {
            "file": (filename, image_bytes, "image/png"),
            "messaging_product": (None, "whatsapp")
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, files=files)

        if response.status_code == 200:
            return response.json().get("id")
        else:
            logger.error(f"Failed to upload image: {response.status_code} - {response.text}")
            return None
