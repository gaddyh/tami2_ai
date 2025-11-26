# demo_tami_router.py

from agent.tami.graph import build_tami_router_app
from agent.linear_flow.state import LinearAgentState
import time
def main():
    app = build_tami_router_app()

    state: LinearAgentState = {
        "input_text": "תזכיר לי לקנות חלב",
        "context": {},
        "messages": [],
        "llm_messages": [],
    }

    start = time.time()
    result = app.invoke(
        state,
        config={"configurable": {"thread_id": "tami-demo-1"}},
    )
    elapsed = time.time() - start
    print(f"Agent flow took {elapsed:.2f}s")

    print("target_agent:", result.get("target_agent"))
    print("response:", result.get("response"))
    print("followup_message:", result.get("followup_message"))

if __name__ == "__main__":
    main()
