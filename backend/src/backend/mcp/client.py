"""Klavis MCP servers (Gmail, Slack) through langchain-mcp-adapters' MultiServerMCPClient.

    from backend.mcp.client import get_tools, call_tool
    tools = get_tools()                         # only REQUIRED_TOOLS, as LangChain tools
    call_tool("gmail_send_email", {...})        # code-side call with code-chosen arguments

Tools are loaded once per process. The graph is synchronous, so async MCP calls run
on their own event loop in a worker thread (works under FastAPI and in the CLI).
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import anyio
import httpx
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from backend.config import get_settings
from backend.core.errors import MCPError

log = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mcp")

GMAIL, SLACK = "klavis-gmail", "klavis-slack"


def required_tools() -> dict[str, str]:
    """Tool name -> server. Only these are loaded; everything else on the servers is ignored."""
    s = get_settings()
    return {s.gmail_send_tool: GMAIL, s.gmail_search_tool: GMAIL, s.gmail_read_tool: GMAIL,
            s.gmail_modify_tool: GMAIL, s.slack_post_tool: SLACK, s.slack_list_channels_tool: SLACK,
            s.slack_history_tool: SLACK}


def _run(coro_factory, timeout: float | None = None):
    timeout = timeout or get_settings().mcp_timeout + 15
    return _pool.submit(lambda: asyncio.run(coro_factory())).result(timeout=timeout)


@lru_cache
def get_client() -> MultiServerMCPClient:
    s = get_settings()
    headers = {"Authorization": f"Bearer {s.klavis_mcp_token}"} if s.klavis_mcp_token else {}
    connections = {}
    if s.klavis_gmail_mcp_url:
        connections[GMAIL] = {"transport": "streamable_http", "url": s.klavis_gmail_mcp_url,
                              "headers": headers}
    if s.klavis_slack_mcp_url:
        connections[SLACK] = {"transport": "streamable_http", "url": s.klavis_slack_mcp_url,
                              "headers": headers}
    # handle_tool_errors=False: a failed send raises, so callers can retry and alert.
    return MultiServerMCPClient(connections, handle_tool_errors=False)


def list_all_tools(server: str | None = None) -> list[BaseTool]:
    """Every tool the server(s) expose (for scripts/list_mcp_tools.py)."""
    return _run(lambda: get_client().get_tools(server_name=server))


@lru_cache
def _required_tool_map() -> dict[str, BaseTool]:
    wanted = required_tools()
    loaded: dict[str, BaseTool] = {}
    for server in sorted(set(wanted.values())):
        if server not in get_client().connections:
            log.warning("MCP server %s not configured (URL missing in .env)", server)
            continue
        for tool in list_all_tools(server):
            if tool.name in wanted:
                loaded[tool.name] = tool
    missing = sorted(set(wanted) - set(loaded))
    if missing:
        log.warning("MCP tools not found: %s (check names with scripts/list_mcp_tools.py)", missing)
    log.info("Loaded %d MCP tools: %s", len(loaded), sorted(loaded))
    return loaded


def get_tools(names: list[str] | None = None) -> list[BaseTool]:
    """The required MCP tools as LangChain tools (optionally a subset by name)."""
    tools = _required_tool_map()
    return [t for n, t in tools.items() if names is None or n in names]


def _to_text(result) -> str:
    if isinstance(result, tuple):            # (content, artifact)
        result = result[0]
    if isinstance(result, list):
        return "\n".join(b.get("text", "") if isinstance(b, dict) else str(getattr(b, "text", b))
                         for b in result)
    return str(result)


def get_tool_map() -> dict[str, BaseTool]:
    """{name: tool} for the required tools; what the graph nodes are given."""
    return dict(_required_tool_map())


def call_tool(tool: BaseTool | str, arguments: dict) -> str:
    """Execute an MCP tool (a loaded tool object, or a required tool's name) with code-chosen
    arguments. Raises MCPError on any failure."""
    if isinstance(tool, str):
        name, tool = tool, _required_tool_map().get(tool)
        if tool is None:
            raise MCPError(f"MCP tool {name} is not available")
    for attempt in (1, 2):
        try:
            return _to_text(_run(lambda: tool.ainvoke(arguments)))
        except Exception as exc:
            if attempt == 1 and _not_delivered(exc):
                log.warning("%s: MCP connection dropped before the request was sent; retrying", tool.name)
                continue
            raise MCPError(f"{tool.name} failed: {exc!r}") from exc


def _not_delivered(exc: BaseException | None) -> bool:
    """A connection failure before the request reached the server (safe to retry, even a send).

    Every call opens a new session to the server; if the server drops it during setup, the
    client's write stream is closed (anyio Broken/ClosedResourceError) or the connect fails.
    """
    if exc is None:
        return False
    if isinstance(exc, (anyio.BrokenResourceError, anyio.ClosedResourceError, httpx.ConnectError)):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_not_delivered(e) for e in exc.exceptions)
    return _not_delivered(exc.__cause__)


def parse_json(text: str) -> dict:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"result": data}
    except (json.JSONDecodeError, TypeError):
        return {}
