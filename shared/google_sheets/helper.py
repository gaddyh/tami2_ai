# --- put these near your other imports ---
import os, json, logging, asyncio
from datetime import datetime
from typing import Any, Dict, List

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from shared.time import to_user_timezone
logger = logging.getLogger(__name__)

# === CONFIG ===
SPREADSHEET_ID = "1660DyXD8JYdUxj7-BWLtUnsHAC14-GT_SW2vAwUOvmA"      # <-- paste the target sheet id
SHEET_NAME     = "Sheet1"                   # <-- tab name
EXPECTED_HEADERS = [
    "טקסט מקורי","שם לקוח","מוצר","כמות","מארז","סוג הובלה","יעד","הערות","נוצר ב",
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

