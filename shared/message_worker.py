import asyncio, logging, time
from collections import deque
from adapters.whatsapp.cloudapi.cloud_api_adapter import CloudAPIAdapter
from shared.user import get_user, create_user, userContextDict
from agent.main import handleUserInput
from store.user import UserStore
from store.new_waiting_users_store import save_user_chat_id, get_user_chat_id

logger = logging.getLogger(__name__)

message_cache: dict[str, float] = {}   # { message_id: first_seen_unix }
message_queue: deque[dict] = deque()   # FIFO queue of jobs
MESSAGE_TTL_SECONDS = 48 * 3600

def _wrap_single_message(phone_number_id: str | None, message_obj: dict) -> dict:
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": phone_number_id} if phone_number_id else {},
                    "contacts": [{
                        "wa_id": message_obj.get("from") or "",
                        "profile": {}
                    }],
                    "messages": [message_obj],
                }
            }]
        }]
    }

import asyncio

import asyncio

newUserMessage = """ 
היי 👋
אני העוזר האישי החדש שלך 🤖
כרגע אני עוד מתכונן מאחורי הקלעים… אבל בקרוב מאוד נוכל לעבוד ביחד 😉

רוצה להיות בין הראשונים לקבל אותי?
==yes_no_buttons_placeholder==
"""

async def wait_or_stop(stop_event: asyncio.Event, timeout: float) -> None:
    if stop_event.is_set():
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        # timed out: just continue the loop
        pass


async def _queue_worker(stop_event: asyncio.Event):
    adapter = CloudAPIAdapter()  # reuse per worker

    while not stop_event.is_set():
        try:
            if not message_queue:
                await wait_or_stop(stop_event, 0.05)  # idle wait; interruptible
                continue

            try:
                job = message_queue.popleft()
            except IndexError:
                # Race: queue became empty between check and pop
                await wait_or_stop(stop_event, 0.01)
                continue

            mid = job.get("message_id")
            phone_number_id = job.get("phone_number_id")
            single_body = _wrap_single_message(phone_number_id, job.get("raw") or {})

            try:
                m = job.get("raw") or {}
                msg_type = m.get("type")
                text = (m.get("text") or {}).get("body")
                caption = ((m.get("image") or {}).get("caption")
                        or (m.get("video") or {}).get("caption")
                        or (m.get("document") or {}).get("caption"))
                interactive_type = (m.get("interactive") or {}).get("type")
                button_text = (m.get("button") or {}).get("text")

                logger.info(
                    "WRK in mid=%s from=%s type=%s text=%s caption=%s interactive=%s button=%s",
                    job.get("message_id"), job.get("from"), msg_type,
                    (text[:120] if text else None),
                    (caption[:120] if caption else None),
                    interactive_type, button_text
                )

                rawMessage = await adapter.parse_incoming(single_body)

                # suppose your normalized object is rawMessage with .content fields
                try:
                    c = getattr(rawMessage, "content", None)
                    norm_text = getattr(c, "text", None) if c else None
                    norm_kind = getattr(c, "kind", None) if c else None

                    if not norm_text:
                        logger.warning(
                            "WRK empty_text mid=%s norm_kind=%s src_type=%s interactive=%s",
                            job.get("message_id"), norm_kind, msg_type, interactive_type
                        )
                except Exception as e:
                    logger.exception("WRK post-parse logging failed: %s", e)

                if not rawMessage:
                    logger.info("Worker: message %s ignored.", mid)
                    continue

                user = get_user(rawMessage.chat_id)
                if user is None:
                    # replied yes to new user message
                    if rawMessage.content.button_reply:
                        br = rawMessage.content.button_reply
                        if br.text == "כן":
                            save_user_chat_id(rawMessage.chat_id)
                            await adapter.send_message(rawMessage.chat_id, "תודה רבה! אני אשמח לעזור לך בקרוב מאוד")
                        else:
                            await adapter.send_message(rawMessage.chat_id, "תודה ושלום :)")
                        continue
                    else:
                        waitingUser = get_user_chat_id(rawMessage.chat_id)
                        if waitingUser:
                            await adapter.send_message(rawMessage.chat_id, "אין לך כבר סבלנות לחכות? אני אשמח לעזור לך בקרוב מאוד")
                        else:
                            # new user first time
                            await adapter.send_message(rawMessage.chat_id, newUserMessage)
                        continue

                    #TODO change to template message 
                    #user = create_user(rawMessage.chat_id, rawMessage.content.text, rawMessage.sender.name)
                    #userContextDict[rawMessage.chat_id] = user

                # Acknowledge receipt
                if mid:
                    await adapter.send_message(rawMessage.chat_id, "אני על זה!", reply_to=mid)
                else:
                    await adapter.send_message(rawMessage.chat_id, "אני על זה!")

                # Process
                result = await handleUserInput(rawMessage, user)
                UserStore(user.user_id).save(user)

                # Respond with result
                await adapter.send_message(rawMessage.chat_id, result)

            except asyncio.CancelledError:
                raise  # let shutdown propagate cleanly
            except Exception:
                logger.exception("Worker: failed processing message %s", mid or "<unknown>")
                # TODO: send to DLQ if/when available
                continue

        except asyncio.CancelledError:
            logger.info("Queue worker cancelled; shutting down.")
            break
        except Exception:
            logger.exception("Worker loop error")
            await wait_or_stop(stop_event, 2)  # brief, interruptible backoff
