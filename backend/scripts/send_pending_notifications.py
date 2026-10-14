"""Booked visits whose confirmation email or Slack post never went out (crash, outage).

    uv run python scripts/send_pending_notifications.py            # list only, sends nothing
    uv run python scripts/send_pending_notifications.py --send     # send what is missing
    uv run python scripts/send_pending_notifications.py --send 4   # only Case #4

The email always goes to the address ON FILE for the booking's customer.
"""

import logging
import sys

from backend.graphs.run_a_chat.deps import load_mcp_tools
from backend.tools.booking import pending_notifications
from backend.tools.notify import send_pending


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpx2", "mcp", "langchain_mcp_adapters"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    send = "--send" in sys.argv
    only = {int(a) for a in sys.argv[1:] if a.isdigit()}

    pending = [p for p in pending_notifications() if not only or p.result.case_id in only]
    if not pending:
        print("Nothing pending: every booked visit has its confirmation email and Slack post.")
        return
    for p in pending:
        r = p.result
        missing = ", ".join(x for x, on in (("email", p.email_pending), ("slack", p.slack_pending)) if on)
        print(f"Case #{r.case_id}: {r.request.name} <{r.request.email}> {r.slot_label} -> missing: {missing}")
    if not send:
        print("\nNothing sent. Re-run with --send to send the missing notifications.")
        return
    tools = load_mcp_tools()
    for p in pending:
        print(f"Case #{p.result.case_id}: {send_pending(p, tools)}")


if __name__ == "__main__":
    main()
