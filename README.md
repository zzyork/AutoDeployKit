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
- 交互式安装、升级和卸载

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

### 环境要求

- Linux、systemd、`ss`
- Python 3.14，可复用已有安装或按脚本提示编译安装
- 自动下载 Python 时需要 `curl` 和可信的系统 CA 证书
- 编译 Python 时需要 C 编译器、make、tar，以及 OpenSSL、zlib、SQLite 开发库；请提前准备

### 安装、升级与卸载

将交付的 wheel 与 `scripts/install_webui.sh` 放到目标机，在交互终端运行：

```bash
sudo bash install_webui.sh
```

1. 在菜单中选择安装、升级或卸载。
2. 安装或升级时输入 wheel 的绝对路径，也可通过脚本第一个参数传入。
3. 没有可用 Python 3.14 时，选择 `y` 从 python.org 下载并编译最新稳定版 `3.14.x`；选择 `n` 则提供本地 `.tgz` 或 `.tar.gz` 源码包。
4. 首次安装时设置管理员口令，无需手动执行 `pip install`。

Python 安装在 `/opt/autodeploykit/python-3.14`，不替换系统 Python。升级期间服务会短暂中断。卸载需输入 `UNINSTALL` 确认，保留数据目录、根密钥和服务账号。

默认位置：

| 内容 | 路径 |
| --- | --- |
| 程序 | `/opt/autodeploykit` |
| 数据 | `/var/lib/autodeploykit` |
| 巡检报告 | `/var/lib/autodeploykit/reports` |
| 加密根密钥 | `/etc/autodeploykit/master.key` |
| 服务地址 | `127.0.0.1:8765` |

可在安装前设置 `WEBUI_INSTALL_DIR`、`WEBUI_DATA_DIR`、`WEBUI_CONFIG_DIR`，使用互不重叠的规范绝对目录。

通过同机反向代理配置 HTTPS 和内网访问限制后，登录 WebUI，登记主机及 SSH 登录凭据，再执行巡检或查看历史报告。WebUI 不读取或导入 CLI 的 `hosts`；使用页面生成的 SSH 公钥时，需自行将公钥配置到目标服务器。当前不提供任意命令执行或服务修改。

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
- WebUI 安装脚本不校验 Python 源码包的 SHA256 或发布签名，请确保下载渠道和本地源码包可信。
- SSH 首次连接不会验证主机身份，存在中间人风险；请限制在受控网络使用，不要直接将 WebUI 暴露到公网。

## 许可证

本项目使用 MIT License，详见 `LICENSE`。
