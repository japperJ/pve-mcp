import asyncio
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CONFIG = os.environ.get("PROXMOX_MCP_CONFIG", str(Path.home() / ".config" / "proxmox-mcp" / "config.json"))
SNAP = "pre-mcp-validation"


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

            print("=== create_snapshot ===")
            print(await call(session, "create_snapshot", {
                "target": "pve", "node": "pve", "vmid": "100",
                "snapname": SNAP, "description": "Before MCP validation", "vm_type": "lxc",
            }))

            for attempt in range(20):
                listing = await call(session, "list_snapshots", {
                    "target": "pve", "node": "pve", "vmid": "100", "vm_type": "lxc",
                })
                if SNAP in listing:
                    print(f"=== snapshot visible after {attempt + 1} check(s) ===")
                    print(listing)
                    break
                await asyncio.sleep(2)
            else:
                print("snapshot did not appear in time")
                return 1

            print("=== delete_snapshot ===")
            print(await call(session, "delete_snapshot", {
                "target": "pve", "node": "pve", "vmid": "100",
                "snapname": SNAP, "vm_type": "lxc",
            }))

            for attempt in range(20):
                listing = await call(session, "list_snapshots", {
                    "target": "pve", "node": "pve", "vmid": "100", "vm_type": "lxc",
                })
                if SNAP not in listing:
                    print(f"=== snapshot removed after {attempt + 1} check(s) ===")
                    print(listing)
                    break
                await asyncio.sleep(2)
            else:
                print("snapshot still present after delete")
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
