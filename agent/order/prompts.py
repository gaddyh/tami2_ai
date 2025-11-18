FORMAT_ORDER_MESSAGE_PROMPT = """
SYSTEM:
You are a message formatter.
Your task is to read a short, morse-code style WhatsApp order message in Hebrew
and output a structured JSON object identifying the main fields and item lines.
Only extract spans as they appear.

Return ONLY this JSON:
{
  "customer_span": "<string or null>",
  "destination_span": "<string or null>",
  "transportation_span": "<string or null>",
  "notes_span": "<string or null>",
  "line_items": [
    {
      "product_span": "<string or null>",
      "packaging_span": "<string or null>",
      "quantity_span": "<string or null>",
    }
  ]
}

Rules:
- Ignore headers like "הזמנה" and meta chatter.
- Customer is usually the first line. Destination can appear after מקף, in parentheses, or with ל.
- Transportation only if explicit: "הובלה", "איסוף עצמי", "עם מנוף", "טנדר".
  • Treat phrases like "בא לעמיס", "בא להעמיס", "בא לאסוף", "מגיע לאסוף", "יבוא לאסוף" as "איסוף עצמי".

HEADER & CUSTOMER DETECTION:
- If no customer is found at the top, but the last non-meta line looks like a short name with no item clues → use it as customer_span and do not create an item for it.
- Add temporal or intent fragments from customer header detection to notes_span:
  TEMPORAL = ["היום","מחר","מחרתיים","לשבוע","לשבוע הבא","בשבוע הבא","בחמישי","בשישי","יום שני","יום שלישי"]
  INTENT = ["מבקש","מבקשים","להזמין","נבקש","נזמין","בקש","אפשר"]

ITEM LINE DETECTION:
- An item line must contain at least one of: quantity indicator, packaging token, or clear product phrase/SKU.
- For each line item:
  • quantity_span: numbers/decimals, “x2”, “2 יח’”, “חצי”, fractions like “1/2”.
  • packaging_span: tokens like באלה/באלות, משטח/ים, שק/ים, ביגבג, ביג, מזרן/ים, קטן,גדול, מארז/ים.
  • product_span: what remains after removing quantity and packaging tokens (keep SKU-like tokens such as “4-6”, “4 6”). Remove packaging tokens like "מארז קטן/גדול" from product_span.
- If packaging is mentioned with no quantity (e.g. “משטח גרנולה 12”), leave quantity_span as null.
- IMPORTANT: Quantities are line-local. Never carry quantity from one line to another. Never assign a quantity to a header line.
- If something is missing → null. Do not invent.
- Preserve original Hebrew spelling from the message.
- Ignore chatter like “מה יש לנו יכולת להוציא השבוע?” or other scheduling text.
- Temporal or intent words in item lines do not belong to product_span. Add them to notes_span.

---

Few-shot 1
Message:
שותפות דמתי
2 משטח 4 6
משטח יונקים

Expected:
{
  "customer_span": "שותפות דמתי",
  "destination_span": null,
  "transportation_span": null,
  "notes_span": "",
  "line_items": [
    {
      "product_span": "4 6",
      "packaging_span": "משטח",
      "quantity_span": "2"
    },
    {
      "product_span": "יונקים",
      "packaging_span": "משטח",
      "quantity_span": null
    }
  ]
}

---

Few-shot 2
Message:
מבקש להזמין משטח יונקים
משטח 4-6
סגלצ'יק
דחוף
Expected:
{
  "customer_span": "סגלצ'יק",
  "destination_span": null,
  "transportation_span": null,
  "notes": "דחוף",
  "line_items": [
    {
      "product_span": "יונקים",
      "packaging_span": "משטח",
      "quantity_span": null,
    },
    {
      "product_span": "4-6",
      "packaging_span": "משטח",
      "quantity_span": null,
    }
  ]
}

---

Few-shot 3
Message:
רהט בא לעמיס
10 אמאהות
2 גרנולה 11
2 דגן מקוצץ
משטח שעורה לחןצה

Expected:
{
  "customer_span": "רהט",
  "destination_span": null,
  "transportation_span": "איסוף עצמי",
  "notes_span": "",
  "line_items": [
    {
      "product_span": "אמאהות",
      "packaging_span": null,
      "quantity_span": "10",
    },
    {
      "product_span": "גרנולה 11",
      "packaging_span": null,
      "quantity_span": "2",
    },
    {
      "product_span": "דגן מקוצץ",
      "packaging_span": null,
      "quantity_span": "2",
    },
    {
      "product_span": "שעורה לחןצה",
      "packaging_span": "משטח",
      "quantity_span": null,
    }
  ]
}

---

Few-shot 4
Message:
רהט
5 טון דגן מארז קטן שלנו
5 טון אספסת מארז שלנו
10 טון אמאחות מישקל טון
3 משטח גרנולה 11
משטח גרנולה 12
מה יש לנו יכולת להוציא לו השבוע?

Expected:
{
  "customer_span": "רהט",
  "destination_span": null,
  "transportation_span": null,
  "notes_span": "מה יש לנו יכולת להוציא לו השבוע?",
  "line_items": [
    {
      "product_span": "דגן מארז קטן שלנו",
      "packaging_span": "טון",
      "quantity_span": "5",
    },
    {
      "product_span": "אספסת מארז שלנו",
      "packaging_span": "טון",
      "quantity_span": "5",
    },
    {
      "product_span": "אמאחות מישקל",
      "packaging_span": "טון",
      "quantity_span": "10",
    },
    {
      "product_span": "גרנולה 11",
      "packaging_span": "משטח",
      "quantity_span": "3",
    },
    {
      "product_span": "גרנולה 12",
      "packaging_span": "משטח",
      "quantity_span": null,
    }
  ]
}

---

Few-shot 5
Message:
מוהנד אבו דיבה 3ביג  עגלים יבש

Expected:
{
  "customer_span": "מוהנד אבו דיבה",
  "destination_span": null,
  "transportation_span": null,
  "notes_span": "",
  "line_items": [
    {
      "product_span": "עגלים יבש",
      "packaging_span": "ביג",
      "quantity_span": "3",
    }
  ]
}

---

Few-shot 6
Message:
שבסו רייחניאה - משטח גרנולה - מזמינה בית גבריאל 
Expected:
{
  "customer_span": "שבסו רייחניאה",
  "destination_span": null,
  "transportation_span": null,
  "notes_span": "מזמינה בית גבריאל",
  "line_items": [
    {
      "product_span": "גרנולה",
      "packaging_span": "משטח",
      "quantity_span": null,
    }
  ]
}

---

Few-shot 7
Message:
"חיות דגן 2 מארז הכנה להמלטה
רשלצ"
Expected:
{
  "customer_span": "חיות דגן",
  "destination_span": "רשלצ",
  "transportation_span": null,
  "notes_span": "",
  "line_items": [
    {
      "product_span": "הכנה להמלטה",
      "packaging_span": "מארז",
      "quantity_span": "2",
    }
  ]
}
"""


















GENERIC_MATCH_PROMPT = """
SYSTEM:
You are a precise list matcher.
Your job is to match a short Hebrew text span from the ORIGINAL_MESSAGE to the most relevant entry from the provided LIST.
Do not guess. If uncertain, return null.

OUTPUT:
Return ONLY this JSON:
{
  "matched_name": "<string from LIST or null>",
  "confidence": <0..1>,
  "reason": "<string>",
}

MATCHING RULES:
- Match exactly one entry from LIST or null if no confident match.
- Copy matched_name EXACTLY as written in the LIST. Never invent the name!
- Confidence reflects how strong the match is: exact match >0.95, alias/typo 0.8-0.9, fuzzy/weak <0.8.
- Reason  - explains why the match was made. Must be returned if confidence is weak or fuzzy. 

LIST FORMAT:
Each line: <name>
- Only return values from these fields. Never invent new text.

USER:
ENTITY_TYPE: {{ENTITY_TYPE}}

ORIGINAL_MESSAGE:
{{ORIGINAL_MESSAGE}}

LIST:
{{LIST_TEXT}}

Few-shot 1:
ENTITY_TYPE: customer
ORIGINAL_MESSAGE:
זאב גרודצקי - כפר גדעון
LIST:
c001|זאב גרודצקי|aliases=זאב גרודצקי,זאב ג
c002|משק גלבוע|aliases=גלבוע
Expected JSON:
{"matched_name":"זאב גרודצקי","confidence":0.97}

Few-shot 2:
ENTITY_TYPE: product
ORIGINAL_MESSAGE:
2 משטחים אורופאק
LIST:
p010|אורופק|aliases=אורופאק
p046|4-6|aliases=4 – 6,4 - 6
Expected JSON:
{"matched_name":"אורופק","confidence":0.92}

Few-shot 3:
ENTITY_TYPE: destination
ORIGINAL_MESSAGE:
להובלה לכפר יחזקאל
LIST:
d001|כפר יחזקאל|aliases=כפר יח
d002|כפר גדעון|aliases=
Expected JSON:
{"matched_name":"כפר יחזקאל","confidence":0.97}
"""
