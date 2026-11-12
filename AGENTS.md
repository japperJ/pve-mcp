# PVE-MCP agent instructions

- This repository is a setup guide and template. The actual server is ProxmoxMCP-Plus, installed with `uvx proxmox-mcp-plus`.
- Read `README.md` and `docs/plans/2026-11-12-proxmox-mcp-setup.md` before changing anything.
- Default to the safe scope: targets `pve` and `pve-host`. Do not add a root `pve-root` target, root SSH, or unrestricted host commands unless the user explicitly asks.
- Never commit `config.json`, tokens, keys, logs, SQLite job files, or backups. Use `config/proxmox-mcp.example.json` as the template.
- Stop and ask the user to run steps that need the PVE console, a password, or a secret. Do not ask for secrets in chat.
- Validate with `opencode mcp list`, `scripts/probe_mcp.py`, and the read-only checks. Ask before destructive operations.
- Report the coverage limits: no VNC/SPICE console, interactive TTY, file transfer, or streaming logs. Docker is managed indirectly through the guest's Docker CLI.
