import os
import hmac
import hashlib
import logging
import time

from fastapi import FastAPI, Request, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse, HTMLResponse
from agent.main import handleUserInput
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
from green_api.instance_mng.create import pool_create_instance

import asyncio

async def wait_or_stop(stop_event: asyncio.Event, timeout: float) -> None:
    if stop_event.is_set():
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        # timed out: just continue the loop
        pass


from contextlib import asynccontextmanager, suppress
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()

    worker_task = asyncio.create_task(_queue_worker(stop_event),        name="queue_worker")

    tasks = (worker_task)

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
app.include_router(google_router)
app.include_router(green_router)
app.include_router(green_live_router)
templates = Jinja2Templates(directory="apps/templates")

@app.get("/")
def health_check():
    return JSONResponse(content={"status": "ok"}, status_code=200)

@app.head("/")
def head_root():
    return Response(status_code=200)

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

from fastapi import Request, Header, HTTPException
from fastapi.responses import Response, JSONResponse
import hmac, hashlib, time, logging

logger = logging.getLogger(__name__)

# Provided/assumed elsewhere:
# APP_SECRET: str | None
# message_cache: dict[str, float]
# message_queue: deque[dict]
# MESSAGE_TTL_SECONDS: int
# MESSAGE_INDEX: singleton with put(wamid:str, msg:dict) and gc()

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

    # Parse JSON
    try:
        raw_data = await request.json()
    except Exception:
        logger.exception("Failed to parse JSON body")
        return Response(status_code=200)

    # ---- enqueue all new Cloud API messages & return fast ----
    saw_messages = False
    new_jobs = 0
    now = time.time()

    # TTL cleanup for dedupe cache (and optionally the message index if you want)
    stale = [mid for mid, ts in message_cache.items() if now - ts >= MESSAGE_TTL_SECONDS]
    for mid in stale:
        try:
            del message_cache[mid]
        except KeyError:
            pass

    try:
        for entry in (raw_data.get("entry") or []):
            for change in (entry.get("changes") or []):
                value = change.get("value") or {}
                phone_number_id = (value.get("metadata") or {}).get("phone_number_id")

                # 1) Handle inbound "messages" (what we care about for replies/originals)
                for m in (value.get("messages") or []):
                    saw_messages = True
                    mid = m.get("id")
                    if not mid:
                        continue

                    # Deduplicate retries
                    if mid in message_cache:
                        continue

                    # Remember this exact inbound message for future reply hydration
                    # (context.id -> MESSAGE_INDEX.get(wamid))
                    try:
                        MESSAGE_INDEX.put(mid, m)
                    except Exception:
                        logger.exception("Failed to index inbound message wamid=%s", mid)

                    # Mark seen and enqueue a compact job for your worker
                    message_cache[mid] = now
                    message_queue.append({
                        "message_id": mid,
                        "phone_number_id": phone_number_id,
                        "raw": m,               # keep the single message dict
                        "timestamp": m.get("timestamp"),
                        "from": m.get("from"),
                    })
                    new_jobs += 1

                # 2) Optionally acknowledge "statuses" to avoid noisy logs (no enqueue)
                #    These are delivery/read acks for messages you SENT.
                #    If you ever need them, handle here—but we ignore for now.
                # for s in (value.get("statuses") or []):
                #     pass

    except Exception:
        logger.exception("Failed to collect messages for enqueue")

    if new_jobs > 0:
        logger.info("Enqueued %d new WhatsApp messages", new_jobs)
        return Response(status_code=200)

    # If we saw messages but all were duplicates, acknowledge and exit
    if saw_messages and new_jobs == 0:
        return JSONResponse({"status": "duplicate"}, status_code=200)

    # No messages (could be only statuses or unrelated changes)
    return Response(status_code=200)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    