# AutoDeployKit

An automation toolkit for operating multiple Linux servers over SSH. It provides interactive workflows for server initialization, software deployment, monitoring setup, inspection report generation, and Agent-assisted diagnosis.

> The current repository is primarily designed for interactive CLI usage and is intended for RPM-based distributions such as CentOS 7/8/9, Rocky Linux, and OpenEuler.

---

## Currently Available Modules

The following modules can be invoked directly through `cli.py`:

- `server_ops`: server initialization
- `middleware_ops`: middleware management
- `software_ops`: software management
- `monitor_ops`: monitoring management
- `server_check`: server inspection
- `agent_ops`: interactive Agent diagnosis

Additionally provided:

- `agent_cli.py`: launch diagnosis directly with natural language

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

> Although `redis_manager.py` and `rabbitmq_manager.py` exist in the repository, they are not registered in `middleware_ops/main.py`, so they are not currently available from the CLI menu.

### 3. Software Management `software_ops`

- Docker management
- Minio management
- Supervisor management

### 4. Monitoring Management `monitor_ops`

- Prometheus installation
- mysqld_exporter installation
- node_exporter installation

### 5. Server Inspection `server_check`

- Collect basic system information
- Collect resource usage
- Check security settings
- Check service and process status
- Check network and listening ports
- Summarize recent error logs
- Export Markdown inspection reports

### 6. Agent Diagnosis `agent_ops` / `agent_cli.py`

- Accept natural language problem descriptions
- Detect common issue types automatically
- Collect evidence such as service status, logs, disk, memory, and ports
- Output diagnosis findings and suggested actions
- Ask for confirmation before low-risk repair actions, then verify results

---

## Project Structure

```text
.
├─ cli.py                      # Main CLI entry
├─ agent_cli.py                # Agent diagnosis entry
├─ hosts.example               # Example hosts inventory
├─ requirements.txt            # Python dependencies
├─ config/                     # Templates and config files
│  ├─ docker/
│  ├─ linux/
│  ├─ minio/
│  ├─ mysql/
│  ├─ nginx/
│  ├─ prometheus/
│  └─ supervisor/
├─ packages/                   # Local package cache
├─ agent/                      # Agent diagnosis core
│  ├─ planner.py               # Intent detection
│  ├─ runner.py                # Diagnosis orchestration and repair flow
│  └─ tools.py                 # Evidence collection and repair tools
├─ agent_ops/
│  └─ main.py                  # Interactive Agent entry
├─ server_ops/
│  ├─ main.py
│  ├─ hostname_ops.py
│  ├─ pkg_ops.py
│  ├─ firewall_ops.py
│  ├─ kernel_optimize_ops.py
│  ├─ disk_partition_ops.py
│  ├─ system_optimize_ops.py
│  ├─ openssl_upgrade.py
│  └─ openssh_upgrade.py       # Present but not enabled in menu
├─ middleware_ops/
│  ├─ main.py
│  ├─ nginx_manager.py
│  ├─ mysql_manager.py
│  ├─ redis_manager.py         # Present but not enabled in menu
│  └─ rabbitmq_manager.py      # Present but not enabled in menu
├─ software_ops/
│  ├─ main.py
│  ├─ docker_manager.py
│  ├─ minio_manager.py
│  └─ supervisor_manager.py
├─ monitor_ops/
│  ├─ main.py
│  ├─ prometheus_monitor.py
│  ├─ mysql_exporter.py
│  └─ node_exporter.py
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

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Hosts Inventory

The program reads a `hosts` file from the current directory. See `hosts.example` for the expected format.

Example:

```ini
[webservers]
192.168.1.10 user=root password=passw0rd port=22
192.168.1.11 user=ec2-user keyfile="~/.ssh/id_rsa" port=22

[dbservers]
10.0.0.5 user=root keyfile="/path/to/key" port=22
10.0.0.6 user=mysql password=mysqlpass port=22 proxy=10.0.0.2 proxy_user=jump proxy_password=jumppass proxy_port=22
```

Supported fields:

- `user`
- `port`
- `password`
- `keyfile`
- `vip`
- `proxy`
- `proxy_user`
- `proxy_password`
- `proxy_keyfile`
- `proxy_port`

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
python cli.py agent_ops webservers
```

### 2. Agent Natural Language Diagnosis

```bash
python agent_cli.py webservers "nginx 502, help me locate the issue"
python agent_cli.py 192.168.1.10 "mysql service won't start, please check"
```

---

## Agent Diagnosis Coverage

Current built-in intent categories include:

- `nginx 502`
- service issues
- disk full / low disk space
- high CPU / load
- SSH login or connection issues
- generic health checks

Typical evidence collection includes:

- `systemctl is-active/status`
- `journalctl -u <service>`
- `tail /var/log/nginx/error.log`
- `df -hT`
- `free -m`
- `ss -lntp`
- `journalctl -p err..alert`

Automatic repair is intentionally limited to low-risk actions, for example:

- asking whether to restart a service when it is not in the `active` state

High-risk changes are not executed automatically by default.

---

## Inspection Report Notes

When running `server_check`, the program prompts for a report output directory.

- Default directory: `server_check/reports`
- Output layout: `group / month / host_report.md`

Concurrency is controlled by the `MAX_WORKERS` environment variable. Set it before running inspection, for example: `MAX_WORKERS=5`.

---

## Notes

- Disk partitioning, formatting, and mounting are destructive operations; verify the target disk carefully
- If target machines cannot access the internet directly, place installation packages in `packages/` for upload fallback
- During multi-host execution, failed connections are skipped and do not block other hosts
- For bastion/jump host scenarios, make sure `proxy*` parameters are configured correctly

---

## License

This project is licensed under the MIT License. See `LICENSE` for details.
