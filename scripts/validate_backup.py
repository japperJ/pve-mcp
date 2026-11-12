import asyncio
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CONFIG = os.environ.get("PROXMOX_MCP_CONFIG", str(Path.home() / ".config" / "proxmox-mcp" / "config.json"))


async def call(session: ClientSession, name: str, arguments: dict) -> str:
    result = await session.call_tool(name, arguments)
    texts = []
    for content in result.content:
        text = getattr(content, "text", None)
        if text is not None:
            texts.append(text)
    return "\n".join(texts)


async def main() -> int:
    params = StdioServerParameters(
        command="uvx",
        args=["proxmox-mcp-plus"],
        env={**os.environ, "PROXMOX_MCP_CONFIG": CONFIG},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("=== create_backup ===")
            print(await call(session, "create_backup", {
                "target": "pve", "node": "pve", "vmid": "100",
                "storage": "local", "compress": "zstd", "mode": "snapshot",
                "notes": "mcp-validation",
            }))

            listing = ""
            for attempt in range(24):
                listing = await call(session, "list_backups", {"target": "pve", "vmid": "100"})
                if "vzdump-lxc-100" in listing:
                    print(f"=== backup visible after {attempt * 5 + 5}s ===")
                    print(listing)
                    return 0
                await asyncio.sleep(5)
            print("=== backup not visible after 120s ===")
            print(listing)
            return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
