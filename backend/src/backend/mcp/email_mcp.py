"""Gmail through the Klavis Gmail MCP server.

Only send-to-a-known-address lives here: there is no forward tool, and callers pass
a recipient that code (not the model) chose. Run B adds list_new / get_thread / reply / label.
Check the real tool names and arguments with `python scripts/list_mcp_tools.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import BaseTool

from backend.config import get_settings
from backend.mcp.client import call_tool, parse_json


@dataclass
class SentEmail:
    message_id: str | None
    thread_id: str | None
    raw: str


def send_email(to: str, subject: str, body: str, tool: BaseTool | None = None) -> SentEmail:
    """Execute gmail_send_email. `tool` is the MCP tool handed to the graph node."""
    text = call_tool(tool or get_settings().gmail_send_tool,
                     {"to": [to], "subject": subject, "body": body})
    data = parse_json(text)
    return SentEmail(
        message_id=data.get("id") or data.get("messageId") or data.get("message_id"),
        thread_id=data.get("threadId") or data.get("thread_id"),
        raw=text,
    )
