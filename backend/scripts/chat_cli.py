"""Terminal chat loop for Run A (build step 4).

    uv run python scripts/chat_cli.py            # new session
    uv run python scripts/chat_cli.py my-session # resume a session (Postgres checkpointer)
"""

import logging
import sys
import uuid

from backend.graphs.run_a_chat import chat_turn


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    session = sys.argv[1] if len(sys.argv) > 1 else f"cli-{uuid.uuid4().hex[:12]}"
    print(f"session {session}. Type 'quit' to exit.\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in ("quit", "exit"):
            break
        if not text:
            continue
        out = chat_turn(session, text)
        print(f"\nbot> {out['reply']}")
        print(f"     [intent={out['intent']} case={out['case_id']} booked={out['booked']} "
              f"fallback={out['fallback_form']} emergency={out['emergency']}]\n")


if __name__ == "__main__":
    main()
