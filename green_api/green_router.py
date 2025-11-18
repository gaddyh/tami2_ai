from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from shared.user import get_user
from fastapi.responses import JSONResponse
from green_api.instance_mng.pool import claim_instance, release_instance
from green_api.instance_mng.qr import get_qr_image
from whatsapp_api_client_python import API
from models.user import userContextDict
import uuid
import traceback
import time
import logging
import asyncio
from adapters.whatsapp.cloudapi.cloud_api_adapter import CloudAPIAdapter
from green_api.groups import list_groups
from store.user import UserStore
from shared.user import create_user

green_router = APIRouter()

# Error codes
ERROR_INVALID_USER_ID = "INVALID_USER_ID"
ERROR_CHANNEL_CREATE = "CHANNEL_CREATE_ERROR"
ERROR_LOGIN_USER = "LOGIN_USER_ERROR"
ERROR_UNEXPECTED = "UNEXPECTED_ERROR"

def _err(status: int, code: str, message: str, extra: dict | None = None) -> JSONResponse:
    payload = {"ok": False, "error": {"code": code, "message": message}}
    if extra:
        payload["error"].update(extra)
    return JSONResponse(status_code=status, content=payload)

def _ok(data: dict) -> JSONResponse:
    return JSONResponse(status_code=200, content={"ok": True, "data": data})

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# -----------------------------------------------------------------------------
# App lifecycle: background events loop
# -----------------------------------------------------------------------------
running = True


async def pool_worker(stop_event: asyncio.Event):
    """Runs forever until stop_event is set."""
    while not stop_event.is_set():
        try:
            await ensure_pool_ready()
        except Exception as e:
            print("Pool worker error:", e)
        await asyncio.sleep(60)  # run every 60s

from observability.obs import span_attrs, mark_error

@green_router.post("/login-user")
async def login_user(req: Request):
    inst = None
    success = False
    state = None
    token = None
    qr = None
    status = "pending"
    user_id = None

    with span_attrs(
        "green.login_user",
        operation="http",
        route="/login-user",
    ) as span:
        try:
            # --- Parse JSON ---
            try:
                data = await req.json()
            except Exception as e:
                mark_error(span, e)
                span.update(error="invalid_json")
                return _err(400, ERROR_UNEXPECTED, "Invalid JSON payload")

            user_id = (data.get("user_id") or "").strip()
            span.update(user_id=user_id)

            if not (user_id.isdigit() and user_id.startswith("972") and len(user_id) == 12):
                span.update(error="invalid_user_id")
                return _err(422, ERROR_INVALID_USER_ID, "Invalid user_id format. Expecting 972XXXXXXXXX")

            # --- Main logic ---
            user = get_user(user_id)
            if not user:
                span.update(error="user_not_found")
                return _err(404, ERROR_INVALID_USER_ID, "User not found")
            
            # Existing token?
            if (
                user
                and user.runtime
                and user.runtime.greenApiInstance
                and user.runtime.greenApiInstance.token
            ):
                token = user.runtime.greenApiInstance.token
                span.update(has_cached_instance=True)

                # Check current state
                state = get_instance_state(user_id)
                span.update(instance_state=state)

                if state == "authorized":
                    status = "connected"
                    success = True
                    span.update(success=True, status=status)
                    return JSONResponse({
                        "status": status,
                        "token": token,
                        "qr": None,
                        "state": state,
                    })
                # else: fall through → try to fetch QR
            else:
                inst = claim_instance(user_id)
                token = inst["apiTokenInstance"]
                span.update(has_cached_instance=False, claimed_instance=True)

            # Try QR fetch
            try:
                qr = get_qr_image(user_id)
                status = "ready"
            except Exception as qr_err:
                # QR failure is not fatal; just note it.
                span.update(qr_error=str(qr_err))
                status = "pending"

            # Cache user in memory
            user = get_user(user_id)
            if user:
                userContextDict[user_id] = user
                span.update(user_cached=True)
            else:
                span.update(user_cached=False)

            success = True
            span.update(success=True, status=status, state=state)

            return JSONResponse({
                "status": status,
                "token": token,
                "qr": qr,
                "state": state,
            })

        except RuntimeError as e:
            mark_error(span, e)
            span.update(error="runtime_error", error_message=str(e))
            if "No ready instance" in str(e):
                status = "pending"
                span.update(status=status, success=False)
                return JSONResponse({
                    "status": "pending",
                    "token": None,
                    "qr": None,
                    "state": None,
                })
            raise

        except HTTPException as e:
            mark_error(span, e)
            msg = e.detail if isinstance(e.detail, str) else str(e.detail)
            span.update(error="http_exception", status_code=e.status_code, error_message=msg)
            return _err(e.status_code, ERROR_UNEXPECTED, msg)

        except Exception as e:
            mark_error(span, e)
            trace_id = str(uuid.uuid4())[:8]
            span.update(error="unexpected_exception", trace_id=trace_id, error_message=str(e))
            print(f"[{trace_id}] unexpected error in /login-user: {e}\n{traceback.format_exc()}")
            return _err(500, ERROR_UNEXPECTED, "Unexpected error during login", {"trace_id": trace_id})

        finally:
            # Final outcome for the span
            span.update(
                final_status=status,
                success=success,
                state=state,
                has_instance=bool(inst),
            )
            if inst and not success:
                try:
                    release_instance(user_id, inst)
                    print(f"Released instance for {user_id} after login failure")
                except Exception as cleanup_err:
                    print(f"⚠️ Failed to release instance for {user_id}: {cleanup_err}")
                    # Don't re-raise; just log.



def get_instance_state(user_id: str) -> str:
    user = get_user(user_id)
    if not user or not getattr(user, "runtime", None) or not user.runtime.greenApiInstance:
        raise HTTPException(404, "No instance found for user")

    green = API.GreenAPI(str(user.runtime.greenApiInstance.id),
                         user.runtime.greenApiInstance.token)
    resp = green.account.getStateInstance()
    return resp.data.get("stateInstance") if hasattr(resp, "data") else resp.get("stateInstance")

@green_router.get("/instance-state")
async def instance_state(user_id: str):
    try:
        state = get_instance_state(user_id)
        return {"state": state}
    except HTTPException:
        # Preserve 404 from get_instance_state
        raise
    except Exception as e:
        trace_id = str(uuid.uuid4())[:8]
        print(f"[{trace_id}] error in /instance-state for {user_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, f"Error checking instance state (trace_id={trace_id})")

def list_groups_as_dict(user_id: str, timeout: float = 20.0) -> dict[str, dict[str, str]]:
    groups = list_groups(user_id, timeout)
    print(f"\nGroups: {len(groups)} groups for {user_id}")
    result = {}
    for g in groups:
        name = g.get("group_name")
        if not name:
            continue
        result[name] = g  # or just {"group_id": g["group_id"]} if you don't want to keep name inside
    return result

from shared.google_calendar.gcal_client import get_contacts

async def refresh_contact(userId):
    print("Refreshing contact")
    all_start = time.perf_counter()
    user = get_user(userId)
    if user is None:
        print(f"❌ User {userId} not found")
        return
    print(f"\nUser: {userId}")
    u_start = time.perf_counter()

    t0 = time.perf_counter()
    try:
      # Assuming user.runtime.contacts is a dict[str, dict[str, str|None]]
        # and list_groups returns a list[dict[str, Any]] with a "group_id" key

        await get_contacts(user.user_id)
        user_store = UserStore(user.user_id)
        user = user_store.load()
        new_groups = list_groups_as_dict(user.user_id)
        print(f"✅ Got {len(new_groups)} groups for {user.user_id}")
        # Extend, don't override
        for name, data in new_groups.items():
            if name in user.runtime.contacts:
                user.runtime.contacts[name].update(data)  # merge into existing
            else:
                user.runtime.contacts[name] = data

    
        UserStore(user.user_id).save(user)
        userContextDict[user.user_id] = user
    except Exception as e:
        print(f"❌ Failed to get contacts for {user.user_id}: {e}")

#todo remove: https://whatsmatter-platform.onrender.com/refresh-contact?user_id=972546610653

#called after succesful qr scan: 
@green_router.get("/refresh-contact")
async def do_refresh_contacts(user_id: str):
    await refresh_contact(user_id)
    return {"status": "ok"}


@green_router.get("/create-user")
async def do_create_user(user_id: str, name: str):
    create_user(user_id, "", name)
    return {"status": "ok"}