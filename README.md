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

## WebUI 容器使用

WebUI 需要 Docker Engine、独立命令 `docker-compose` v2 及可访问 Python 包索引的构建环境；仅有 `docker compose` 插件时请将下方命令相应替换。镜像标签为 `autodeploykit-webui:local`。

在部署主机的交互终端、仓库目录下首次初始化并启动：

```bash
docker-compose -f compose.webui.yaml build webui
docker-compose -f compose.webui.yaml --profile setup run --rm --no-deps init
docker-compose -f compose.webui.yaml up -d --no-deps webui
```

初始化时随机创建 `admin` 账号，初始口令只在终端显示一次，不会以明文写入磁盘。请立即妥善保存并登录后修改；不能从容器日志找回。普通账号由管理员在设置页创建，能查看共享资产和报告并发起只读巡检，不能修改资产、SSH 凭据或模型配置。资产、SSH 公钥、会话、任务和报告对所有已登录账号共享，聊天内容不提供个人隔离。WebUI 只监听主机 `127.0.0.1:8765`，对外访问须经 HTTPS 反向代理并限制访问来源。反向代理必须透传原始 Host（例如 Nginx 的 `proxy_set_header Host $http_host;`），否则来源校验会拒绝登录；Compose 默认要求 HTTPS Cookie，本机直接通过 HTTP 登录时需在自有部署配置中取消 `WEBUI_SECURE_COOKIES=1`。

已有管理员数据不会重新生成口令；旧版单管理员数据库可用原管理员口令登录，首次登录后自动迁移账号。升级前先安排停止旧实例的写入并分别备份数据库/报告卷和根密钥卷；升级时不要在旧服务运行期间执行 `init`，直接构建并替换 WebUI 服务，由新容器迁移会话表。不要在丢失根密钥后重新初始化。当前 `scripts/install_webui.sh` 尚未接入完整部署流程，不要用它代替以上命令。

## 许可证

本项目使用 MIT License，详见 `LICENSE`。
