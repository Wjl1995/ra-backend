import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect local stdio MCP server handlers without transport")
    parser.add_argument("server", choices=["memory", "knowledge", "utility"])
    parser.add_argument("method", choices=["tools/list", "resources/list", "prompts/list"])
    args = parser.parse_args()

    if args.server == "memory":
        from mcp_servers.memory_server.server import build_server
    elif args.server == "knowledge":
        from mcp_servers.knowledge_server.server import build_server
    else:
        from mcp_servers.utility_server.server import build_server

    server = build_server()
    payload = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": args.method, "params": {}})
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
