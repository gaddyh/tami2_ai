

from agent.order.prompts import GENERIC_MATCH_PROMPT
from openai import AsyncOpenAI
from store.customer_aliases_store import get_customer_canonical_name
from store.product_aliases_store import get_canonical_product
from typing import Optional
import json
import re
client = AsyncOpenAI()

import asyncio
import random


# add cache for previous searches
async def match_entity(entity_type: str, message: str, list_text: str, customer_id: Optional[str] = None):
    print(f"Matching {entity_type} for {message}")

    if entity_type == "customer":
        canonical_name = get_customer_canonical_name(message)
        if canonical_name:
            return {
                "matched_name": canonical_name,
                "confidence": 1.0,
            }

    prompt = GENERIC_MATCH_PROMPT\
        .replace("{{ENTITY_TYPE}}", entity_type)\
        .replace("{{ORIGINAL_MESSAGE}}", message)\
        .replace("{{LIST_TEXT}}", list_text)

    response = await client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "system", "content": prompt}],
    )
    print(f"Matched {entity_type} for {message}: {response.choices[0].message.content}")
    content = response.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON substring (if model wrapped it in text)
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    print(f"content: {content}")
    return content

def try_default(entity_type: str, message: str, customer_id: Optional[str] = None):
    if entity_type == "customer":
        return get_customer_canonical_name(message)
    if entity_type == "product":
        return get_canonical_product(message, customer_id=customer_id)
    return None