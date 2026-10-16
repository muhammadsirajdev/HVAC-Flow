"""Slack through the Klavis Slack MCP server: resolve channel names, post messages, and read a
channel's recent messages (the staff status channel, Run C).
Check tool names with `python scripts/list_mcp_tools.py`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from langchain_core.tools import BaseTool

from backend.config import get_settings
from backend.core.errors import MCPError
from backend.mcp.client import call_tool, parse_json

_CHANNEL_ID = re.compile(r"^[CGD][A-Z0-9]{8,}$")
_ids: dict[str, str] = {}


def resolve_channel(name_or_id: str, tools: Mapping[str, BaseTool] | None = None) -> str:
    """Channel ID for a name like 'slack_urgent_channel' (or '#name'); IDs pass through. Cached.

    Uses slack_user_list_channels (from `tools` when the graph handed them over).
    """
    key = name_or_id.strip().lstrip("#")
    if _CHANNEL_ID.match(key):
        return key
    if key in _ids:
        return _ids[key]
    name = get_settings().slack_list_channels_tool
    tool = (tools or {}).get(name) or name
    data = parse_json(call_tool(tool, {"channel_name": key, "limit": 200, "response_format": "concise"}))
    for ch in data.get("channels", []):
        if ch.get("name") == key:
            _ids[key] = ch["id"]
            return ch["id"]
    raise MCPError(f"Slack channel '{key}' not found (or the Slack user is not in it)")


def post_message(channel: str, text: str, tools: Mapping[str, BaseTool] | None = None) -> str:
    """Execute the Slack post tool (slack_user_post_message) on the resolved channel."""
    name = get_settings().slack_post_tool
    tool = (tools or {}).get(name) or name
    return call_tool(tool, {"channel_id": resolve_channel(channel, tools), "text": text})


def channel_history(channel: str, limit: int = 200) -> list[dict]:
    """Recent top-level messages of a channel, newest first: [{text, ts, user_id}]."""
    data = parse_json(call_tool(get_settings().slack_history_tool,
                                {"channel_id": resolve_channel(channel), "limit": limit}))
    return data.get("messages") or []
