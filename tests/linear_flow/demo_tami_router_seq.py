# demo_tami_router_seq.py

from agent.tami.graph import build_tami_router_app
from agent.linear_flow.state import LinearAgentState
from agent.tami.graph import handle_tami_turn

def run_message(app, thread_id, text):
    state: LinearAgentState = {
        "input_text": text,
        "context": {},
        "messages": [],
        "llm_messages": [],
    }

    print("\n==============================")
    print("USER:", text)
    print("==============================")

    result = handle_tami_turn(app, thread_id, text, base_state=state)

    # Print all the important stuff
    print("→ target_agent:", result.get("target_agent"))
    print("→ followup_message:", result.get("followup_message"))
    print("→ final response:", result.get("response"))
    print("→ context:", result.get("context"))
    return result


def main():
    app = build_tami_router_app()
    thread_id = "tami-demo-thread-1"

    messages = [
        "תזכיר לי להתקשר לבנק",
        "מחר יש לי פגישה בעשר",
        "שלח לאמא שאני בדרך",
        "למה יש לי חור בלוח זמנים מחר?",
        "תוסיף פגישה עם דויד בשבוע הבא",
        "תכתוב למיכל שהפגישה תדחה בשעה",
        "תזכיר לי מחר לשלם ארנונה",
        "בצהריים",
        "יש לי יום עמוס בראשון, תוכל לארגן לי את היום?",
        "תשלח לגל את הסיכום של הפגישה האחרונה שלנו",
    ]

    for text in messages:
        run_message(app, thread_id, text)


if __name__ == "__main__":
    main()
