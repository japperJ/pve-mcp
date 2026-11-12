import asyncio
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CONFIG = os.environ.get("PROXMOX_MCP_CONFIG", str(Path.home() / ".config" / "proxmox-mcp" / "config.json"))
if len(sys.argv) < 2:
    raise SystemExit("usage: python scripts/poll_job.py <job_id>")
JOB = sys.argv[1]


async def main() -> int:
    params = StdioServerParameters(
        command="uvx",
        args=["proxmox-mcp-plus"],
        env={**os.environ, "PROXMOX_MCP_CONFIG": CONFIG},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for name, arguments in (
                ("poll_job", {"target": "pve", "job_id": JOB}),
                ("get_job", {"target": "pve", "job_id": JOB}),
                ("list_snapshots", {"target": "pve", "node": "pve", "vmid": "100", "vm_type": "lxc"}),
            ):
                print(f"=== {name} ===")
                result = await session.call_tool(name, arguments)
                for content in result.content:
                    text = getattr(content, "text", None)
                    if text is not None:
                        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
