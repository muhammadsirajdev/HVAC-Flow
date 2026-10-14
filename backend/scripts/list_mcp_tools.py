"""List the Klavis MCP tools and which ones the app uses.

    uv run python scripts/list_mcp_tools.py          # all servers
    uv run python scripts/list_mcp_tools.py -v       # with argument schemas
"""

import json
import sys

from backend.mcp.client import GMAIL, SLACK, get_client, get_tools, list_all_tools, required_tools


def main() -> None:
    verbose = "-v" in sys.argv
    used = required_tools()
    for server in (GMAIL, SLACK):
        if server not in get_client().connections:
            print(f"== {server}: not configured")
            continue
        tools = list_all_tools(server)
        print(f"== {server}: {len(tools)} tools")
        for t in tools:
            mark = "*" if t.name in used else " "
            args = t.args_schema if isinstance(t.args_schema, dict) else t.args_schema.model_json_schema()
            print(f" {mark} {t.name}({', '.join(args.get('properties', {}))})")
            if verbose:
                print("     " + json.dumps(args, indent=2).replace("\n", "\n     "))
    print(f"\n* = required by the app. Loaded: {[t.name for t in get_tools()]}")


if __name__ == "__main__":
    main()
