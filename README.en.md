# AutoDeployKit

An automation toolkit for operating and deploying across multiple Linux servers via SSH. It streamlines common tasks such as server initialization, software install/upgrade, monitoring setup, and server inspection. Features are organized by modules and executed in batch via `cli.py` by specifying a module and a host group.

---

## Features

- Server initialization
  - Set hostname
  - Manage Yum repositories and packages
  - Manage firewalld and SELinux
  - Kernel parameters and system optimization
  - Bare disk partitioning, LVM creation, and mounting to a target directory
  - OpenSSL security upgrade
- Software management
  - Nginx: build from source, upgrade, and manage via systemd
  - Docker: install static binaries and manage via systemd
- Monitoring setup
  - mysqld_exporter install and credential injection
  - Prometheus install and systemd setup
- Server inspection
  - Collect system info, resource usage, service status, network/ports, and error logs
  - Export reports to Markdown with per-group and monthly archival
- SSH batch execution
  - Password and key-based authentication
  - Bastion/Jump host support
  - Live streaming of remote command output

---

## Directory Structure

```
.
├─ cli.py                   # CLI entry: select module and load host group
├─ requirements.txt         # Dependencies
├─ config/                  # systemd and service template files
├─ scripts/                 # Helper scripts
├─ server_ops/              # Server initialization operations
│  ├─ main.py               # Menu entry
│  ├─ hostname_ops.py       # Hostname management
│  ├─ dnf_repos_ops.py      # Yum repositories
│  ├─ pkg_ops.py            # Packages
│  ├─ firewall_selinux_ops.py# firewalld / SELinux
│  ├─ kernel_optimize_ops.py# Kernel tuning
│  ├─ disk_partition_ops.py # Bare disk + LVM + mount
│  ├─ system_optimize_ops.py# System optimization
│  └─ openssl_upgrade.py    # OpenSSL upgrade
├─ middleware_ops/            # Middleware management (Nginx, MySQL)
│  ├─ main.py
│  ├─ nginx_manager.py
│  └─ docker_manager.py
├─ monitor_ops/             # Monitoring setup (mysqld_exporter, Prometheus)
│  ├─ main.py
│  ├─ mysql_monitor.py
│  └─ prometheus_monitor.py
├─ server_check/            # Server inspection and report generation
│  └─ main.py
├─ server_check_reports/    # Output directory for inspection reports
└─ utils/                   # Utilities
   ├─ ssh_utils.py          # SSH connection & commands (with proxy support)
   ├─ file_utils.py         # Download/upload, template render, GitHub version fetch, MD5 utilities
   ├─ output.py             # Colored console and local logfile
   └─ server_utils.py       # Server helper utilities
```

---

## Requirements

- Python 3.9+ (recommended)
- Internet access (for downloading artifacts and GitHub API)
- Target servers
  - Linux (CentOS/Rocky/Alma or other RHEL-like distros)
  - sudo/root privileges
  - Reachable via SSH; provide bastion settings if needed

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Hosts Inventory (hosts)

`cli.py` reads a `hosts` file (INI-like format) from the current working directory. Example:

```
[webservers]
192.168.1.10 user=root password=passw0rd port=22
192.168.1.11 user=ec2-user keyfile="~/.ssh/id_rsa" port=22

[dbservers]
10.0.0.5 user=root keyfile="/path/to/key" proxy=10.0.0.2 proxy_user=jump proxy_password=*** proxy_port=22
```

Supported fields:
- user, port, password, keyfile (maps to internal `key_file`)
- vip (virtual IP for connection, if present)
- proxy, proxy_user, proxy_password, proxy_keyfile, proxy_port

---

## Usage

General invocation:

```bash
python cli.py <module_name> <group>
```

- `<module_name>` options:
  - `server_ops` Server initialization
  - `middleware_ops` Software management (Nginx, Docker)
  - `monitor_ops` Monitoring setup (mysqld_exporter, Prometheus)
  - `server_check` Server inspection (Markdown report)
- `<group>`: group name from the hosts file, e.g., `webservers`

Examples:

```bash
# Server initialization (interactive menu)
python cli.py server_ops webservers

# Software management (Nginx, Docker)
python cli.py middleware_ops webservers

# Monitoring setup (mysqld_exporter, Prometheus)
python cli.py monitor_ops dbservers

# Server inspection (reports to server_check_reports/<group>/<YYYYMM>/)
python cli.py server_check webservers
```

---

## Module Overview

- server_ops
  - Hostname, Yum repos, packages, firewalld & SELinux, kernel & system tuning
  - Disk partitioning & mounting: detect bare disks, create GPT + LVM, format XFS, mount to `/data`
  - OpenSSL upgrade for security hardening
- middleware_ops
  - Nginx: fetch stable version, build from source, template `nginx.conf`, systemd service
  - Docker: install official static binaries, systemd service
- monitor_ops
  - mysqld_exporter: fetch latest from GitHub, upload and install, interactive DB credentials, systemd service
  - Prometheus: fetch latest from GitHub, upload and install, create data dir, systemd service
- server_check
  - Collect OS info, resource metrics, service status, networking/ports, and error logs to Markdown

---

## Notes & Best Practices

- Run commands with root or sudo privileges; some tasks require elevated permissions
- Disk partitioning/LVM will alter disk data; verify selected disk and confirm prompts
- For offline environments, pre-download artifacts into `packages/` for upload
- Bastion: provide `proxy` parameters to connect through a jump host
- For multiple hosts, operations run sequentially; failures on one host do not block others

---

## Contributing

- Issues and PRs are welcome
- Keep the modular and interactive design style

---

## License

MIT License. See `LICENSE` for details.
