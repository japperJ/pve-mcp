import asyncio
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CONFIG = os.environ.get("PROXMOX_MCP_CONFIG", str(Path.home() / ".config" / "proxmox-mcp" / "config.json"))

CALLS = [
    ("list_targets", {}),
    ("get_nodes", {"target": "pve"}),
    ("get_node_status", {"target": "pve", "node": "pve"}),
    ("get_containers", {"target": "pve"}),
    ("get_container_config", {"target": "pve", "node": "pve", "vmid": "100"}),
    ("get_container_ip", {"target": "pve", "node": "pve", "vmid": "100"}),
    ("get_storage", {"target": "pve"}),
    ("get_cluster_status", {"target": "pve"}),
    (
        "execute_container_command",
        {"target": "pve", "selector": "100", "command": "/usr/local/bin/pihole -v"},
    ),
    (
        "execute_container_command",
        {"target": "pve", "selector": "100", "command": "rm -rf /tmp/pve-mcp-policy-test"},
    ),
    ("execute_node_command", {"target": "pve-host", "node": "pve", "command": "uptime"}),
    ("execute_node_command", {"target": "pve-host", "node": "pve", "command": "whoami"}),
]


async def main() -> int:
    params = StdioServerParameters(
        command="uvx",
        args=["proxmox-mcp-plus"],
        env={**os.environ, "PROXMOX_MCP_CONFIG": CONFIG},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for name, arguments in CALLS:
                print(f"=== {name} {arguments} ===")
                try:
                    result = await session.call_tool(name, arguments)
                    for content in result.content:
                        text = getattr(content, "text", None)
                        if text is not None:
                            print(text)
                    if getattr(result, "isError", False):
                        print("TOOL_ERROR")
                except Exception as error:
                    print(f"CALL_ERROR: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
