# ledger_extractor.py
from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional, Union, Sequence

from dotenv import load_dotenv
from openai import AsyncOpenAI
import httpx

import asyncio
from datetime import datetime
from shared.time import to_user_timezone

load_dotenv(".venv/.env")

logger = logging.getLogger(__name__)
client = AsyncOpenAI()

# ---- JSON Schema: object with "orders" (array) ----
ORDERS_JSON_SCHEMA = {
    "name": "orders_payload",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "orders": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "טקסט מקורי": {"type": "string"},
                        "שם לקוח": {"type": ["string", "null"]},
                        "מוצר": {"type": ["string", "null"]},
                        "כמות": {"type": "integer", "minimum": 1},
                        "מארז": {"type": ["string", "null"]},
                        "סוג הובלה": {"type": ["string", "null"]},
                        "יעד": {"type": ["string", "null"]},
                        "הערות": {"type": ["string", "null"]}
                    },
                    "required": ["טקסט מקורי", "שם לקוח", "מוצר", "כמות", "מארז", "סוג הובלה", "יעד", "הערות"]
                }
            }
        },
        "required": ["orders"]
    }
}
SYSTEM_PROMPT = """
You are **Order Extractor**, a deterministic parser for WhatsApp/SMS purchase messages in Hebrew/English (incl. code-switching and typos).
You receive:
1) RAW_MESSAGE: the original text from the user (unaltered).
2) HINTS: a structured object produced by earlier matchers with fields:
   - customer_span: string|null
   - customer_matched: JSON string|null of shape:
       {
         "entity_type": "customer",
         "original_span": "<string>",
         "matched_id": "<string>",
         "matched_name": "<string>",
         "confidence": <float 0..1>,
         "alternates": ["<id:name>", ...]
       }
   - destination_span: string|null
   - destination_matched: the destination address of the customer
       
   - transportation_span: string|null
   - line_items: array of objects each with:
       - product_span: string|null
       - product_matched: string|null
       - packaging_span: string|null
       - quantity_span: string|null

   - prefer matched fields over spans

Return **one JSON object** with a single key "orders" whose value is an **array of order objects**.
Do not chat, do not explain, return only the JSON.

## Output (hard contract)
{
  "orders": [
    {
      "טקסט מקורי": "<original text of the specific line item>",
      "שם לקוח": "<string|null>",
      "מוצר": "<string|null>",
      "כמות": <integer>,
      "מארז": "<string|null>",
      "סוג הובלה": "<string|null>",
      "יעד": "<string|null>",
      "הערות": "<string|null>"
    }
  ]
}

## Deterministic policy: trust HINTS first
- Parse any JSON strings in HINTS (customer_matched, product_matched) into objects.
- **Customer**:
  - If customer_matched.matched_name exists with confidence ≥ 0.80 → use that exact name for "שם לקוח".
  - Else if customer_span is clearly a single name and consistent with RAW_MESSAGE → use it.
  - Else → null.
- **Product** (per line item):
  - If product_matched.matched_name exists with confidence ≥ 0.75 → use that exact name for "מוצר".
  - If multiple alternates exist but confidence < threshold or near-ties remain → set מוצר = null.
  - If no product_matched and product_span is unambiguous in RAW_MESSAGE → use normalized product_span; else null.
- **Do NOT invent or search beyond HINTS**. If uncertain, use null.

## Field rules
- **"כמות"**:
  - If quantity_span is a valid integer → use it, unless the product name has the same number.
  - If none found → 1.
- **"מארז"**:
  - Normalize common forms to singulars (e.g., "שקים"→"שק", "ביג"→"ביגבג", "באלות"→"מארז" only if truly generic).
  - If size/weight appears, include with the packaging (e.g., "שק 25 ק\"ג", "ביגבג 1 טון").
  - If nothing reliable → null.
- **"סוג הובלה"**:
  - Prefer transportation_span if present and meaningful (e.g., "משלוח", "איסוף עצמי", "מנוף").
  - Otherwise infer from RAW_MESSAGE if explicit; else null.
- **"יעד"**:
  - Prefer destination_span if present; otherwise use destination_matched if present; else infer only if clearly stated; else null.
- **"הערות"**:
  - Freeform extras (זמני אספקה, שער, טלפון איש קשר, הוראות מיוחדות) if explicitly present; else null.

## Splitting into multiple orders
- Produce **one object per line item** in HINTS.line_items.
- Copy shared fields (שם לקוח, יעד, סוג הובלה, הערות כלליות) consistently to each relevant object.
- Respect per-item packaging/quantity from each line item.

## Pre-Processing (minimal typo fixing)
- Apply only minimal normalization needed to interpret numbers, packaging, and obvious typos.
- Preserve original line in "טקסט מקורי" for traceability.
- Do not rewrite product/customer names that come from matched_name; use them verbatim if selected by the confidence rules.

## Confidence & ambiguity
- If confidence thresholds are not met or contradictions exist → prefer null for that field.
- No hallucinations. Output only what is grounded in RAW_MESSAGE or in HINTS with sufficient confidence.

## Example — based on provided HINTS
RAW_MESSAGE:
"טואטי השקעות
משטח גרנולה "

HINTS:
customer_span='עמית דותן'
customer_matched='{
  "entity_type": "customer",
  "original_span": "טואטי השקעות",
  "matched_id": "702370",
  "matched_name": "השקעות טואטי ב.א בע"מ - עין ורד",
  "confidence": 0.92,
  "alternates": []
}'
destination_span=null
destination_matched="עין ורד"
transportation_span=null
line_items=[
  {
    "product_span":"גרנולה",
    "product_matched":"גרנולה 12",
    "packaging_span":"משטח",
    "quantity_span":12,
  }
]

Output:
{
  "orders": [
    {
      "טקסט מקורי": "משטח גרנולה 12",
      "שם לקוח": "השקעות טואטי ב.א בע"מ - עין ורד",
      "מוצר": "גרנולה 12",
      "כמות": 1,
      "מארז": "משטח",
      "סוג הובלה": null,
      "יעד": "עין ורד",
      "הערות": null
    }
  ]
}
"""


WEB_APP_URL = "https://script.google.com/macros/s/AKfycbw7FpjBNoUvpg93Vecxwq-mVU56E1R2WyrpEOTwdjZg4qKoI5GhZqsEViv0m1bhP6U/exec"


def _to_int_maybe(n: Union[int, float, str, None]) -> Optional[int]:
    if n is None or isinstance(n, bool):
        return None
    if isinstance(n, int):
        return n
    if isinstance(n, float):
        try:
            return int(n)
        except Exception:
            return None
    if isinstance(n, str):
        s = n.strip()
        if not s:
            return None
        try:
            return int(s)
        except Exception:
            try:
                return int(float(s))
            except Exception:
                return None
    return None

# --- put these near your other imports ---
import os, json, logging, asyncio
from datetime import datetime
from typing import Any, Dict, List

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# === CONFIG ===
SPREADSHEET_ID = "1660DyXD8JYdUxj7-BWLtUnsHAC14-GT_SW2vAwUOvmA"      # <-- paste the target sheet id
SHEET_NAME     = "Sheet1"                   # <-- tab name
#SHEET_NAME2    = "Sheet2"                   # <-- tab name
SHEET_NAME2    = "SheetTest"                   # <-- tab name
EXPECTED_HEADERS = [
    "טקסט מקורי","שם לקוח","מוצר","כמות","מארז","סוג הובלה","יעד","הערות","נוצר ב",
]
EXPECTED_HEADERS2 = [
    "טקסט","שם לקוח מטקסט","שם לקוח רשמי","מזהה לקוח","שם מוצר מטקסט","שם מוצר רשמי","מזהה מוצר","כמות מטקסט","כמות","מארז","סוג הובלה","יעד","הערות","נוצר ב","הוזן",
]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# === AUTH: service account via file path or env var ===
_svc = None
def _sheets_service():
    secrets_dir = os.getenv("SECRETS_DIR", ".secrets")
    creds_path = os.path.join(secrets_dir, "sheets.json")
    global _svc
    if _svc:
        return _svc
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # falls back to GOOGLE_APPLICATION_CREDENTIALS file path
        creds = Credentials.from_service_account_file(
           creds_path, scopes=SCOPES
        )
    _svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return _svc

def _orders_to_rows(payload: Dict[str, Any]) -> List[List[Any]]:
    """Map payload['orders'] -> rows in EXACT EXPECTED_HEADERS order with safe defaults."""
    orders = payload.get("orders") or []
    now_iso = to_user_timezone(datetime.now()).isoformat()
    rows: List[List[Any]] = []
    for o in orders:
        # normalize per row
        if not isinstance(o, dict):
            continue
        o.setdefault("טקסט מקורי", "")
        o.setdefault("שם לקוח", None)
        o.setdefault("מוצר", None)
        o.setdefault("כמות", 1)
        o.setdefault("מארז", None)
        o.setdefault("סוג הובלה", None)
        o.setdefault("יעד", None)
        o.setdefault("הערות", None)
        o.setdefault("נוצר ב", now_iso)

        # coerce quantity to int >= 1
        try:
            q = int(o.get("כמות") or 1)
            if q < 1: q = 1
            o["כמות"] = q
        except Exception:
            o["כמות"] = 1

        # build row by header order
        row = [(o[h] if o[h] is not None else "") for h in EXPECTED_HEADERS]
        rows.append(row)
    return rows

def _orders_to_rows2(payload: dict) -> List[List[Any]]:
    """Map payload -> rows in EXACT EXPECTED_HEADERS2 order with safe defaults."""
    import json
    from datetime import datetime

    def g(obj, key, default=None):
        if obj is None: return default
        if isinstance(obj, dict): return obj.get(key, default)
        return getattr(obj, key, default)

    now_iso = to_user_timezone(datetime.now()).isoformat()

    # Root/customer fields
    original_text = g(payload, "original_text")
    cust_span = g(payload, "customer_span")
    cust_name_official = g(payload, "customer_matched")
    cust_id = g(payload, "customer_id")

    dest = g(payload, "destination_matched") or g(payload, "destination_span")
    transport = g(payload, "transportation_matched") or g(payload, "transportation_span")
    notes = g(payload, "notes_span") or ""

    rows: List[List[Any]] = []
    for item in g(payload, "line_items", []) or []:
        prod_span = g(item, "product_span")
        prod_match = g(item, "product_matched")
        prod_id_matched = g(item, "product_id_matched")

        # Resolve official product name + id
        prod_name_official, prod_id = None, None
        if isinstance(prod_match, dict):
            prod_name_official = prod_match.get("matched_name") or prod_match.get("name")
            prod_id = prod_match.get("matched_id") or prod_match.get("id")
        else:
            prod_name_official = prod_match  # string like "עגלות 4-6 מארז קטן"

        # product_id preference: explicit field > dict-derived > None
        if prod_id_matched not in (None, ""):
            prod_id = prod_id_matched

        qty_text = g(item, "quantity_span")
        try:
            q = int(str(qty_text).strip()) if qty_text not in (None, "") else 1
            if q < 1: q = 1
        except Exception:
            q = 1

        packaging = g(item, "packaging_span")

        o = {
            "טקסט": original_text,
            "שם לקוח מטקסט": cust_span,
            "שם לקוח רשמי": cust_name_official,
            "מזהה לקוח": cust_id,
            "שם מוצר מטקסט": prod_span,
            "שם מוצר רשמי": prod_name_official,
            "מזהה מוצר": prod_id,
            "כמות מטקסט": qty_text,
            "כמות": q,
            "מארז": packaging,
            "סוג הובלה": transport,
            "יעד": dest,
            "הערות": notes,
            "נוצר ב": now_iso,
            "הוזן": None,
        }

        if o["שם מוצר מטקסט"] is not None:
            rows.append([(o[h] if o[h] is not None else "") for h in EXPECTED_HEADERS2])

    return rows


def _append_rows_sync(rows: List[List[Any]]) -> bool:
    """Blocking Sheets API call (runs in thread)."""
    if not rows:
        logger.info("[sheets] no rows to write")
        return True
    svc = _sheets_service()
    rng = f"{SHEET_NAME}!A1"   # append ignores start cell; header expected in row 1
    body = {
        "range": rng,
        "majorDimension": "ROWS",
        "values": rows,
    }
    try:
        resp = (
            svc.spreadsheets()
            .values()
            .append(
                spreadsheetId=SPREADSHEET_ID,
                range=rng,
                valueInputOption="USER_ENTERED",   # respects checkbox/number formatting
                insertDataOption="INSERT_ROWS",
                includeValuesInResponse=False,
                body=body,
            )
            .execute()
        )
        updates = ((resp or {}).get("updates") or {})
        written = updates.get("updatedRows", 0)
        logger.info("[sheets] appended rows=%s", written)
        return bool(written)
    except HttpError as e:
        logger.exception("[sheets] HttpError: %s", getattr(e, "content", e))
        return False
    except Exception as e:
        logger.exception("[sheets] unexpected error: %s", e)
        return False



def _append_rows_sync2(rows: List[List[Any]]) -> bool:
    """Blocking Sheets API call (runs in thread)."""
    if not rows:
        logger.info("[sheets] no rows to write")
        return True
    svc = _sheets_service()
    rng = f"{SHEET_NAME2}!A1"   # append ignores start cell; header expected in row 1
    body = {
        "range": rng,
        "majorDimension": "ROWS",
        "values": rows,
    }
    try:
        resp = (
            svc.spreadsheets()
            .values()
            .append(
                spreadsheetId=SPREADSHEET_ID,
                range=rng,
                valueInputOption="USER_ENTERED",   # respects checkbox/number formatting
                insertDataOption="INSERT_ROWS",
                includeValuesInResponse=False,
                body=body,
            )
            .execute()
        )
        updates = ((resp or {}).get("updates") or {})
        written = updates.get("updatedRows", 0)
        logger.info("[sheets] appended rows=%s", written)
        return bool(written)
    except HttpError as e:
        logger.exception("[sheets] HttpError: %s", getattr(e, "content", e))
        return False
    except Exception as e:
        logger.exception("[sheets] unexpected error: %s", e)
        return False

# === REPLACEMENT for your previous webhook POST ===
async def _send_orders_async(payload: Dict[str, Any]) -> bool:
    """Append payload['orders'] to Google Sheet via Sheets API (service account)."""
    try:
        rows = _orders_to_rows(payload)
        # run blocking client in a worker thread
        return await asyncio.to_thread(_append_rows_sync, rows)
    except Exception as e:
        logger.exception("[sheets] send failed: %s", e)
        return False

async def _send_orders_async2(payload: Dict[str, Any]) -> bool:
    """Append payload['orders'] to Google Sheet via Sheets API (service account)."""
    try:
        rows = _orders_to_rows2(payload)
        # run blocking client in a worker thread
        print("[sheets] appending rows=%s", rows)
        return await asyncio.to_thread(_append_rows_sync2, rows)
    except Exception as e:
        logger.exception("[sheets] send failed: %s", e)
        return False

async def extract_ledger_from_message(
    *,
    chat_id: str,
    ts: float,
    text: str,
    original_text: Optional[str] = None,
    instance_id: Optional[str] = None,
    message_id: Optional[str] = None,
    provider: Optional[str] = None,
    direction: Optional[str] = None,
    sender: Optional[str] = None,
    quoted_text: Optional[str] = None,
    quoted_message_id: Optional[str] = None,
    media_urls: List[str] = [],
) -> Optional[Dict[str, Any]]:
    preview = (text[:200] + "…") if len(text) > 200 else text
    logger.info("[ledger] Extracting orders from message: %s", preview)

    # just before the LLM call inside extract_ledger_from_message(...)
    safe_text = (text or "").strip()
    if not safe_text:
        context_bits: List[str] = []
        if quoted_text:
            context_bits.append(f"reply_to: {quoted_text}")
        if quoted_message_id:
            context_bits.append(f"reply_id: {quoted_message_id}")
        if media_urls:
            context_bits.append("media: " + ", ".join(media_urls))
        notes = " | ".join(context_bits) if context_bits else None

        payload = {
            "orders": [{
                "טקסט מקורי": "",
                "שם לקוח": None,
                "מוצר": None,
                "כמות": 1,
                "מארז": None,
                "סוג הובלה": None,
                "יעד": None,
                "הערות": notes,
            }]
        }
        print("[extractor] no-text fast path; notes:", notes)  # <-- debug
        sent_ok = await _send_orders_async(payload)
        return payload if sent_ok else None

    # --- LLM call ---
    try:
        resp = await client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_schema", "json_schema": ORDERS_JSON_SCHEMA},
        )
    except Exception as e:
        logger.exception("[ledger] OpenAI call failed: %s", e)
        return None

    raw = (resp.choices[0].message.content or "").strip()
    if not raw:
        logger.warning("[ledger] Empty model content.")
        # send a single row with just the original text
        return await _send_orders_async({"orders": [{"טקסט מקורי": text}]})

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("[ledger] Failed to parse JSON: %r", raw[:500])
        # fall back to a single row with just the original text
        return await _send_orders_async({"orders": [{"טקסט מקורי": text}]})

    orders = payload.get("orders", [])
    # normalize: enforce keys and default quantity
    norm_orders: List[Dict[str, Any]] = []
    for o in orders:
        if not isinstance(o, dict):
            continue
        for k in ["טקסט מקורי", "שם לקוח", "מוצר", "כמות", "מארז", "סוג הובלה", "יעד", "הערות"]:
            o.setdefault(k, None)
        o["טקסט מקורי"] = original_text  # ensure original text always there
        qty = _to_int_maybe(o.get("כמות"))
        o["כמות"] = 1 if (qty is None or qty < 1) else qty
        context_bits: List[str] = []
        if quoted_text:
            context_bits.append(f"reply_to: {quoted_text}")
        if quoted_message_id:
            context_bits.append(f"reply_id: {quoted_message_id}")
        if media_urls:
            context_bits.append("media: " + ", ".join(media_urls))

        if context_bits:
            ctx = " | ".join(context_bits)
            for o in norm_orders:
                if o.get("הערות"):
                    o["הערות"] = f'{o["הערות"]} | {ctx}'
                else:
                    o["הערות"] = ctx
        
        norm_orders.append(o)

    # if LLM gave zero orders, still send a dummy row with only original text
    if not norm_orders:
        norm_orders = [{"טקסט מקורי": text, "שם לקוח": None, "מוצר": None,
                        "כמות": 1, "מארז": None, "סוג הובלה": None, "יעד": None, "הערות": None}]

    normalized_payload = {"orders": norm_orders}
    sent_ok = await _send_orders_async(normalized_payload)
    if not sent_ok:
        logger.error("[ledger] Failed to send row to Apps Script.")
        return None
    return normalized_payload




async def test_send_orders():
    payload = {
        "orders": [
            {
                "טקסט מקורי": "2 משטח 4 6",
                "שם לקוח": "שותפות דמתי",
                "מוצר": "4 6",
                "כמות": 2,
                "מארז": "משטח",
                "סוג הובלה": None,
                "יעד": None,
                "הערות": None,
                "נוצר ב": to_user_timezone(datetime.now()).isoformat(),
            }
        ]
    }
    ok = await _send_orders_async(payload)
    print("✅ Sent orders successfully" if ok else "❌ Failed to send orders")

import asyncio, time

async def test_extract_ledger_from_message():
    msgs = [
        # multi-product
        "שותפות דמתי\n2 משטח 4 6\nמשטח יונקים",
        # single product, with packaging & qty implicit
        "עמית דותן\nמשטח אמאהות",
        # no recognizable order -> should still send a single row with טקסט מקורי only
        "היי, מחר אגיע מאוחר. תודה!",
        "שלום דמתי\nמשטח יונקים\n3 משטח 4 6",
        "מבקש להזמין משטח יונקים\nמשטח 4-6\nסגלצ'יק",
        "הזמנה\nיאיר ברקוביץ\n10 שקים 4-6\n20 שקים יונקים",
        "הזמנה\nלייכט\n3 ביגבג יונקים\nדחוף",
        "רהט בא לעמיס\n10 אמאהות\n2 גרנולה 11\n2 דגן מקוצץ\nמשטח שעורה לחןצה",
        "סמיר פקולטה לשבוע הבא 10 מארזים\nביגבג לפינוי",
    ]

    for i, text in enumerate(msgs, 1):
        print(f"\n--- TEST {i} ---")
        payload = await extract_ledger_from_message(
            chat_id="chat123",
            ts=time.time(),
            text=text,
            instance_id="instA",
            message_id=f"m{i}",
            provider="green-api",
            direction="inbound",
            sender="גדי",
        )
        if payload is None:
            print("❌ extract_ledger_from_message returned None (send failed)")
        else:
            print("✅ sent. normalized payload:")
            print(payload)

if __name__ == "__main__":
    asyncio.run(test_extract_ledger_from_message())


