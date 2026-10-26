"""Dependency-free JSON-RPC/MCP server for local research tools."""

from __future__ import annotations

import json
import sys

from research_core.tools import TOOL_DEFINITIONS, execute_tool


SERVER_INFO = {"name": "quant-research", "version": "1.0.0"}


def send(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(message: dict) -> None:
    method = message.get("method")
    rid = message.get("id")
    if method == "notifications/initialized":
        return
    if method == "initialize":
        protocol = (message.get("params") or {}).get("protocolVersion", "2024-11-05")
        send({"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": protocol, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}})
        return
    if method == "ping":
        send({"jsonrpc": "2.0", "id": rid, "result": {}})
        return
    if method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOL_DEFINITIONS}})
        return
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            data = execute_tool(str(params.get("name", "")), params.get("arguments") or {})
            result = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}], "isError": False}
        except Exception as exc:
            result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        send({"jsonrpc": "2.0", "id": rid, "result": result})
        return
    if rid is not None:
        send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown method: {method}"}})


def main() -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            handle(message)
        except Exception as exc:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}})


if __name__ == "__main__":
    main()
