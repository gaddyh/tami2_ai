# demo_notes_agent.py

from typing import Dict, Any
from datetime import datetime
from models.input import In, Source, Category
import uuid
from shared.time import utcnow, now_iso_in_tz
import time
from agent.tami.main import process_input

def run(text, thread_id):
    start_time = time.time()
    res = process_input(In(
        thread_id=thread_id, 
        text=text, 
        user_id="972546610653", 
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
    return res


def _now_iso() -> str:
    return datetime.now().isoformat()

def main():
    print("Tasks Agent Demo. Type 'quit' to exit.\n")

    test_inputs1 = [
        "whats my tasks",
        "add 3 tasks:check mail, throw garbage, clean table",
        "whats my tasks",
        "delete 2",
        "whats my tasks",
    ]
    test_inputs2 = [
        """
        משימה
קרמיקות שבורות מתחת לארון חשמל בקומה 5 בבניין יצחק שמיר אחד (ראה בתמונה המצטרפת)
ליפקין שחק 2 , גבעת שמואל
        """,
    ]

    test_inputs_tasks = [
        "whats my tasks",
        "delete check mail",
        "whats my tasks",
    ]

    test_inputs_scheduled_messages = [
        "מה ההודעות המתומנות שלי?",
        "תזכיר לי לעשן עוד 5 דקות",
        "מה ההודעות המתומנות שלי?",

    ]

    test_inputs_events = [
        "מה האירועים שלי"
    ]
        

    for user in test_inputs_scheduled_messages:
        print("You:", user)
        start = time.perf_counter_ns()
        result = run(user, "tasks__linear_demo")
        elapsed = (time.perf_counter_ns() - start) / 1e6
        print(f"Agent flow took {elapsed:.2f}ms")

        print("\nBot:", result)




if __name__ == "__main__":
    main()
