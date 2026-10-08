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

## WebUI 在线安装

部署主机须为 Linux `x86_64`，具备 root 权限、交互终端、`sha256sum`，可访问发布附件下载地址及公开 GHCR 镜像仓库，且安装目录与 Docker 数据目录各有至少 1 GiB 可用空间。如未安装 `curl`、Docker Engine / Compose v2，脚本会在确认后尝试从 APT/DNF 软件源安装；部署主机不构建镜像。

每次发布时，维护者同步更新 `scripts/install_webui.sh` 顶部的 `WEBUI_VERSION` 和 `pyproject.toml` 的版本；在已登录 GHCR、具备 Docker Engine 的 Linux `x86_64` 发布机运行：

```bash
bash scripts/install_webui.sh --prepare-release
```

命令会构建并推送 `ghcr.io/zzyork/autodeploykit-webui:v<版本>`；确认镜像包为公开可拉取后，将生成的 `dist/v<版本>/compose.webui.yaml` 与 `dist/v<版本>/install_webui.sh` 上传到同名 `v<版本>` GitHub Release。未上传前单脚本在线安装不可用。安装脚本内已固定镜像 digest 和 Compose 文件的 SHA-256，不要直接分发仓库中的模板脚本。

维护者的完整发布、更新和验收命令见 [WebUI 发布与更新](docs/WEBUI_RELEASE.md)。

镜像按 digest 拉取；`Dockerfile.webui` 的基础镜像标签及 `pyproject.toml` 的依赖范围尚未锁定，重建同一源码可能产生不同镜像。正式发布前应固定基础镜像摘要与 Python 依赖版本，并在 Linux Docker 主机完成首次安装、重复运行和升级验证。

服务器只需取得已发布的单个脚本，在交互终端以 root 运行：

```bash
bash install_webui.sh
```

如已将**相同的 Compose 附件**发布到其他 HTTPS 下载源，可在运行前设置 `AUTODEPLOYKIT_WEBUI_DOWNLOAD_BASE_URL`，其值为 `.../releases/download`，脚本会自动拼接 `/v<版本>/compose.webui.yaml`；未设置时使用 GitHub Releases。此设置仅改变 Compose 文件来源，不改变 GHCR 镜像来源；下载或校验失败不会自动切换来源。

安装时只需选择安装目录（默认 `/data/autodeploykit`）和 HTTPS 端口（默认 `8765`）。服务在宿主机 `0.0.0.0:<端口>` 对外监听，不限制来源 IP；脚本为当时所有非回环 IPv4 网卡地址签发自签名证书，并在完成后列出可尝试的访问地址。数据/报告和加密根密钥保存在两个独立 Docker 卷，安装目录保存部署文件及升级备份。首次安装随机生成 `admin` 口令，只在终端显示一次，请立即保存并登录后修改。浏览器访问脚本显示的 `https://<网卡IP>:<端口>/`；自签名证书会触发信任警告，请核对终端显示的证书指纹。防火墙和云安全组仍可能需要由管理员另行放行端口。

再次运行同版本脚本会重新检测网卡地址，必要时更新证书并重新启动服务；安装后新增加的网卡地址需要重跑脚本才会进入证书。使用新版本脚本升级时保持相同的安装目录和端口；脚本先拉取新镜像，暂停旧服务写入，备份并验证数据库、报告和密钥，备份失败不升级。旧版手动 Compose 部署未自动接管，须先人工迁移；丢失密钥时不得重新初始化。数据库升级可能修改 schema，启动失败后不要只切回旧镜像，需使用安装目录下的匹配备份恢复。普通账号由管理员在设置页创建；资产、会话、任务和报告对已登录账号共享。

## 许可证

本项目使用 MIT License，详见 `LICENSE`。
