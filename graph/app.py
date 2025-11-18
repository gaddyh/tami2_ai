# tami_graph.py

from graph.build import build_tami_app
from graph.state import TamiState

tami_graph_app = build_tami_app()

if __name__ == "__main__":
    # Ask something that should *not* use the tool
    state1: TamiState = {
        "input_text": "מה העניינים?",
        "context": {},
    }
    out1 = tami_graph_app.invoke(state1)
    print("Reply 1:", out1["final_output"])

    # Ask something that *should* use the get_time tool
    state2: TamiState = {
        "input_text": "מה השעה עכשיו?",
        "context": {},
    }
    out2 = tami_graph_app.invoke(state2)
    print("Reply 2:", out2["final_output"])
