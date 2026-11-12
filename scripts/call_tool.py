import asyncio
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CONFIG = os.environ.get("PROXMOX_MCP_CONFIG", str(Path.home() / ".config" / "proxmox-mcp" / "config.json"))
TOOL = sys.argv[1]
ARGS = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}


async def main() -> int:
    params = StdioServerParameters(
        command="uvx",
        args=["proxmox-mcp-plus"],
        env={**os.environ, "PROXMOX_MCP_CONFIG": CONFIG},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(TOOL, ARGS)
            for content in result.content:
                text = getattr(content, "text", None)
                if text is not None:
                    print(text)
            if getattr(result, "isError", False):
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
