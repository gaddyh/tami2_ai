import os
import hmac
import hashlib
import logging
import time

from fastapi import FastAPI, Request, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse, HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from shared.event_trigger import trigger_events_loop
from shared.google_calendar.oauth import google_router
from shared.message_worker import message_queue, _queue_worker, message_cache, MESSAGE_TTL_SECONDS
from fastapi.templating import Jinja2Templates
from green_api.green_router import green_router
from green_api.live_router import green_live_router
from adapters.whatsapp.cloudapi.message_index import MESSAGE_INDEX

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
import asyncio
import contextlib
from fastapi import FastAPI
from contextlib import asynccontextmanager, suppress
from typing import Optional
from green_api.instance_mng.pool import ensure_pool_ready

import asyncio
# --- logging helpers at top of file (near imports) ---
import json

def _peek_textish(m: dict) -> tuple[str|None, str|None, str|None, str|None]:
    text = (m.get("text") or {}).get("body")
    cap  = ((m.get("image") or {}).get("caption")
            or (m.get("video") or {}).get("caption")
            or (m.get("document") or {}).get("caption"))
    itype = (m.get("interactive") or {}).get("type")
    btxt  = (m.get("button") or {}).get("text")
    return text, cap, itype, btxt

async def wait_or_stop(stop_event: asyncio.Event, timeout: float) -> None:
    if stop_event.is_set():
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        # timed out: just continue the loop
        pass


async def pool_worker(stop_event: asyncio.Event):
    """Runs forever until stop_event is set."""
    while not stop_event.is_set():
        try:
            await ensure_pool_ready()
        except Exception as e:
            print("Pool worker error:", e)
        # Sleep, but wake up early if we're asked to stop
        await wait_or_stop(stop_event, 60)

from datetime import timedelta
from shared.time import utcnow
from shared.daily_digest import handle_daily_tasks_digest
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

TZ = ZoneInfo("Asia/Jerusalem")

async def daily_digest_loop(stop_event: asyncio.Event):
    while not stop_event.is_set():
        # 1. Localize now to Israel time
        now_local = datetime.now(TZ)

        # 2. Build today's target at 07:30 Israel time
        target_local = now_local.replace(hour=9, minute=0, second=0, microsecond=0)

        # 3. If passed → schedule tomorrow
        if target_local <= now_local:
            target_local += timedelta(days=1)

        # 4. Compute local delay
        delay = (target_local - now_local).total_seconds()

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
            if stop_event.is_set():
                break
        except asyncio.TimeoutError:
            pass

        if stop_event.is_set():
            break

        try:
            await handle_daily_tasks_digest("972546610653")
            await handle_daily_tasks_digest("972528310789")
            await handle_daily_tasks_digest("972507674593")
        except Exception:
            import traceback, sys
            traceback.print_exc(file=sys.stderr)


from contextlib import asynccontextmanager, suppress
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()

    loop_task   = asyncio.create_task(trigger_events_loop(stop_event), name="trigger_events_loop")
    worker_task = asyncio.create_task(_queue_worker(stop_event),        name="queue_worker")
    pool_task   = asyncio.create_task(pool_worker(stop_event),          name="pool_worker")
    digest_task = asyncio.create_task(daily_digest_loop(stop_event),    name="daily_digest_loop")

    tasks = (loop_task, worker_task, pool_task, digest_task)

    try:
        yield
    finally:
        # Cooperative shutdown
        stop_event.set()
        # Give them a moment to exit gracefully
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=2.0)
        except asyncio.TimeoutError:
            # Fallback: force-cancel any stragglers
            for t in tasks:
                if t and not t.done():
                    t.cancel()
            for t in tasks:
                if t:
                    with suppress(asyncio.CancelledError):
                        await t

# Config
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "...")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")

app = FastAPI(lifespan=lifespan)
app.include_router(google_router) #auth connect, refresh contacts
app.include_router(green_router) #login user, get qr, get instance state
app.include_router(green_live_router) #webhook

templates = Jinja2Templates(directory="apps/templates")

from fastapi.staticfiles import StaticFiles

# ✅ serve only under /static
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def health_check():
    return JSONResponse(content={"status": "ok"}, status_code=200)

@app.head("/")
def head_root():
    return Response(status_code=200)

@app.get("/home", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/success", response_class=HTMLResponse)
async def google_connect_success(request: Request):
    return templates.TemplateResponse("google_success.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})

@app.get("/connect", response_class=HTMLResponse)
async def google_connect_page(request: Request):
        return templates.TemplateResponse("google_connect.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def serve_login_page(request: Request, user_id: Optional[str] = Query(None)):
    """
    Dedicated login page that contains the phone input, login button, spinner, and QR <img>.
    Make sure apps/templates/login.html exists and uses the IDs: phone, login-btn, spinner, qr-image.
    """
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "user_id": user_id}
    )
    
@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    print("hub_mode", hub_mode)
    print("hub_verify_token", hub_verify_token)
    print("hub_challenge", hub_challenge)
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        logger.info("Webhook verification succeeded.")
        return hub_challenge or ""
    logger.warning("Webhook verification failed.")
    raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/webhook")
async def webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=None)
):
    body_bytes = await request.body()

    # Verify Meta signature if app secret is set
    if APP_SECRET:
        expected_signature = "sha256=" + hmac.new(
            APP_SECRET.encode(), body_bytes, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, x_hub_signature_256 or ""):
            logger.warning("Signature verification failed.")
            raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        raw_data = await request.json()
    except Exception as e:
        logger.exception("Failed to parse JSON body")
        return Response(status_code=200)

    # ---- NEW: enqueue all new Cloud API messages & return fast ----
    saw_messages = False
    new_jobs = 0
    now = time.time()

    stale = [mid for mid, ts in message_cache.items() if now - ts >= MESSAGE_TTL_SECONDS]
    for mid in stale:
        del message_cache[mid]

    try:
        for entry in (raw_data.get("entry") or []):
            for change in (entry.get("changes") or []):
                value = change.get("value") or {}
                phone_number_id = (value.get("metadata") or {}).get("phone_number_id")

                for m in (value.get("messages") or []):
                    saw_messages = True
                    mid = m.get("id")
                    if not mid:
                        continue

                    if mid in message_cache:
                        # Already seen (likely retry/batch dup)
                        continue

                    # --- inside your /webhook loop, just before message_queue.append({...}) ---
                    try:
                        msg_type = m.get("type")
                        keys = list(m.keys())
                        text, caption, interactive_type, button_text = _peek_textish(m)

                        logger.info(
                        "ENQ mid=%s from=%s type=%s keys=%s text=%s caption=%s interactive=%s button=%s",
                        mid, m.get("from"), msg_type, keys,
                        (text[:120] if text else None),
                        (caption[:120] if caption else None),
                        interactive_type, button_text
                    )
                    except Exception as e:
                        logger.exception("ENQ post-parse logging failed: %s", e)

                    # (Optional) deep debug for unknowns / empties
                    if not (text or caption or button_text or interactive_type):
                        logger.debug("ENQ raw message (no textish fields): %s", json.dumps(m)[:1000])

                    # Mark seen and enqueue a compact job
                    message_cache[mid] = now
                    message_queue.append({
                        "message_id": mid,
                        "phone_number_id": phone_number_id,
                        "raw": m,        # the single message object (keep minimal)
                        "timestamp": m.get("timestamp"),
                        "from": m.get("from"),
                    })
                    new_jobs += 1

    except Exception:
        logger.exception("Failed to collect messages for enqueue")

    if new_jobs > 0:
        logger.info("Enqueued %d new WhatsApp messages", new_jobs)
        return Response(status_code=200)

    # If we saw messages but all were duplicates, acknowledge and exit
    if saw_messages and new_jobs == 0:
        return JSONResponse({"status": "duplicate"}, status_code=200)

    return Response(status_code=200)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    