# Proxmox MCP Setup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Register one ProxmoxMCP-Plus stdio MCP server in OpenCode that can inspect and manage the `pve` homelab (nodes, LXC/VMs, snapshots, backups, guest commands, and guarded host commands).

**Architecture:** One `uvx proxmox-mcp-plus` process launched by OpenCode. Two named targets point at the same PVE API: `pve` (API + LXC `pct exec` over SSH with scoped sudo) and `pve-host` (unprivileged, allowlisted host commands over SSH). Credentials are a dedicated PVE API user/token and a dedicated SSH key/user. Command execution is gated by ProxmoxMCP-Plus `command_policy`.

**Tech Stack:** Proxmox VE 9.1.1, ProxmoxMCP-Plus (PyPI, `uvx`), OpenSSH/Paramiko, OpenCode local MCP servers.

---

## Common pitfalls this plan handles

These are the failure modes that a naive config usually hits:

1. **Self-signed TLS guard:** `verify_ssl=false` is rejected unless `security.dev_mode=true` (legacy config) or `allow_insecure_tls=true` (named targets). This plan uses named targets with `allow_insecure_tls: true`.
2. **Command policy default:** `command_policy.mode` defaults to `deny_all`. With no allow patterns, both `execute_container_command` and `execute_node_command` are blocked. This plan sets `audit_only` for LXC and `allowlist` for host.
3. **Host command sudo mismatch:** with `use_sudo=true`, `execute_node_command` runs `sudo -n /usr/bin/timeout ... /bin/sh -c '<command>'`, but the proposed sudoers rule only allows `/usr/sbin/pct exec`. Host commands would be denied. This plan uses a separate `pve-host` target with `use_sudo=false` for unprivileged host commands.
4. **OpenCode schema:** some OpenCode installs use the legacy direct `mcp.<name>` + `enabled` schema, not V2's `mcp.servers`. Match the schema already in use; do not convert the file.
5. **PowerShell key generation:** use `-N ''` in PowerShell 7, not `-N '""'`, or the key gets a literal two-character passphrase.
6. **known_hosts encoding:** append with `Add-Content -Encoding ascii`; PowerShell redirection can write UTF-16, which Paramiko will not parse.

## Decisions

- **API identity:** recommended `mcp-api@pve` + token `mcp-token`, roles `PVEVMAdmin`, `PVEDatastoreAdmin`, `PVEAuditor`, `privsep 0`. Fallback: a `root@pam` token only if a required API call is denied.
- **TLS:** `verify_ssl=false` + `allow_insecure_tls=true` on the trusted LAN. Optional later: trust the PVE CA and re-enable verification.
- **LXC commands:** `command_policy.mode=audit_only` with the default deny patterns. This is effectively a root shell inside containers; take snapshots before mutations.
- **Host commands:** `pve-host` is unprivileged and allowlisted for read-only diagnostics. Root-level host administration is deliberately not granted; add explicit sudoers entries only if needed later.
- **Transport:** stdio only. No OpenAPI bridge, no native MCP HTTP, no extra MCP servers.
- **No secrets in git:** the live config lives outside the repository at `$HOME\.config\proxmox-mcp\config.json`.

## Coverage review: does this deliver 100%?

Short answer: **no**. ProxmoxMCP-Plus exposes a curated Proxmox surface, and this plan deliberately keeps the PVE host unprivileged. It is a safe default, not a complete replacement for the PVE UI, SSH, or a purpose-built Docker tool.

| Area | What this plan can do | What is missing | Verdict |
| --- | --- | --- | --- |
| **PVE host** | Read node status/diagnostics/time, storage, bridges, cluster status/join info, syslog/task/cluster/firewall logs; unprivileged allowlisted commands (`uptime`, `df`, `free`, `systemctl status`, `journalctl`); API-driven VM/LXC lifecycle | Node reboot/shutdown/power, network/DNS/time/hostname config, storage/ZFS/LVM/Ceph/SDN/HA config, firewall rules, service/package management, users/ACLs, cluster join/leave, certificates, kernel, host file transfer, interactive shell, console | **No** — host is read-only diagnostics in this plan |
| **VMs** | List/status/config, create, clone, start/stop/shutdown/reset/delete, offline migration, snapshots, backup/restore, ISO download, cloud-init basics, serial console config, QEMU guest-agent exec, IP discovery | Disk resize/move, PCI/USB passthrough, machine/BIOS/EFI/TPM/CPU flags, template creation, lock/unlock, HA/replication, firewall rules, scheduled backups, VNC/SPICE console, file copy, interactive shell, custom cloud-init/hookscripts | **No** — common lifecycle, not every config knob |
| **LXC** | List/status/config, create, start/stop/restart/delete, migration, snapshots, backup/restore, `pct exec`, basic network/resources, SSH-key injection, templates | Clone, template creation, mount points/bind mounts, features beyond nesting, startup order, tags/DNS, firewall rules, console, file push/pull, interactive shell, unprivileged/privileged conversion, `pct mount`/`pct fstrim` | **No** — common lifecycle, not every config knob |
| **Docker** | Indirect only: run `docker` CLI inside an LXC via `execute_container_command`, or inside a VM via `execute_vm_command` (guest agent required) | Native Docker inventory/API, compose stack modeling, streaming logs, TTY, 60s timeout, 1 MiB output, cross-guest discovery, file copy, Docker on the PVE host under the unprivileged target | **Partial/indirect** |

**Docker, specifically:** there are no Docker tools in ProxmoxMCP-Plus. If Docker is inside an LXC guest (for example CT 101), `execute_container_command` can run `docker ps -a`, `docker start/stop/restart`, `docker exec` (non-interactive), `docker logs --tail`, and `docker compose ...` (subject to the 60s timeout). If Docker is inside a VM, the same is possible through `execute_vm_command`, but only when the QEMU guest agent is installed, running, and permits `guest-exec`. The agent can "find" containers by running `docker ps` in each guest; there is no automatic inventory and no Docker API.

**To get closer to 100%:**

- **Full-control variant:** add a `pve-root` target with a root SSH key, `use_sudo=false`, `allow_node_commands=true`, and `command_policy.mode=audit_only` (or a broad allowlist for `qm`, `pct`, `pvesh`, `systemctl`, `apt`, `docker`). This gives root-equivalent host control and lets the agent use `qm`/`pct`/`pvesh` for operations the native tools do not expose. It also removes the "guarded" property: treat it as root access.
- **API breadth:** use a `root@pam` token (privsep 0) or a broader role if a native API call is denied. API tokens still cannot access VM/system console endpoints.
- **Residual gaps even with root:** no VNC/SPICE console, no interactive TTY/stdin, no MCP file upload/download, 60s command timeout, 8,192-character command limit, 1 MiB output cap, and no streaming logs. Use the PVE web UI or a direct SSH session for those.
- **True 100%:** ProxmoxMCP-Plus alone is not the right tool. A raw Proxmox API MCP, a console-capable server, or a custom server would be needed, which conflicts with the one-server constraint in this guide.

## Prerequisites

- Windows box `<windows-host-ip>`, PowerShell 7, `uv`/`uvx` installed (`uvx --version`).
- PVE `pve.example.com`, node `pve`, root console access.
- PVE API reachable at `https://pve.example.com:8006`.
- The PVE console is easier for the host-side setup than the self-signed web UI in the preview browser.
- No existing `~/.ssh/proxmox_mcp` key; `~/.ssh/known_hosts` may exist.

---

## Task 1: Generate the SSH key and trust the PVE host key (Windows)

**Files:**
- Create: `$HOME\.ssh\proxmox_mcp`
- Create: `$HOME\.ssh\proxmox_mcp.pub`
- Modify: `$HOME\.ssh\known_hosts`

**Step 1: Create the key without a passphrase**

```powershell
New-Item -ItemType Directory -Force -Path "$HOME\.ssh" | Out-Null
if (Test-Path "$HOME\.ssh\proxmox_mcp") { throw "Key already exists: $HOME\.ssh\proxmox_mcp" }
ssh-keygen -t ed25519 -f "$HOME\.ssh\proxmox_mcp" -N '' -C "pve-mcp@$env:COMPUTERNAME"
```

Expected: `Your identification has been saved in ...` and `Your public key has been saved in ...`.

**Step 2: Verify there is no passphrase**

```powershell
ssh-keygen -y -P '' -f "$HOME\.ssh\proxmox_mcp" | Select-Object -First 1
```

Expected: prints the `ssh-ed25519 ...` public key without prompting. If it prompts, delete both key files and repeat Step 1 with the correct empty-string argument.

**Step 3: Print the public key for the PVE console**

```powershell
Get-Content "$HOME\.ssh\proxmox_mcp.pub"
```

Expected: one line starting with `ssh-ed25519`. Keep it for Task 2.

**Step 4: Add the PVE host key to known_hosts**

```powershell
ssh-keyscan -H pve.example.com 2>$null | Add-Content -Encoding ascii "$HOME\.ssh\known_hosts"
ssh-keygen -F pve.example.com -f "$HOME\.ssh\known_hosts"
```

Expected: `# Host pve.example.com found: line N`.

**Failure modes:**
- `ssh-keygen -y` prompts: the key has a passphrase. Regenerate.
- `ssh-keyscan` returns nothing: check that `pve.example.com:22` is reachable.
- `ssh-keygen -F` says not found: the host key was not appended; check the file encoding.

---

## Task 2: Create the PVE SSH user and scoped sudo rule

Run these on the PVE console as `root`.

**Step 1: Install sudo if missing**

```bash
apt update && apt install -y sudo
```

Expected: `sudo is already the newest version` or a successful install.

**Step 2: Create the dedicated SSH user**

```bash
id mcp-agent 2>/dev/null || useradd -m -s /bin/bash mcp-agent
passwd -l mcp-agent
install -d -m 700 -o mcp-agent -g mcp-agent /home/mcp-agent/.ssh
```

Expected: the user exists, has a locked password, and owns `/home/mcp-agent/.ssh` with mode `700`.

**Step 3: Install the public key from Task 1**

Replace `ssh-ed25519 AAAA...REPLACE...` with the exact line printed in Task 1.

```bash
cat > /tmp/mcp-agent.pub <<'EOF'
ssh-ed25519 AAAA...REPLACE... pve-mcp@WINDOWS
EOF
install -m 600 -o mcp-agent -g mcp-agent /tmp/mcp-agent.pub /home/mcp-agent/.ssh/authorized_keys
rm -f /tmp/mcp-agent.pub
chown -R mcp-agent:mcp-agent /home/mcp-agent/.ssh
```

If `authorized_keys` already contains keys you want to keep, append instead of overwriting:

```bash
cat /tmp/mcp-agent.pub >> /home/mcp-agent/.ssh/authorized_keys
chmod 600 /home/mcp-agent/.ssh/authorized_keys
chown mcp-agent:mcp-agent /home/mcp-agent/.ssh/authorized_keys
```

**Step 4: Grant passwordless sudo only for `pct exec`**

```bash
echo 'mcp-agent ALL=(root) NOPASSWD: /usr/sbin/pct exec *' > /etc/sudoers.d/mcp-agent
chmod 440 /etc/sudoers.d/mcp-agent
visudo -c -f /etc/sudoers.d/mcp-agent
```

Expected: `/etc/sudoers.d/mcp-agent: parsed OK`.

This rule is intentionally narrow. Do **not** add `/usr/bin/timeout` to sudoers: ProxmoxMCP-Plus wraps host commands as `sudo timeout ... sh -c '<command>'`, so allowing `timeout` would grant a root shell. Host commands use the unprivileged `pve-host` target instead.

**Step 5 (optional): Read-only journal access**

Only if `journalctl` host checks should work as `mcp-agent`:

```bash
usermod -aG systemd-journal mcp-agent
```

The new SSH session picks up the group. Reconnect after this change. `uptime`, `df`, `free`, and `cat /etc/os-release` do not need it.

**Failure modes:**
- `useradd: user 'mcp-agent' already exists`: continue; do not recreate.
- `visudo -c` fails: the file has a syntax error; remove it and retry.
- SSH still asks for a password: check `authorized_keys` ownership/mode and `sshd_config` (`PubkeyAuthentication yes`).

---

## Task 3: Create the PVE API user and token

Run these on the PVE console as `root`.

**Step 1: Create a dedicated API user**

```bash
pveum user add mcp-api@pve --comment "Proxmox MCP automation"
```

If PVE insists on a password, set a random one and discard it; token auth does not need it:

```bash
pveum user add mcp-api@pve --comment "Proxmox MCP automation" --password "$(openssl rand -base64 24)"
```

**Step 2: Grant scoped roles at the root path**

```bash
pveum acl modify / --users mcp-api@pve --roles PVEVMAdmin
pveum acl modify / --users mcp-api@pve --roles PVEDatastoreAdmin
pveum acl modify / --users mcp-api@pve --roles PVEAuditor
```

Expected: no output on success. If a role name is rejected, check `pveum role list`. `PVEAdmin` is a broader fallback; `root@pam` is the last resort.

**Step 3: Create the API token with full user privileges**

```bash
pveum user token add mcp-api@pve mcp-token --privsep 0
```

Expected: a table containing `tokenid  mcp-api@pve!mcp-token` and a one-time `value` UUID. Copy the `value` immediately; it cannot be retrieved again.

**Step 4: Verify the user, ACL, and token**

```bash
pveum user token list mcp-api@pve
pveum user permissions mcp-api@pve
```

Expected: the token is listed and the permissions include the VM, datastore, and audit privileges.

**Note:** API tokens cannot access VM/system console endpoints. `execute_vm_command` uses the QEMU guest-agent API, not the console, so it is compatible with token auth. The LXC path uses SSH + `pct exec`, not the token.

---

## Task 4: Verify SSH and `pct exec` from Windows

**Step 1: Verify SSH**

```powershell
ssh -i "$HOME\.ssh\proxmox_mcp" -o BatchMode=yes -o StrictHostKeyChecking=yes mcp-agent@pve.example.com "echo SSH OK"
```

Expected: `SSH OK`.

**Step 2: Verify scoped sudo and `pct exec`**

```powershell
ssh -i "$HOME\.ssh\proxmox_mcp" -o BatchMode=yes -o StrictHostKeyChecking=yes mcp-agent@pve.example.com "sudo -n /usr/sbin/pct exec 100 -- /usr/local/bin/pihole -v"
```

Expected: Pi-hole version output for CT 100 (`core`, `web`, `ftl`). The example environment used `core=v6.6 web=v6.6.1 ftl=v6.9`. Note: `pct exec` can start with an empty `PATH`, so use absolute paths for binaries under `/usr/local/bin` (verified: `/usr/local/bin/pihole`).

**Failure modes:**
- `Permission denied (publickey)`: `authorized_keys`, ownership, or mode is wrong.
- `Host key verification failed`: rerun the `ssh-keyscan` step.
- `sudo: a password is required`: `/etc/sudoers.d/mcp-agent` is missing or wrong; rerun `visudo -c`.
- `pct: command not found`: use `/usr/sbin/pct` exactly.
- Container not running: start CT 100 in the PVE UI/console first.

---

## Task 5: Create the MCP config file

**Files:**
- Create: `$HOME\.config\proxmox-mcp\config.json`
- Create: `$HOME\.config\proxmox-mcp\` (directory; logs and SQLite live here)

**Step 1: Create the directory and restrict it to the current user**

```powershell
$cfgDir = "$HOME\.config\proxmox-mcp"
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
icacls $cfgDir /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F"
Test-Path $cfgDir
```

Expected: `True`.

**Step 2: Write the config**

Save this as `$HOME\.config\proxmox-mcp\config.json`. Replace both `REPLACE_WITH_PVE_TOKEN_SECRET` placeholders with the token value from Task 3.

```json
{
  "targets": {
    "pve": {
      "host": "pve.example.com",
      "port": 8006,
      "verify_ssl": false,
      "allow_insecure_tls": true,
      "service": "PVE",
      "auth": {
        "user": "mcp-api@pve",
        "token_name": "mcp-token",
        "token_value": "REPLACE_WITH_PVE_TOKEN_SECRET"
      },
      "ssh": {
        "user": "mcp-agent",
        "port": 22,
        "key_file": "<YOUR_HOME>/.ssh/proxmox_mcp",
        "use_sudo": true,
        "known_hosts_file": "<YOUR_HOME>/.ssh/known_hosts",
        "strict_host_key_checking": true,
        "host_overrides": {
          "pve": "pve.example.com"
        },
        "allow_node_commands": false
      },
      "command_policy": {
        "mode": "audit_only",
        "allow_patterns": [],
        "deny_patterns": [
          "(^|\\s)rm\\s+-rf(\\s|$)",
          ":\\(\\)\\{:\\|:\\&\\};:"
        ],
        "require_approval_token": false,
        "high_risk_mode": "audit_only"
      }
    },
    "pve-host": {
      "host": "pve.example.com",
      "port": 8006,
      "verify_ssl": false,
      "allow_insecure_tls": true,
      "service": "PVE",
      "auth": {
        "user": "mcp-api@pve",
        "token_name": "mcp-token",
        "token_value": "REPLACE_WITH_PVE_TOKEN_SECRET"
      },
      "ssh": {
        "user": "mcp-agent",
        "port": 22,
        "key_file": "<YOUR_HOME>/.ssh/proxmox_mcp",
        "use_sudo": false,
        "known_hosts_file": "<YOUR_HOME>/.ssh/known_hosts",
        "strict_host_key_checking": true,
        "host_overrides": {
          "pve": "pve.example.com"
        },
        "allow_node_commands": true
      },
      "command_policy": {
        "mode": "allowlist",
        "allow_patterns": [
          "uptime",
          "id",
          "df -h",
          "free -h",
          "cat /etc/os-release",
          "systemctl status [A-Za-z0-9_.@-]+",
          "journalctl -u [A-Za-z0-9_.@-]+ -n [0-9]+"
        ],
        "deny_patterns": [
          "(^|\\s)rm\\s+-rf(\\s|$)",
          ":\\(\\)\\{:\\|:\\&\\};:"
        ],
        "require_approval_token": false,
        "high_risk_mode": "audit_only"
      }
    }
  },
  "logging": {
    "level": "INFO",
    "file": "<YOUR_HOME>/.config/proxmox-mcp/proxmox-mcp.log"
  },
  "mcp": {
    "transport": "STDIO"
  },
  "security": {
    "dev_mode": false
  },
  "jobs": {
    "sqlite_path": "<YOUR_HOME>/.config/proxmox-mcp/proxmox-jobs.sqlite3",
    "poll_cache_ttl": 1
  }
}
```

**Step 3: Validate the JSON**

```powershell
Get-Content "$HOME\.config\proxmox-mcp\config.json" -Raw | ConvertFrom-Json | Out-Null
"JSON OK"
```

Expected: `JSON OK`.

**Why two targets:**
- `pve`: `use_sudo=true`, so LXC `pct exec` works; `allow_node_commands=false`, so host commands are not exposed through this target.
- `pve-host`: `use_sudo=false`, so host commands run as unprivileged `mcp-agent`; `allow_node_commands=true`; command policy is a full-match allowlist.
- With multiple targets, every tool call must pass `target`. Use `target="pve"` for API/LXC/VM work and `target="pve-host"` only for `execute_node_command`.

**Why the token appears twice:** ProxmoxMCP-Plus reads auth per target. Both targets use the same API token. Rotate both entries together.

**Failure modes:**
- Startup error `Insecure TLS configuration blocked`: `allow_insecure_tls` is missing or false on a target.
- Startup error `Top-level ssh is only valid for legacy configuration`: move `ssh` inside each target (already done).
- Startup error `Unknown Proxmox target`: check the `target` argument spelling.
- JSON parse error: use a JSON-aware editor; do not use smart quotes.

---

## Task 6: Prewarm `uvx` and probe the MCP server over stdio

**Files:**
- Create (optional but recommended): `scripts\probe_mcp.py`

**Step 1: Prewarm the package environment**

```powershell
uvx --from proxmox-mcp-plus python -c "import proxmox_mcp; print('proxmox_mcp import OK')"
```

Expected: `proxmox_mcp import OK`. This downloads and caches the package so OpenCode's startup timeout is less likely to be hit.

**Step 2: Create the probe script**

```python
import asyncio
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CONFIG = os.path.expandvars(r"$HOME\.config\proxmox-mcp\config.json")


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
                    if getattr(content, "type", None) == "text":
                        print(content.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

**Step 3: Run the probe**

```powershell
uv run --no-project --with mcp python scripts\probe_mcp.py
```

Expected:
- `tools=` count greater than 40.
- The list includes `execute_container_command`, `execute_node_command`, `get_nodes`, and `get_containers`.
- `get_nodes` returns node `pve` online.
- `get_containers` returns CT 100-105.

**Step 4: Check the server log on failure**

```powershell
Get-Content "$HOME\.config\proxmox-mcp\proxmox-mcp.log" -Tail 100
```

Expected: startup lines including `Container command execution enabled (SSH configured for user 'mcp-agent')` and no TLS/auth validation errors.

**Failure modes:**
- `Configuration validation failed`: check the config JSON and token placeholders.
- `401`/`403` from PVE: token value or ACLs are wrong.
- `SSH error connecting`: key path, known_hosts, or `mcp-agent` setup is wrong.
- `no [ssh] section`: the `ssh` block is nested incorrectly.

---

## Task 7: Register the server in OpenCode

**Files:**
- Modify: `$HOME\.config\opencode\opencode.json`

**Step 1: Add the `proxmox` entry under the existing `mcp` object**

The current file uses the legacy direct-entry schema. Add this after the existing `android` entry, keeping the surrounding commas correct:

```jsonc
    "proxmox": {
      "type": "local",
      "command": ["uvx", "proxmox-mcp-plus"],
      "enabled": true,
      "environment": {
        "PROXMOX_MCP_CONFIG": "C:/Users/<you>/.config/proxmox-mcp/config.json"
      }
    }
```

Do **not** change the file to `mcp.servers`; the existing servers (`pencil`, `context7`, `rea`, `android`, etc.) are configured with the legacy shape and currently work.

**Step 2: Validate the JSON**

```powershell
Get-Content "$HOME\.config\opencode\opencode.json" -Raw | ConvertFrom-Json | Out-Null
"JSON OK"
```

Expected: `JSON OK`.

**Step 3: Restart OpenCode/T3 Code fully**

The MCP server list is read at startup. Restart the app/session, then check:

```powershell
opencode mcp list
```

Expected: `proxmox` is listed as connected. If the CLI is not on PATH, use `/mcps` in the app.

**Step 4: First agent call**

Ask the agent to call `proxmox_get_nodes` with `target="pve"`. The tool name is prefixed by the server name (`proxmox_get_nodes`).

Expected: node `pve`, status online, CPU/memory/uptime.

**Failure modes:**
- Server not listed: JSON entry is in the wrong object or the app was not restarted.
- Startup timeout: rerun the prewarm step; check whether `uvx` is on the PATH used by the OpenCode process.
- Tools missing: check the server log; a config validation failure prevents tool registration.

---

## Task 8: Validate read-only inventory

Call these through the agent. Every call needs `target="pve"`.

| Tool | Arguments | Expected |
| --- | --- | --- |
| `proxmox_get_nodes` | `{"target":"pve"}` | node `pve`, online |
| `proxmox_get_node_status` | `{"target":"pve","node":"pve"}` | CPU/memory/uptime |
| `proxmox_get_containers` | `{"target":"pve","include_stats":true}` | CT 100-105, statuses |
| `proxmox_get_container_config` | `{"target":"pve","node":"pve","vmid":"100"}` | hostname `<ct-100-hostname>` |
| `proxmox_get_container_ip` | `{"target":"pve","node":"pve","vmid":"100"}` | `<ct-100-ip>` |
| `proxmox_get_storage` | `{"target":"pve"}` | `local`, `local-lvm` |
| `proxmox_get_cluster_status` | `{"target":"pve"}` | cluster status |
| `proxmox_list_targets` | `{}` | `pve`, `pve-host` |

If any read fails with `Permission denied`, add `PVEAuditor` or the specific privilege to `mcp-api@pve`, then retry.

---

## Task 9: Validate LXC command execution and policy

**Step 1: Read-only Pi-hole version check**

```text
proxmox_execute_container_command
  target="pve"
  selector="100"
  command="/usr/local/bin/pihole -v"
```

Expected: `success: true`, output with `core=v6.6`, `web=v6.6.1`, `ftl=v6.9`. `pct exec` may have an empty `PATH`; use absolute paths for Pi-hole and other `/usr/local/bin` tools.

**Step 2: Confirm the execution identity**

```text
proxmox_execute_container_command
  target="pve"
  selector="100"
  command="hostname && id"
```

Expected: `<ct-100-hostname>` and `uid=0(root)`. `pct exec` runs as root inside the container by design.

**Step 3: Confirm the deny policy blocks destructive commands**

```text
proxmox_execute_container_command
  target="pve"
  selector="100"
  command="rm -rf /tmp/pve-mcp-policy-test"
```

Expected: `success: false`, code `CMD_POLICY_DENY_PATTERN`, and the command is not executed.

**Step 4 (optional): Confirm the timeout path**

```text
proxmox_execute_container_command
  target="pve"
  selector="100"
  command="sleep 90"
```

Expected after about 60 seconds: `success: false`, code `COMMAND_TIMEOUT`, `timed_out: true`, `exit_code: 124`. This takes ~70 seconds; skip unless needed.

**Failure modes:**
- `SSH is not configured for target 'pve'`: the `ssh` section is missing from the target.
- `pct: not found` or `sudo: a password is required`: Task 2/4 is incomplete.
- `CMD_POLICY_NOT_ALLOWLISTED`: `pve` was left in `deny_all`; it must be `audit_only` or have allow patterns.
- `Container is not running`: start CT 100.

---

## Task 10: Validate guarded host command execution

Use `target="pve-host"` for all host commands. This target runs as unprivileged `mcp-agent`.

**Step 1: Allowed diagnostics**

```text
proxmox_execute_node_command target="pve-host" node="pve" command="uptime"
proxmox_execute_node_command target="pve-host" node="pve" command="df -h"
proxmox_execute_node_command target="pve-host" node="pve" command="cat /etc/os-release"
```

Expected: `success: true` for each, with normal output. `uptime` shows load average; `df -h` shows filesystems; `cat /etc/os-release` shows Debian/PVE.

**Step 2: Confirm the allowlist rejects an unlisted command**

```text
proxmox_execute_node_command target="pve-host" node="pve" command="whoami"
```

Expected: `success: false`, code `CMD_POLICY_NOT_ALLOWLISTED`. This proves the full-match allowlist is active.

**Step 3 (optional): journal check**

```text
proxmox_execute_node_command target="pve-host" node="pve" command="journalctl -u pveproxy -n 20"
```

If it fails with permission denied, add `mcp-agent` to `systemd-journal` (Task 2, Step 5) and reconnect.

**Failure modes:**
- `Host SSH commands are disabled for this target`: the call used `target="pve"`; use `target="pve-host"`.
- `SSH error`/`sudo` error: `pve-host` must have `use_sudo=false`; it does not have the `pct exec` sudo rule.
- `CMD_POLICY_NOT_ALLOWLISTED`: extend `allow_patterns` for the exact command form. Remember host allow patterns are full-match.

---

## Task 11: Validate snapshot and backup workflows

**Step 1: Create a pre-validation LXC snapshot**

```text
proxmox_create_snapshot
  target="pve"
  node="pve"
  vmid="100"
  snapname="pre-mcp-validation"
  description="Before MCP validation"
  vm_type="lxc"
```

Expected: snapshot created; response includes `Task ID` and `Job ID`.

**Step 2: Poll the job**

```text
proxmox_poll_job target="pve" job_id="<job_id>"
```

Expected: status `success`/stopped with `OK`. If it stays running, poll again.

**Step 3: List snapshots**

```text
proxmox_list_snapshots target="pve" node="pve" vmid="100" vm_type="lxc"
```

Expected: `pre-mcp-validation` appears.

**Important:** the container stays locked until the create job finishes. Poll the create job to `completed`/`OK` before deleting. If the delete fails with `CT is locked (snapshot)`, poll the create job, then retry with `retry_job` or call `delete_snapshot` again.

**Step 4: Delete the test snapshot**

```text
proxmox_delete_snapshot
  target="pve"
  node="pve"
  vmid="100"
  snapname="pre-mcp-validation"
  vm_type="lxc"
```

Expected: deletion task submitted; poll again.

**Step 5 (optional): Create a backup**

First check storage and existing backups:

```text
proxmox_get_storage target="pve"
proxmox_list_backups target="pve" vmid="100"
```

Then create a small backup on `local`:

```text
proxmox_create_backup
  target="pve"
  node="pve"
  vmid="100"
  storage="local"
  compress="zstd"
  mode="snapshot"
  notes="mcp-validation"
```

Expected: `Task ID`/`Job ID`; `proxmox_list_backups` shows the new archive after the task completes. Keep the backup as a safety artifact unless the user asks to delete it.

**Failure modes:**
- `Permission denied`: `PVEVMAdmin`/`PVEDatastoreAdmin` missing; check `pveum user permissions`.
- `storage 'local' does not exist`: use the storage name returned by `get_storage`.
- `Job ID: n/a`: the server was started without a job store; check `jobs.sqlite_path` and directory permissions.

---

## Task 12: Optional — secure the Pi-hole web UI

This is a follow-up use case, not an MCP acceptance criterion. The handover found the Pi-hole UI open on the LAN and the `root@<ct-100-ip>` password unknown.

1. Snapshot CT 100 first (Task 11 pattern).
2. Set the web password from the PVE console (interactive, avoids logging the secret):

```bash
pct exec 100 -- /usr/local/bin/pihole setpassword
```

3. Verify `http://<ct-100-ip>/admin` now prompts for a password.
4. Do not put the password in this plan, the repo, or an MCP tool call. If using the MCP path, run it only after confirming command logs do not retain the value, or use a throwaway password and rotate it.

If `/usr/local/bin/pihole setpassword` is unavailable in Pi-hole v6, use the Settings UI or edit `/etc/pihole/pihole.toml` and restart FTL.

---

## Task 12b: Discover and control Docker containers (optional)

This is indirect: it uses the guest shell, not a Docker API.

**Step 1: Check a Docker-host LXC (for example CT 101) for the Docker CLI and containers**

```text
proxmox_execute_container_command
  target="pve"
  selector="101"
  command="/usr/bin/docker ps -a --format '{{.Names}} | {{.Image}} | {{.Status}}'"
```

Expected: `/usr/bin/docker` and the container table (for example, `<name> | <image> | Up ...`). If `/usr/bin/docker` is missing, Docker is not in this CT.

**Step 2: Control a container (non-interactive)**

```text
proxmox_execute_container_command target="pve" selector="101" command="/usr/bin/docker restart <name>"
proxmox_execute_container_command target="pve" selector="101" command="/usr/bin/docker logs --tail 100 <name>"
proxmox_execute_container_command target="pve" selector="101" command="/usr/bin/docker exec <name> <command>"
proxmox_execute_container_command target="pve" selector="101" command="/usr/bin/docker compose -f /path/compose.yml ps"
```

`docker exec -it` will not work (no TTY). `docker logs -f` will hit the 60-second timeout. `docker compose up --build` may exceed 60 seconds; run it detached or as a host-side systemd unit and poll.

**Step 3: Docker inside a VM**

```text
proxmox_execute_vm_command target="pve" node="pve" vmid="<vmid>" command="command -v docker && docker ps -a"
```

Requires the QEMU guest agent, a running VM, and `guest-exec` support. There are no VMs in the current inventory, so this is a template for later.

**Step 4: Docker on the PVE host**

The `pve-host` target is unprivileged and allowlisted, so `docker ps` is blocked. Do not add it unless you accept the risk; if needed, add `docker ps`/`docker inspect` to the allowlist and put `mcp-agent` in the `docker` group, or use the full-control `pve-root` variant.

---

## Task 13: Hardening, acceptance criteria, and rollback

### Hardening checklist

- [ ] Config directory ACL restricts access to the current Windows user.
- [ ] API token is scoped to `mcp-api@pve`, not `root@pam`.
- [ ] SSH key is dedicated to this service and has no passphrase only because OpenCode launches it unattended.
- [ ] `pve-host` is unprivileged and allowlisted.
- [ ] `pve` LXC policy is `audit_only`; accept that this is a root shell inside containers.
- [ ] Optional: set `command_policy.require_approval_token=true` on `pve` if every LXC exec should require a manual token. Do not store that token in `AGENTS.md` if it is meant as a gate.
- [ ] Optional: use `mcp.tool_allowlist` to reduce the tool catalog. Exact names include:
  `get_nodes`, `get_node_status`, `get_containers`, `get_container_config`, `get_container_ip`,
  `get_vms`, `get_vm_config`, `get_vm_ip_addresses`, `get_storage`, `get_cluster_status`,
  `execute_vm_command`, `execute_container_command`, `execute_node_command`,
  `start_container`, `stop_container`, `restart_container`, `create_container`, `delete_container`,
  `start_vm`, `stop_vm`, `shutdown_vm`, `reset_vm`, `create_vm`, `delete_vm`,
  `create_snapshot`, `list_snapshots`, `rollback_snapshot`, `delete_snapshot`,
  `create_backup`, `list_backups`, `restore_backup`, `delete_backup`,
  `list_isos`, `list_templates`, `download_iso`, `delete_iso`,
  `list_jobs`, `get_job`, `poll_job`, `cancel_job`, `retry_job`,
  `get_node_syslog`, `get_task_log`, `get_cluster_log`, `list_targets`, `list_bridges`.
  Unknown names fail startup; start with the full catalog and trim later.
- [ ] Optional: trust the PVE CA and set `verify_ssl=true` instead of `allow_insecure_tls`. This requires the cert to match the host/IP used; if it does not, keep the current LAN-only exception.

### Acceptance criteria

- `opencode mcp list` shows the `proxmox` server connected.
- `proxmox_get_nodes` (target `pve`) returns node `pve` online.
- `proxmox_get_containers` (target `pve`) returns CT 100-105.
- `proxmox_execute_container_command` with `selector="100"`, `command="/usr/local/bin/pihole -v"` returns success and the expected versions.
- `proxmox_execute_node_command` with target `pve-host`, node `pve`, command `uptime` returns success.
- `proxmox_execute_node_command` with command `whoami` is blocked by policy.
- Snapshot create/list/delete works on CT 100.
- No token, key, or password is committed to the repository.
- The Pi-hole web UI task is optional and only considered done after it prompts for a password.

### Validation performed (2026-11-12)

The safe-scope setup was validated against a single-node PVE 9.1.1 lab:

- `opencode mcp list` reported `proxmox connected`; 68 tools loaded.
- Both targets resolved; the node reported online; all six example LXC guests were listed.
- LXC command execution returned the expected service version; a deny-pattern command was blocked.
- Host `uptime` succeeded; `whoami` was blocked by the allowlist.
- Snapshot create/list/delete succeeded; a first delete raced the CT lock, and `retry_job` completed after the create job finished.
- A test backup was created and listed.
- Docker was discovered inside a guest via the Docker CLI.
- Gotchas: `pct exec` can have an empty `PATH` (use absolute paths); poll snapshot jobs before deleting.

### Rollback

1. Remove the `proxmox` entry from `$HOME\.config\opencode\opencode.json` and restart OpenCode.
2. Remove local secrets and state:

```powershell
Remove-Item -Recurse -Force "$HOME\.config\proxmox-mcp"
Remove-Item "$HOME\.ssh\proxmox_mcp", "$HOME\.ssh\proxmox_mcp.pub" -ErrorAction SilentlyContinue
```

3. On the PVE console, remove the API token, ACL, user, sudo rule, and SSH user:

```bash
pveum user token remove mcp-api@pve mcp-token
pveum acl delete / --users mcp-api@pve
pveum user delete mcp-api@pve
rm -f /etc/sudoers.d/mcp-agent
userdel -r mcp-agent
```

If `pveum acl delete` complains, delete each role assignment separately:

```bash
pveum acl delete / --users mcp-api@pve --roles PVEVMAdmin
pveum acl delete / --users mcp-api@pve --roles PVEDatastoreAdmin
pveum acl delete / --users mcp-api@pve --roles PVEAuditor
```

4. Optionally remove the PVE host key from `known_hosts` with `ssh-keygen -R pve.example.com`.

---

## Open questions for your environment

1. **API scope:** Is `PVEVMAdmin` + `PVEDatastoreAdmin` + `PVEAuditor` sufficient for every planned tool, or should the plan fall back to a `root@pam` token?
2. **Host command depth:** Is unprivileged host diagnostics enough, or do you want root-level host administration later? Root would require a separate SSH identity or an explicit sudoers decision.
3. **LXC policy:** Is `audit_only` acceptable for the LXC shell, or do you want a strict allowlist of commands?
4. **Pi-hole:** Should securing the web UI be part of the acceptance run, or a separate follow-up?
5. **100% scope:** Do you want the safe plan (partial native coverage; use the PVE UI/SSH for gaps) or the full-control variant (add `pve-root`, accept root-equivalent access, still no console/TTY/file transfer)?
