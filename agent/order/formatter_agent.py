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
from agent.order.prompts import FORMAT_ORDER_MESSAGE_PROMPT
from agent.order.json_models import FORMATTER_JSON_SCHEMA

load_dotenv(".venv/.env")

logger = logging.getLogger(__name__)
client = AsyncOpenAI()


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

logger = logging.getLogger(__name__)

async def extract_orders_format_from_message(
    *,
    text: str,
) -> Optional[Dict[str, Any]]:
    preview = (text[:200] + "…") if len(text) > 200 else text
    logger.info("[orders] Extracting orders from message: %s", preview)

    # just before the LLM call inside extract_orders_from_message(...)
    safe_text = (text or "").strip()
    if not safe_text:
        return None

    # --- LLM call ---
    try:
        resp = await client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": FORMAT_ORDER_MESSAGE_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_schema", "json_schema": FORMATTER_JSON_SCHEMA},
        )
    except Exception as e:
        logger.exception("[orders] OpenAI call failed: %s", e)
        return None

    raw = (resp.choices[0].message.content or "").strip()
    if not raw:
        logger.warning("[orders] Empty model content.")
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("[orders] Failed to parse JSON: %r", raw[:500])
        return None

    line_items = payload.get("line_items", [])
    if line_items is None:
        return None
    # we allow zero line items if we just extracted customer name
    return payload


def print_order_result(test_number, text, payload):
    print(f"--- TEST {test_number} ---")
    print(f"📩 Original message:")
    print(text)
    print(f"\n🧾 Extracted JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}")
    print("\n" + "-" * 40 + "\n")

async def test_extract_orders_from_message():
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
        print(f"\n--- TEST {i} ---\ntext: {text}")
        payload = await extract_orders_format_from_message(
            text=text,
        )
        if payload is None:
            print("❌ extract_orders_from_message returned None (send failed)")
        else:
            print_order_result(i, text, payload)

if __name__ == "__main__":
    asyncio.run(test_extract_orders_from_message())


