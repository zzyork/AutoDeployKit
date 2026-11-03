# AutoDeployKit

An automation toolkit for operating multiple Linux servers over SSH. It provides interactive workflows for server initialization, software deployment, monitoring setup, and inspection report generation.

> The current repository is primarily designed for interactive CLI usage and is intended for RPM-based distributions such as CentOS 7/8/9, Rocky Linux, and OpenEuler.

---

## Currently Available Modules

The following modules can be invoked directly through `cli.py`:

- `server_ops`: server initialization
- `middleware_ops`: middleware management
- `software_ops`: software management
- `monitor_ops`: monitoring management
- `server_check`: server inspection

---

## Feature Overview

### 1. Server Initialization `server_ops`

- Set hostname
- Manage packages
- Configure firewalld / SELinux
- Tune kernel parameters
- Partition and mount disks
- Apply system optimization
- Manage OpenSSL

### 2. Middleware Management `middleware_ops`

Currently wired into the menu:

- Nginx management
- MySQL management
- Redis management

> Although `rabbitmq_manager.py` exists in the repository, it is not registered in `middleware_ops/main.py`, so it is not currently available from the CLI menu.

### 3. Software Management `software_ops`

- Docker management
- Minio management
- Supervisor management
- JDK management

### 4. Monitoring Management `monitor_ops`

- Prometheus installation
- mysqld_exporter installation
- node_exporter installation
- redis_exporter installation

### 5. Server Inspection `server_check`

- Collect basic system information
- Collect resource usage
- Check security settings
- Check service and process status
- Check network and listening ports
- Summarize recent error logs
- Export Markdown inspection reports

## Project Structure

```text
.
├─ cli.py                      # Main CLI entry
├─ hosts.example               # Example hosts inventory
├─ pyproject.toml              # Python project and dependency config
├─ config/                     # Templates and config files
│  ├─ docker/
│  ├─ linux/
│  ├─ minio/
│  ├─ mysql/
│  ├─ nginx/
│  ├─ prometheus/
│  └─ supervisor/
├─ packages/                   # Local package cache
├─ server_ops/
│  ├─ main.py
│  ├─ hostname_ops.py
│  ├─ pkg_ops.py
│  ├─ firewall_ops.py
│  ├─ kernel_optimize_ops.py
│  ├─ disk_partition_ops.py
│  ├─ system_optimize_ops.py
│  └─ openssl_upgrade.py
├─ middleware_ops/
│  ├─ main.py
│  ├─ nginx_manager.py
│  ├─ mysql_manager.py
│  ├─ redis_manager.py
│  └─ rabbitmq_manager.py      # Present but not enabled in menu
├─ software_ops/
│  ├─ main.py
│  ├─ docker_manager.py
│  ├─ jdk_manager.py
│  ├─ minio_manager.py
│  └─ supervisor_manager.py
├─ monitor_ops/
│  ├─ main.py
│  ├─ prometheus_monitor.py
│  ├─ mysql_exporter.py
│  ├─ node_exporter.py
│  └─ redis_exporter.py
├─ server_check/
│  └─ main.py
├─ scripts/
│  └─ get-pip.py
└─ utils/
   ├─ ssh_utils.py
   ├─ file_utils.py
   ├─ output.py
   ├─ menu_runner.py
   ├─ choice.py
   └─ server_utils.py
```

---

## Requirements

- Python 3.9+
- SSH access to target hosts
- root or sudo privileges on target hosts
- RHEL-family distributions are recommended

Install the project and dependencies:

```bash
pip install -e .
```

---

## Skills Required for AI Agent Maintenance

When maintaining this repository with an AI Agent that supports Skills, enable at least the following Skills:

### Required Skills

- `Code`: for code changes, task planning, implementation, and verification workflows.
- `brainstorming`: for requirement clarification and design evaluation before adding features, changing behavior, or making design decisions.
- `git-essentials`: for inspecting changes, commit history, branch state, and following a safe Git workflow.

### Optional Skills

- `security-auditor`: enable when working on SSH, permissions, keys, command execution, input validation, or high-risk operations.
- `architecture-designer`: enable for module boundaries, workflow refactoring, plugin design, or batch operations architecture changes.
- `writing-plans` / `executing-plans`: enable when a clear specification exists or a larger change needs to be implemented in stages.

The Agent should also follow the project rules in `CLAUDE.md`: read the project instructions first; load `.venv` only when invoking repository modules or workflows; read target SSH configuration from `hosts` before any remote operation; and apply the command policy for read-only, modify/restart, and move/delete/stop/shutdown operations.

---

## Hosts Inventory

The program reads a `hosts` file from the current directory. See `hosts.example` for the expected format.

Example:

```ini
[webservers]
192.0.2.10 user=root port=22 password="example-password" proxy="" hostname="web-01" lan_ip="10.0.0.10" vip="" remark="Example Web host"
192.0.2.11 user=admin port=22 keyfile="/path/to/private_key" proxy="" hostname="web-02" lan_ip="10.0.0.11" vip="192.0.2.100" remark="Key authentication"

[dbservers]
10.0.0.5 user=root port=22 keyfile="/path/to/db_key" proxy="192.0.2.2" proxy_user=jump proxy_port=22 proxy_keyfile="/path/to/jump_key" hostname="db-01" lan_ip="10.0.0.5" vip="" remark="Via jump host"
```

Recommended field order (parsing is order-independent):

| Item | Field | Required | Meaning |
| --- | --- | --- | --- |
| Address | First item on the line | Yes | Host IP or domain, used for matching |
| Username | `user` | Yes | SSH login user |
| Port | `port` | Yes | Explicit integer from 1 to 65535 |
| Password / SSH key | `password` / `keyfile` | At least one | Nonempty authentication; key takes precedence when both are provided |
| Jump host | `proxy` | No | Use with `proxy_user`, `proxy_port`, and `proxy_password` / `proxy_keyfile` |
| Hostname | `hostname` | No | Inventory metadata; does not change the remote hostname |
| LAN IP | `lan_ip` | No | Inventory metadata; does not select the SSH destination |
| Virtual IP (VIP) | `vip` | No | Preserves existing behavior: used as the SSH destination when nonempty |
| Notes | `remark` | No | Inventory metadata; not used for matching or operations |

Optional fields may be omitted or set to `""`. Invalid selected entries (missing required fields, invalid ports, or malformed parameters) abort loading before any connection. Existing entries remain valid if they satisfy these requirements.

Quote values containing spaces and escape embedded double quotes as `\"`, for example `remark="Example \"Web\" host"`. Use double quotes for Windows key paths, for example `keyfile="C:\Users\example\.ssh\id_ed25519"`.

---

## Usage

### 1. General CLI

```bash
python cli.py <module_name> <host_pattern>
```

`<host_pattern>` supports:

- a host group, for example `webservers`
- a single IP, for example `192.168.1.10`
- multiple IPs, for example `192.168.1.10,192.168.1.11`
- all hosts: `all`

Examples:

```bash
python cli.py server_ops webservers
python cli.py middleware_ops webservers
python cli.py software_ops webservers
python cli.py monitor_ops dbservers
python cli.py server_check webservers
```

---

## Inspection Report Notes

When running `server_check`, the program prompts for a report output directory. You can also set `SERVER_CHECK_REPORT_DIR`.

- Default directory: `server_check/reporters`
- Output layout: `group / month / host_report.md`

Concurrency is controlled by the `MAX_WORKERS` environment variable. If unset, it defaults to at most 5 workers.

---

## Notes

- Disk partitioning, formatting, and mounting are destructive operations; verify the target disk carefully
- If target machines cannot access the internet directly, place installation packages in `packages/` for upload fallback
- During multi-host execution, failed connections are skipped and do not block other hosts
- For bastion/jump host scenarios, make sure `proxy*` parameters are configured correctly

---

## License

This project is licensed under the MIT License. See `LICENSE` for details.
