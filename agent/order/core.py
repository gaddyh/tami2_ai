
from context.primitives.replies_info import ContentInfo
from shared.google_sheets.helper import _send_orders_async
from agent.order.formatter_agent import extract_orders_format_from_message
from agent.order.match_agent import match_entity, try_default
from agent.order.file_helper import CUSTOMERS_STRING, PRODUCTS_STRING
from agent.order.json_models import FormatterPayload
from typing import Optional, Dict, Any
from green_api.ledger_item import extract_ledger_from_message, _send_orders_async2
import logging
import json
from agent.order.file_helper import CUSTOMERS
logger = logging.getLogger(__name__)

async def sendToGoogleSheets(content: ContentInfo):
    notes = ""
   # current message
    if content.media:
        notes = content.media.download_url or content.media.url or ""
    if content.text:
        notes = (notes + "\n" if notes else "") + content.text.removeprefix("stt:").removeprefix("text:")
    if content.reply_context:
        notes += ("\n" + str(content.reply_context.original_text)) if content.reply_context.original_text else ""
        notes += ("\n" + str(content.reply_context.original_media_url)) if content.reply_context.original_media_url else ""
    payload = {
            "orders": [{
                "טקסט מקורי": content.text.removeprefix("stt: ") if content.text else "",
                "שם לקוח": "",
                "מוצר": None,
                "כמות": None,
                "מארז": None,
                "סוג הובלה": None,
                "יעד": None,
                "הערות": notes,
            }]
        }

    sent_ok = await _send_orders_async(payload)
    return sent_ok 

def _to_int_or_none(x):
    try:
        return int(str(x).strip())
    except Exception:
        return None

import re
from agent.order.file_helper import get_customer_id_by_name, get_product_id_by_name
async def extract_orders_from_message(text: str) -> Optional[Dict[str, Any]]:

    #step 1: extract order format
    print(f"extracting order format from {text}")
    order_format = await extract_orders_format_from_message(text=text)
    if order_format is None:
        return None
    
    payload = FormatterPayload(**order_format)
    payload.original_text = text
    
    print(f"extracted order format: {payload}")
    customer = payload.customer_span
    if customer is None:
        return None

    #step 2: extract customer
    customer_match = await match_entity("customer", customer or "", CUSTOMERS_STRING)
    if customer_match is None:
        return None
    
    cid = None
    confidence = float(customer_match.get("confidence", 0) or 0)
    reason = customer_match.get("reason") or None
    customer_match = customer_match.get("matched_name") if confidence > 0.8 else None
   
    if customer_match:
        payload.customer_matched = customer_match
        cid = _to_int_or_none(get_customer_id_by_name(customer_match))
        print(f"cid: {cid}")
        payload.customer_id = cid
        row = CUSTOMERS.get(cid) if cid is not None else None
        print(f"row: {row}")
        # defensive: never chain on None
        payload.destination_matched = (row or {}).get("address", "")
        print(f"destination_matched: {payload.destination_matched}")
    else:
        if reason:
            payload.customer_matched = reason
    #step 3: extract order items
    items = payload.line_items
    if items is None:
        return None
    
    for item in items:
        product = item.product_span
        if not product:
            continue
        product_alias = try_default("product", product) # get product alias: גרנולה - גרנולה 12 
        if product_alias:
            product_alias = product_alias.get("canonical_product_name")
        else:
            product_alias = product
        print(f"product_alias: {product_alias}, product: {product}")
        packaging = item.packaging_span
        if packaging == "משטח" or packaging is None:
            item.packaging_span = "מארז קטן"
            if item.packaging_span not in product_alias :
                product_alias += " " + item.packaging_span
        elif packaging == "ביג" or packaging == "מארזים" or packaging == "ביגבג" or packaging == "משטחים" or packaging == "מארז":
            item.packaging_span = "מארז גדול"
            if item.packaging_span not in product_alias :
                product_alias += " " + item.packaging_span
        product_match = await match_entity("product", product_alias or "", PRODUCTS_STRING, cid)
        if product_match is None:
            return None

        item.product_matched = product_match.get("matched_name") if float(product_match.get("confidence", 0) or 0) > 0.8 else product_alias
        item.product_id_matched = get_product_id_by_name(item.product_matched)
        print(f"product_match: {item.product_matched}, product: {product}")

    await _send_orders_async2(payload)
    return payload
    input = f"""
        RAW_MESSAGE:
        {text}

        HINTS:
        {payload}
    """

    print(f"input: {input}\n\n")
    ledger = await extract_ledger_from_message(text=input, chat_id="", ts=0, original_text=text)
    if ledger is None:
        return None
    print(f"ledger: {ledger}")
    logger.info(f"order ledger: {ledger}")
    return ledger

async def main():
    #message = "שלום דמתי\n2 משטח 4 6\nמשטח יונקים"
    #payload = await extract_orders_from_message(message)
    #print(f"payload: {payload}")

    message = """
 פייגין,
בקר טוב  10     4.6 בבקשה
    """

    payload = await extract_orders_from_message(message)
    print(f"payload: {payload}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
    