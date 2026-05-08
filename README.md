# AutoDeployKit

一个面向多台 Linux 服务器的自动化运维与部署工具，基于 SSH 批量连接目标主机，提供服务器初始化、软件部署、监控安装、巡检报告以及 Agent 辅助诊断能力。

> 当前仓库以交互式命令行为主，适用于 CentOS 7/8/9、Rocky Linux、OpenEuler 等基于 RPM 的发行版。

---

## 当前可用模块

本项目当前通过 `cli.py` 可直接调用的模块如下：

- `server_ops`：服务器初始化
- `middleware_ops`：中间件管理
- `software_ops`：软件管理
- `monitor_ops`：监控管理
- `server_check`：服务器巡检
- `agent_ops`：交互式 Agent 诊断

另外还提供：

- `agent_cli.py`：直接用自然语言发起诊断

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

### 6. Agent 诊断 `agent_ops` / `agent_cli.py`

- 支持自然语言问题输入
- 自动识别常见问题类型
- 自动采集服务状态、日志、磁盘、内存、端口等证据
- 输出诊断结论与建议动作
- 对低风险修复动作先确认、再执行验证

---

## 项目结构

```text
.
├─ cli.py                      # 主 CLI 入口
├─ agent_cli.py                # Agent 诊断入口
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
├─ agent/                      # Agent 诊断核心逻辑
│  ├─ planner.py               # 问题意图识别
│  ├─ runner.py                # 诊断编排与修复执行
│  └─ tools.py                 # 证据采集与修复工具
├─ agent_ops/
│  └─ main.py                  # 交互式 Agent 菜单入口
├─ server_ops/
│  ├─ main.py
│  ├─ hostname_ops.py
│  ├─ pkg_ops.py
│  ├─ firewall_ops.py
│  ├─ kernel_optimize_ops.py
│  ├─ disk_partition_ops.py
│  ├─ system_optimize_ops.py
│  ├─ openssl_upgrade.py
│  └─ openssh_upgrade.py       # 目前未在菜单中启用
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
python cli.py agent_ops webservers
```

### 2. Agent 自然语言诊断

```bash
python agent_cli.py webservers "nginx 502，帮我定位一下"
python agent_cli.py 192.168.1.10 "mysql 服务起不来，帮我看下"
```

---

## Agent 当前支持的诊断方向

当前已内置的主要识别类型：

- `nginx 502`
- 服务异常
- 磁盘空间不足
- CPU / 负载过高
- SSH 登录或连接异常
- 通用健康检查

典型采集内容包括：

- `systemctl is-active/status`
- `journalctl -u <service>`
- `tail /var/log/nginx/error.log`
- `df -hT`
- `free -m`
- `ss -lntp`
- `journalctl -p err..alert`

当前自动修复能力只覆盖低风险场景，例如：

- 服务不在 `active` 状态时，询问是否执行重启

高风险操作默认不会自动执行。

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
