# PVE-MCP

A security-conscious setup guide for running [ProxmoxMCP-Plus](https://github.com/RekklesNA/ProxmoxMCP-Plus) as an MCP server for Proxmox VE, plus validation scripts and a sanitized config template.

This repository is a guide and template, not a fork of ProxmoxMCP-Plus. The server is installed with `uvx proxmox-mcp-plus` (tested with `0.6.10`).

## What it gives you

- Node, VM, and LXC inventory and status
- VM/LXC lifecycle, snapshots, backups, restore, and ISO/template downloads
- LXC command execution via SSH + `pct exec`
- VM command execution via the QEMU guest agent
- Unprivileged, allowlisted host diagnostics
- Persistent job tracking with retry/cancel
- Docker discovery/control inside a guest via the Docker CLI (indirect)

## Architecture

One stdio MCP server with two named targets:

| Target | Purpose | SSH |
| --- | --- | --- |
| `pve` | Proxmox API, LXC `pct exec`, VM guest-agent exec | `mcp-agent`, `use_sudo=true`, sudoers only `/usr/sbin/pct exec *` |
| `pve-host` | Unprivileged host diagnostics | `mcp-agent`, `use_sudo=false`, command allowlist |

The safe default does **not** grant root host control. See the plan's coverage review for what is and is not covered.

## Use with an AI coding agent

The plan is written for Windows/PowerShell; adapt paths and commands for Linux/macOS. Paste this prompt into OpenCode, Claude Code, Cursor, or another coding agent:

```text
Set up PVE-MCP on this machine from this repository.

1. Read README.md and docs/plans/2026-11-12-proxmox-mcp-setup.md completely before changing anything.
2. Use the safe scope only: targets `pve` and `pve-host`; no `pve-root`, no root SSH, and no unrestricted host commands.
3. Ask me for the non-secret values you need: PVE host/IP and SSH port, node name, SSH key path (or permission to generate one), and the LXC/VM IDs to use for validation. For the API token, ask me to place it in the local config file; do not ask me to paste it in chat.
4. Follow the plan task-by-task. Stop and give me the exact commands whenever a step needs my PVE console, a password, or a secret. Never put secrets in chat, logs, git, or the repository.
5. Adapt Windows/PowerShell paths to my OS if needed.
6. Validate with `opencode mcp list`, `scripts/probe_mcp.py`, and the read-only checks. Do not run destructive commands without asking.
7. When done, report what works, what is still manual, and the coverage limits (no console/TTY/file transfer; Docker only via the guest CLI).
```

The repository also includes `AGENTS.md` with the same guardrails for agents that load repository instructions automatically.

## Quick start

1. Read the plan: [`docs/plans/2026-11-12-proxmox-mcp-setup.md`](docs/plans/2026-11-12-proxmox-mcp-setup.md).
2. Create the PVE API user/token and the dedicated SSH user.
3. Copy `config/proxmox-mcp.example.json` to `%USERPROFILE%\.config\proxmox-mcp\config.json` and replace the placeholders.
4. Add the server to OpenCode:

```json
"proxmox": {
  "type": "local",
  "command": ["uvx", "proxmox-mcp-plus"],
  "enabled": true,
  "environment": {
    "PROXMOX_MCP_CONFIG": "C:/Users/<you>/.config/proxmox-mcp/config.json"
  }
}
```

Match the schema already used by your OpenCode config (`mcp.<name>` legacy or `mcp.servers` V2).

5. Restart OpenCode and verify with `opencode mcp list`.
6. Run the standalone probe:

```powershell
uv run --no-project --with mcp python scripts\probe_mcp.py
```

## Validation scripts

All scripts read `PROXMOX_MCP_CONFIG`; if unset, they use `~/.config/proxmox-mcp/config.json`.

- `scripts/probe_mcp.py` — connect, list tools, call `get_nodes` and `get_containers`
- `scripts/validate_mcp.py` — read-only inventory, LXC exec, policy denial, host allowlist
- `scripts/validate_snapshot.py` — snapshot create/list/delete on CT 100
- `scripts/validate_backup.py` — backup CT 100 to `local`
- `scripts/call_tool.py <tool> '<json>'` — call any tool
- `scripts/poll_job.py <job_id>` — poll a job and list CT 100 snapshots

Run them with:

```powershell
uv run --no-project --with mcp python scripts\<name>.py
```

The snapshot/backup examples assume CT 100; change the IDs and storage names for your environment.

## Security notes

- Keep `config.json` outside the repository; `.gitignore` excludes it.
- Use a dedicated PVE API token and SSH key.
- The `pve-host` target is unprivileged and allowlisted. Do not add `/usr/bin/timeout` to sudoers; that is root-equivalent.
- `verify_ssl=false` is only for a trusted LAN. Prefer trusting the PVE CA and re-enabling verification.
- LXC `execute_container_command` is effectively a root shell inside the container; snapshot before mutations.
- Rotate tokens and keys if they are ever exposed.
- Do not expose the MCP server or the PVE API to the internet.

## Coverage and limitations

This setup does not provide 100% of PVE, VM, or LXC control:

- No VNC/SPICE console, interactive TTY, file upload/download, or streaming logs.
- Host control is read-only diagnostics by default.
- Docker is managed indirectly through the guest's Docker CLI; there is no Docker API or compose-stack model.
- A full-control variant (`pve-root`) is described in the plan, but it is root-equivalent and still has the same console/TTY/file-transfer limits.

## Repository layout

```text
docs/plans/2026-11-12-proxmox-mcp-setup.md   # setup plan, coverage review, verification notes
config/proxmox-mcp.example.json              # sanitized config template
scripts/                                     # validation helpers
```

## License

MIT. See [`LICENSE`](LICENSE).
