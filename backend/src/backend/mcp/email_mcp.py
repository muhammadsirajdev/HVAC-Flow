"""Gmail through the Klavis Gmail MCP server.

Tools used (of the 10 the server offers): gmail_send_email (new email, or a reply with threadId),
gmail_search_emails (candidate message IDs), gmail_read_email (a message's whole thread) and
gmail_modify_email (remove UNREAD). Drafts, delete, batch, attachment and contact tools are not used.

The server returns no raw headers (no Authentication-Results, Reply-To or Message-ID).
Callers always pass a recipient that code chose, never the model; there is no forward tool.
Check the real tool names and arguments with `python scripts/list_mcp_tools.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from email.utils import parseaddr

from langchain_core.tools import BaseTool

from backend.config import get_settings
from backend.core.errors import MCPError
from backend.mcp.client import call_tool, parse_json


@dataclass
class SentEmail:
    message_id: str | None
    thread_id: str | None
    raw: str


@dataclass
class Email:
    message_id: str
    thread_id: str
    sender: str            # lower-cased address
    sender_name: str
    to: str
    subject: str
    text: str


def send_email(to: str, subject: str, body: str, tool: BaseTool | None = None,
               thread_id: str | None = None) -> SentEmail:
    """Execute gmail_send_email; with `thread_id` it is a reply in that thread."""
    args = {"to": [to], "subject": subject, "body": body}
    if thread_id:
        args["threadId"] = thread_id
    text = call_tool(tool or get_settings().gmail_send_tool, args)
    data = parse_json(text)
    message_id = data.get("id") or data.get("messageId") or data.get("message_id")
    thread_id = data.get("threadId") or data.get("thread_id") or thread_id
    if message_id and not thread_id:        # the send result may carry no thread: look it up
        try:
            thread_id = (read_thread(message_id) or [None])[0].thread_id
        except (MCPError, AttributeError):
            thread_id = None
    return SentEmail(message_id=message_id, thread_id=thread_id, raw=text)


def search(query: str, max_results: int) -> list[str]:
    """Message IDs matching a Gmail query, oldest first."""
    data = parse_json(call_tool(get_settings().gmail_search_tool, {"query": query, "maxResults": max_results}))
    return [m["id"] for m in reversed(data.get("result") or []) if m.get("id")]


def read_thread(message_id: str) -> list[Email]:
    """Every message in the thread that contains `message_id`, oldest first."""
    data = parse_json(call_tool(get_settings().gmail_read_tool, {"messageId": message_id}))
    thread_id = data.get("threadId") or message_id
    out = []
    for e in data.get("emails") or []:
        name, addr = parseaddr(e.get("from") or "")
        body = e.get("body") or {}
        text = body.get("text") or re.sub(r"<[^>]+>", " ", body.get("html") or "")
        out.append(Email(message_id=e["messageId"], thread_id=thread_id, sender=addr.lower(),
                         sender_name=name, to=(e.get("to") or "").lower(), subject=e.get("subject") or "",
                         text=text))
    return out


def mark_read(message_id: str) -> None:
    call_tool(get_settings().gmail_modify_tool, {"messageId": message_id, "removeLabelIds": ["UNREAD"]})

