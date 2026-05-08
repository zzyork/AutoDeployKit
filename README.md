# AutoDeployKit

一个面向多台 Linux 服务器的自动化运维与部署工具，基于 SSH 批量连接目标主机，提供服务器初始化、软件部署、监控安装和巡检报告能力。

> 当前仓库以交互式命令行为主，适用于 CentOS 7/8/9、Rocky Linux、OpenEuler 等基于 RPM 的发行版。

---

## 当前可用模块

本项目当前通过 `cli.py` 可直接调用的模块如下：

- `server_ops`：服务器初始化
- `middleware_ops`：中间件管理
- `software_ops`：软件管理
- `monitor_ops`：监控管理
- `server_check`：服务器巡检

---

## 功能概览

### 1. 服务器初始化 `server_ops`

- 设置主机名
- 管理软件包
- 配置 firewalld / SELinux
- 内核参数调优
- 磁盘分区与挂载
- 系统优化
- OpenSSL 管理

### 2. 中间件管理 `middleware_ops`

当前菜单中已接入：

- Nginx 管理
- MySQL 管理

> 仓库中虽然存在 `redis_manager.py`、`rabbitmq_manager.py`，但当前 `middleware_ops/main.py` 未注册这两个入口，因此不属于当前 CLI 可直接使用的模块。

### 3. 软件管理 `software_ops`

- Docker 管理
- Minio 管理
- Supervisor 管理

### 4. 监控管理 `monitor_ops`

- Prometheus 安装
- mysqld_exporter 安装
- node_exporter 安装

### 5. 服务器巡检 `server_check`

- 采集系统基础信息
- 采集资源使用情况
- 检查安全配置
- 检查服务与进程状态
- 检查网络与监听端口
- 汇总近期错误日志
- 输出 Markdown 巡检报告

## 项目结构

```text
.
├─ cli.py                      # 主 CLI 入口
├─ hosts.example               # 主机清单示例
├─ requirements.txt            # Python 依赖
├─ config/                     # 服务模板与配置文件
│  ├─ docker/
│  ├─ linux/
│  ├─ minio/
│  ├─ mysql/
│  ├─ nginx/
│  ├─ prometheus/
│  └─ supervisor/
├─ packages/                   # 本地缓存的软件包
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
│  ├─ redis_manager.py         # 文件存在，但未在菜单中启用
│  └─ rabbitmq_manager.py      # 文件存在，但未在菜单中启用
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

## 环境要求

- Python 3.9+
- 可通过 SSH 访问目标主机
- 目标主机具备 root 或 sudo 权限
- 目标系统建议为 RHEL 系发行版

安装依赖：

```bash
pip install -r requirements.txt
```

---

## 使用 AI Agent 维护本仓库所需 Skills

如果使用支持 Skills 的 AI Agent 辅助维护本仓库，建议至少启用以下 Skills：

### 必需 Skills

- `Code`：用于代码修改、计划拆解、实现与验证流程。
- `brainstorming`：用于新增功能、调整行为或设计方案前的需求澄清与方案评估。
- `git-essentials`：用于查看变更、提交记录、分支状态以及执行规范化 Git 工作流。

### 按需启用 Skills

- `security-auditor`：涉及 SSH、权限、密钥、命令执行、输入校验或高风险运维操作时启用。
- `architecture-designer`：涉及模块边界、流程重构、插件化或批量运维架构调整时启用。
- `writing-plans` / `executing-plans`：有明确规格或需要分阶段实施较大改动时启用。
- `frontend-design` 或 `ui-ux-pro-max`：如果后续新增 Web UI、可视化报告或交互界面时启用。

Agent 使用本仓库时还应遵守 `CLAUDE.md` 中的项目规则：先读取项目指令；只有在调用本仓库模块或流程时才加载 `.venv`；所有远程 SSH 操作必须先从 `hosts` 读取目标主机配置，并按查看、修改/重启、移动/删除/停止/关闭三类命令规则执行。

---

## 主机清单

程序默认从当前目录读取 `hosts` 文件，格式可参考 `hosts.example`。

示例：

```ini
[webservers]
192.168.1.10 user=root password=passw0rd port=22
192.168.1.11 user=ec2-user keyfile="~/.ssh/id_rsa" port=22

[dbservers]
10.0.0.5 user=root keyfile="/path/to/key" port=22
10.0.0.6 user=mysql password=mysqlpass port=22 proxy=10.0.0.2 proxy_user=jump proxy_password=jumppass proxy_port=22
```

支持字段：

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

## 使用方式

### 1. 通用 CLI

```bash
python cli.py <module_name> <host_pattern>
```

`<host_pattern>` 支持：

- 主机组，例如：`webservers`
- 单个 IP，例如：`192.168.1.10`
- 多个 IP，例如：`192.168.1.10,192.168.1.11`
- 所有主机：`all`

示例：

```bash
python cli.py server_ops webservers
python cli.py middleware_ops webservers
python cli.py software_ops webservers
python cli.py monitor_ops dbservers
python cli.py server_check webservers
```

---

## 巡检报告说明

执行 `server_check` 时，程序会提示选择或输入报告目录。

- 默认目录：`server_check/reports`
- 输出形式：按 `组名 / 月份 / 主机报告.md` 归档

并发数量由环境变量 `MAX_WORKERS` 控制，运行巡检前请先设置，例如：`MAX_WORKERS=5`。

---

## 注意事项

- 涉及磁盘分区、格式化、挂载的操作具有破坏性，请务必确认目标磁盘
- 若目标机器无法直接联网，可先将安装包放入 `packages/` 目录供上传使用
- 多主机执行时，连接失败的主机会跳过，不影响其他主机继续执行
- 跳板机场景请正确填写 `proxy*` 参数

---

## 许可证

本项目使用 MIT License，详见 `LICENSE`。
