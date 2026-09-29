# AutoDeployKit

一个面向多台 Linux 服务器的自动化运维与部署工具，提供 CLI 和 WebUI，支持服务器初始化、软件部署、监控安装和巡检报告。

CLI 面向 CentOS 7/8/9、Rocky Linux、openEuler 等基于 RPM 的发行版；具体软件的支持范围以安装提示为准。WebUI 用于主机资产管理、只读巡检和历史报告查看。

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
- RabbitMQ 安装（RabbitMQ `4.2.0` / Erlang `27.3.4.11`，仅支持 `x86_64`）

RabbitMQ 的升级、备份和回滚尚未接入 CLI。

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

### 6. WebUI

- 管理主机资产及 SSH 登录凭据
- 执行只读服务器巡检
- 查看历史巡检报告
- 容器安装与升级

## CLI 安装

- Python 3.9+
- 可通过 SSH 访问目标主机
- 目标主机具备 root 或 sudo 权限
- 目标系统建议为 RHEL 系发行版

安装项目与依赖：

```bash
pip install -e .
```

## CLI 主机清单

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

## CLI 使用

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

### 巡检报告

执行 `server_check` 时，程序会提示选择或输入报告目录，也可通过 `SERVER_CHECK_REPORT_DIR` 指定。

- 默认目录：`server_check/reporters`
- 输出形式：按 `组名 / 月份 / 主机报告.md` 归档

并发数量由环境变量 `MAX_WORKERS` 控制；未设置时默认最多 5 个并发。

## WebUI 安装与使用

### 容器部署环境要求

- Linux 主机、Docker Engine 和 Docker Compose 插件（`docker compose`）；脚本检测到缺失时会询问是否从本机已配置的 APT/DNF 仓库安装并启动 Docker，拒绝则退出
- 安装 Docker 需要 root 或 sudo；运行脚本的账号还需有权访问本机 Docker 守护进程（Unix socket）。不支持的软件仓库或缺包时请先手动配置可信来源
- 构建镜像时能访问 Python 包索引；主机不需要安装 Python 或 systemd 服务

### 安装与升级

将完整仓库放到部署主机，在交互终端安装：

```bash
bash scripts/install_webui.sh install
```

首次安装时脚本通过初始化容器在终端设置管理员口令；已有数据请使用 `upgrade`，不会重置口令。升级时先备份两个卷、获取新代码，保持原部署目录或 `COMPOSE_PROJECT_NAME` 不变，再运行 `bash scripts/install_webui.sh upgrade`。脚本自动构建镜像、校验数据、初始化并启动服务；不自动停用旧 systemd 服务，也不删除数据。镜像内使用 Python 3.14，服务始终为单 worker。`docker compose -f compose.webui.yaml ps` 可查看状态，`curl -fsS http://127.0.0.1:8765/` 可检查首页。

部署位置：

| 内容 | 容器内路径 / 主机端口 |
| --- | --- |
| 程序 | 镜像内 Python 包；`/opt/autodeploykit` 为只读工作目录及规则文件 |
| 数据卷 `webui_data` | `/var/lib/autodeploykit`（数据库与 `reports/`） |
| 密钥卷 `webui_key` | `/etc/autodeploykit/master.key`（运行时只读） |
| 访问地址 | 主机 `127.0.0.1:8765` |

两个命名卷的实际名称带有 Compose 项目前缀，请用 `docker compose -f compose.webui.yaml config` 核对。备份数据库及报告时需确保没有写入，同时单独备份根密钥卷；恢复时同时恢复两者，不要在丢失密钥时重新安装。迁移原 systemd 部署时，管理员须先备份、停用旧服务并移除旧服务单元（保留数据和根密钥），将原数据目录与根密钥分别迁入对应卷后再运行 `upgrade`；不要让旧服务与容器同时写同一数据库。脚本不自动停用旧服务或删除旧文件、卷。

通过同机反向代理配置 HTTPS 和内网访问限制后，登录 WebUI，登记主机及 SSH 登录凭据，再执行巡检或查看历史报告。容器须能访问目标 SSH 主机及模型 API；配置模型地址时，容器内的 `localhost` 指向容器自身。不要挂载 Docker socket 或把服务端口公开到公网。WebUI 不读取或导入 CLI 的 `hosts`；使用页面生成的 SSH 公钥时，需自行将公钥配置到目标服务器。当前不提供任意命令执行或服务修改。

### 本地启动

在 Python 3.14 的独立虚拟环境中安装 WebUI 依赖：

```bash
pip install -e ".[web]"
```

在仓库外准备数据目录和根密钥目录，然后在本机终端初始化并启动：

```bash
autodeploykit-webui-init --data-dir /absolute/data/path --key-file /another/absolute/path/master.key
WEBUI_DATA_DIR=/absolute/data/path WEBUI_KEY_FILE=/another/absolute/path/master.key python -m uvicorn webui.app:create_app --factory --host 127.0.0.1 --port 8765 --workers 1
```

浏览器访问 `http://127.0.0.1:8765`。

## 注意事项

- 涉及磁盘分区、格式化、挂载的操作具有破坏性，请务必确认目标磁盘。
- 若目标机器无法直接联网，可先将安装包放入 `packages/` 目录供上传使用；RabbitMQ 安装包须使用官方原文件名及内容。
- 跳板机场景请正确填写 `proxy*` 参数。
- RabbitMQ 4.2 和 CentOS 7 已结束社区支持，使用前请评估安全与维护风险。
- WebUI 数据库与根密钥必须分别备份；任一丢失时，不要创建新密钥覆盖旧密钥。
- WebUI 镜像构建会下载 Python 依赖；请从可信来源构建镜像并审查依赖。
- SSH 首次连接不会验证主机身份，存在中间人风险；请限制在受控网络使用，不要直接将 WebUI 暴露到公网。

## 许可证

本项目使用 MIT License，详见 `LICENSE`。
