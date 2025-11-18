# cli_tami.py
import asyncio
from datetime import datetime, timezone

from graph.nodes.tami_runner import run_tami_turn
from models.input import In, Source  # use your actual import / enum
from graph.nodes.prepare_messages import parse_tami_json

async def main():
    user_id = "cli-user"
    thread_id = "cli-thread-1"
    tz = "Asia/Jerusalem"

    print("Tami CLI. Type 'exit' to quit.\n")

    while True:
        try:
            text = input("> ").strip()
        except EOFError:
            break

        if not text:
            continue
        if text.lower() in ("exit", "quit", "q"):
            break

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
        res = parse_tami_json(out.final_output)
        print(f"Tami: {res}\n")


if __name__ == "__main__":
    asyncio.run(main())
