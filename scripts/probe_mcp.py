import asyncio
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CONFIG = os.environ.get("PROXMOX_MCP_CONFIG", str(Path.home() / ".config" / "proxmox-mcp" / "config.json"))


async def main() -> int:
    params = StdioServerParameters(
        command="uvx",
        args=["proxmox-mcp-plus"],
        env={**os.environ, "PROXMOX_MCP_CONFIG": CONFIG},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(tool.name for tool in tools.tools)
            print(f"tools={len(names)}")
            print(",".join(names))
            for name, arguments in (
                ("get_nodes", {"target": "pve"}),
                ("get_containers", {"target": "pve"}),
            ):
                result = await session.call_tool(name, arguments)
                print(f"--- {name} ---")
                for content in result.content:
                    text = getattr(content, "text", None)
                    if text is not None:
                        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
