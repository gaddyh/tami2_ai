# cli_tami.py
import asyncio
from datetime import datetime, timezone

from graph.nodes.tami_runner import run_tami_turn
from models.input import In, Source  # use your actual import / enum
from graph.nodes.prepare_messages import parse_tami_json

async def main():
    user_id = "cli-user2" + str(datetime.now(timezone.utc))
    thread_id = "cli-thread-2" + str(datetime.now(timezone.utc))
    tz = "Asia/Jerusalem"

    print("Tami CLI. Type 'exit' to quit.\n")

    while True:
       
        text = "what are my tasks?"

        in_ = In(
            tz=tz,
            text=text,
            locale="he-IL",                   # or "he" / whatever you use
            source="whatsapp",
            user_id=user_id,
            thread_id=thread_id,
            user_name="CLI User",
            current_datetime=datetime.now(timezone.utc).isoformat(),
        )

        out = await run_tami_turn(in_)
        print("out raw:", out)
        res = parse_tami_json(out.final_output)
        #print(f"Tami: {res}\n")

        try:
            text = input("> ").strip()
        except EOFError:
            break

        if not text:
            continue
        if text.lower() in ("exit", "quit", "q"):
            break


if __name__ == "__main__":
    messages = [1, 2, 3, 4,5,6,7,8,9,10]
    MAX = 6

    print(messages[-MAX:])   # keeps newest (good!)
    print(messages[:MAX])   # keeps oldest (bad)
    asyncio.run(main())
