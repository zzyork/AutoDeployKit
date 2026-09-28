# AutoDeployKit

一个面向多台 Linux 服务器的自动化运维与部署工具，基于 SSH 批量连接目标主机，提供服务器初始化、软件部署、监控安装和巡检报告能力。

> CLI 适用于 CentOS 7/8/9、Rocky Linux、OpenEuler 等基于 RPM 的发行版；WebUI 第一版要求客户机预装 Python 3.14 和 systemd。

WebUI 第一版的范围和安全边界见 [实施计划](docs/plans/2026-09-28-webui-v1-implementation.md)；早期架构草案仅作历史参考。

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
- Redis 管理
- RabbitMQ 安装（Erlang 官方 RPM + RabbitMQ 通用二进制包；默认 RabbitMQ `4.2.0` / Erlang `27.3.4.11`）

> 安装前检查系统、架构及已有安装。CentOS/RHEL 7/8/9、Rocky Linux、AlmaLinux、Oracle Linux 根据主版本选择 el7/el8/el9 RPM；openEuler 22.03 固定使用 el8 RPM，不升级 OpenSSL。当前已核验的安装包仅支持 `x86_64`。已有可用 Erlang 27.x 会复用，其他版本不会自动替换。

> 通过 `dnf` / `yum` 安装 `socat`、`ncurses-compat-libs`、`wget`、`xz`；安装包保存到 `/usr/local/src`，RabbitMQ 安装到 `/usr/local/rabbitmq_server4.2`，环境变量写入 `/etc/profile.d/rabbitmq.sh`。不添加 RabbitMQ 软件源。优先上传 `packages/` 中的同名安装包，否则从 GitHub 下载，失败后复用现有本地下载上传流程；所有安装包均按官方发布资产的 SHA256 校验。团队软件库的包也可按原文件名放入 `packages/`，但必须与官方包一致。

> 管理插件、systemd 服务、启动及开机自启、admin 管理员均需分别确认，默认跳过。systemd 按参考文档使用 root 运行；密码交互输入，要求至少 12 位并包含大小写字母、数字和特殊符号，只向服务器传输加盐 SHA256 哈希。不覆盖已有安装目录、PATH 文件或服务，不修改已有 admin，不关闭防火墙，不放开 guest 的远程访问。

> RabbitMQ 4.2.0 不兼容 Erlang 25.3.2，因此未沿用文档中的 Erlang 版本。RabbitMQ 4.2 社区支持已于 2026-07-31 结束，CentOS 7 也已结束支持；本流程固定版本并提示风险，不自动切换为最新版本。参考：[通用二进制安装](https://www.rabbitmq.com/docs/install-generic-unix)、[Erlang 兼容矩阵](https://www.rabbitmq.com/docs/which-erlang)、[支持时间表](https://www.rabbitmq.com/release-information)、[Erlang 27.3.4.11 RPM](https://github.com/rabbitmq/erlang-rpm/releases/tag/v27.3.4.11)。

> RabbitMQ 的升级、备份和回滚尚未接入 CLI。

### 3. 软件管理 `software_ops`

- Docker 管理
- Minio 管理
- Supervisor 管理
- JDK 管理

### 4. 监控管理 `monitor_ops`

- Prometheus 安装
- mysqld_exporter 安装
- node_exporter 安装
- redis_exporter 安装

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
├─ pyproject.toml              # Python 项目与依赖配置
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
│  ├─ redis_manager.py
│  └─ rabbitmq_manager.py      # CLI 仅接入安装入口
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
   ├─ software_check.py
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

安装项目与依赖：

```bash
pip install -e .
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

### WebUI 第一版

WebUI 只使用自身数据库中的资产，**不读取或导入** CLI 的 `hosts`。管理员在页面登记主机、登录账号及密钥或密码；生成的 SSH 公钥需自行配置到服务器。首版只开放只读巡检和历史报告，不提供任意命令或服务修改。CLI 的主机来源和报告目录选择保持不变。

Linux 交付包由构建环境生成的 wheel 与 `scripts/install_webui.sh` 组成，目标机不需要源码仓库。管理员在目标机本机终端执行（脚本会创建专用服务账号、安装目录与独立虚拟环境，交互设置管理员口令后启动服务）：

```bash
sudo bash install_webui.sh /absolute/path/autodeploykit-0.1.0-py3-none-any.whl
```

脚本默认将程序放在 `/opt/autodeploykit`，数据和报告放在 `/var/lib/autodeploykit`，加密根密钥放在 `/etc/autodeploykit/master.key`；可在安装前设置 `WEBUI_INSTALL_DIR`、`WEBUI_DATA_DIR`、`WEBUI_CONFIG_DIR` 为互不重叠的绝对目录。服务只监听 `127.0.0.1:8765`，须由管理员另行配置同机反向代理的 HTTPS 与内网访问限制。数据库与根密钥必须分别备份；任一丢失时不要重建密钥覆盖旧数据库。客户机管理员有权限读取已安装的 Python 代码，文件权限只限制普通用户。

本地开发时，使用 Python 3.14 的独立虚拟环境安装 `.[web]`；在**仓库外**准备数据目录和根密钥目录，以本机终端运行初始化入口后再启动服务：

```bash
autodeploykit-webui-init --data-dir /absolute/data/path --key-file /another/absolute/path/master.key
WEBUI_DATA_DIR=/absolute/data/path WEBUI_KEY_FILE=/another/absolute/path/master.key python -m uvicorn webui.app:create_app --factory --host 127.0.0.1 --port 8765 --workers 1
```

WebUI 报告只写入数据目录下的 `reports/`。目标与跳板机沿用现有 Paramiko 主机密钥自动接受行为，首次连接无法验证服务器身份；正式部署前需评估中间人风险并限制为受控网络。未经确认不要将服务暴露到公网。

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

执行 `server_check` 时，程序会提示选择或输入报告目录，也可通过 `SERVER_CHECK_REPORT_DIR` 指定。

- 默认目录：`server_check/reporters`
- 输出形式：按 `组名 / 月份 / 主机报告.md` 归档

并发数量由环境变量 `MAX_WORKERS` 控制；未设置时默认最多 5 个并发。

## 软件启动检测工具

`utils.software_check.check_software_started` 接收已有 SSH 连接，仅执行查看类命令，不负责安装、启动或重启软件。调用方应沿用从 `hosts` 读取配置并通过 `utils.ssh_utils` 建立连接的流程。

```python
from utils.software_check import check_software_started

result = check_software_started(
    client,
    service_name="nginx",
    process_name="nginx",
    retries=3,
    interval=2,
)
started = result["success"]
details = result["checks"]
warnings = result["warnings"]
```

- 至少指定 `service_name` 或 `process_name`；指定的运行状态检查必须全部通过。服务名省略 `.service` 时自动补齐；systemd 检查要求服务为 `loaded/active/running`，并通过 `ps` 验证 `MainPID` 仍存活；进程名为 `ps -C` 使用的可执行文件名，不是命令行片段，僵尸、已停止或暂停的进程不算运行。
- 默认读取服务当前启动批次的 journal；无法取得 `InvocationID` 时读取最近 5 分钟日志。可用 `log_path="/var/log/example/app.log"` 改为读取指定文件末尾 `log_lines` 行（默认 100 行，可能包含历史启动记录）。
- 日志默认只提供诊断；设置 `success_pattern=r"ready for connections"` 后，还必须在日志中匹配该正则（忽略大小写）。错误关键字记录在 `checks["logs"]["error_matches"]` 和 `warnings` 中，不直接判定启动失败；读取日志失败且指定了成功关键字时，检测不通过。
- 返回整体 `success`、实际 `attempts`、各项 `checks` 和 `warnings`；检查项保留命令、标准输出、错误输出、退出码和通过状态。`retries` 为总尝试次数，`interval` 为尝试间隔，不是 SSH 超时；该工具验证运行状态，不代表业务接口已经就绪。

---

## 注意事项

- 涉及磁盘分区、格式化、挂载的操作具有破坏性，请务必确认目标磁盘
- 若目标机器无法直接联网，可先将安装包放入 `packages/` 目录供上传使用
- 多主机执行时，连接失败的主机会跳过，不影响其他主机继续执行
- 跳板机场景请正确填写 `proxy*` 参数

---

## 许可证

本项目使用 MIT License，详见 `LICENSE`。
