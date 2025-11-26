# demo_tami_router_seq.py

from agent.tami.graph import build_tami_router_app
from agent.tami.main import process_input
from shared.time import utcnow, now_iso_in_tz
import uuid
import time
from models.input import In, Source, Category

def run_message(app, thread_id, text):
    print("\n==============================")
    print("USER:", text)
    print("==============================")

    start_time = time.time()
    res = process_input(In(
        thread_id=thread_id, 
        text=text, user_id="user_id", 
        user_name="user_name", 
        source=Source.WHATSAPP, 
        category=Category.USER_REQUEST, 
        input_id=uuid.uuid4().hex, 
        idempotency_key=uuid.uuid4().hex,
        tz="Asia/Jerusalem",
        locale="he",
        current_datetime=now_iso_in_tz("Asia/Jerusalem"),
        received_at=utcnow(),
        redacted=False,
    ))
    end_time = time.time()
    print(f"turn took {end_time - start_time:.2f}s")

    if res["status"] == "interrupt":
        interrupt_payload = res["interrupt"].value
        result = interrupt_payload["question"]
        print("FOLLOWUP:", result)
    else:
        state = res["state"]
        result = state
        print("→ final response:", result.get("response"))
    return result


def main():
    app = build_tami_router_app()
    thread_id = "tami-demo-thread-1" + uuid.uuid4().hex

    messages = [
    # COMMS (WhatsApp messages / reminders to self)
    "בעוד שעה תזכיר לי להתקשר לבנק",
    "תשלח לדנה הודעה שאאחר לפגישה בערך בחצי שעה",

    # EVENTS (calendar scheduling)
    "תקבע לי פגישה למחר בשעה עשר",
    "ביום שני הבא בשמונה בערב תוסיף הרצאה ליומן",

    # TASKS (todo list)
    "תוסיף משימה לקנות מתנה ליום הולדת של נועם",
    "תיצור משימה לסדר את המסמכים בסוף השבוע",
]


    for text in messages:
        run_message(app, thread_id, text)


if __name__ == "__main__":
    main()
