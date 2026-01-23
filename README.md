# AutoDeployKit

一个面向多台服务器的自动化运维与部署工具，支持通过 SSH 一键执行服务器初始化、软件安装/升级、监控安装与服务器巡检等常见任务。以分模块的方式组织功能，通过 `cli.py` 指定模块与主机组，批量连接并交互式执行操作。


！！！本工具仅适用于，CentOS 7、CentOS 8、CentOS 9、OpenEuler、RockyLinux 等基于 RPM 的 Linux 发行版
---

## 功能特性

- 服务器初始化
  - 设置主机名
  - 配置 Yum 源、软件包安装
  - 防火墙 firewalld 管理、SELinux 管理
  - 内核参数与系统优化
  - 裸盘分区、LVM 创建与挂载到指定目录
  - OpenSSL 安全升级
- 软件管理
  - Nginx 源码安装、升级与 systemd 管理
  - Docker 二进制安装与 systemd 管理
- 监控部署
  - mysqld_exporter 安装与凭据配置
  - Prometheus 二进制安装与 systemd 管理
- 服务器巡检
  - 采集系统信息、资源使用、服务状态、网络与端口、日志错误等
  - 以 Markdown 报告落盘归档（按主机组与月份归档）
- SSH 批量执行
  - 支持密码与密钥登录
  - 支持跳板机/代理连接
  - 实时输出远程命令执行过程

---

## 目录结构

```
.
├─ cli.py                   # 命令行入口：选择模块并加载主机组
├─ requirements.txt         # 依赖
├─ config/                  # systemd 与服务模板配置
├─ scripts/                 # 辅助脚本
├─ server_ops/              # 服务器初始化相关操作
│  ├─ main.py               # 菜单入口
│  ├─ hostname_ops.py       # 主机名管理
│  ├─ dnf_repos_ops.py      # Yum 源
│  ├─ pkg_ops.py            # 软件包
│  ├─ firewall_selinux_ops.py# 防火墙/SELinux
│  ├─ kernel_optimize_ops.py# 内核调优
│  ├─ disk_partition_ops.py # 裸盘分区+LVM+挂载
│  ├─ system_optimize_ops.py# 系统优化
│  └─ openssl_upgrade.py    # OpenSSL 升级
├─ middleware_ops/            # 软件管理（Nginx、Docker）
│  ├─ main.py
│  ├─ nginx_manager.py
│  └─ docker_manager.py
├─ monitor_ops/             # 监控部署（mysqld_exporter、Prometheus）
│  ├─ main.py
│  ├─ mysql_monitor.py
│  └─ prometheus_monitor.py
├─ server_check/            # 服务器巡检与报告生成
│  └─ main.py
├─ server_check_reports/    # 巡检报告输出目录（运行时生成）
└─ utils/                   # 工具库
   ├─ ssh_utils.py          # SSH 连接、命令执行（支持代理）
   ├─ file_utils.py         # 下载/上传文件、模板渲染、GitHub 版本获取, MD5 工具
   ├─ output.py             # 彩色日志打印与本地日志落盘
   └─ server_utils.py       # 服务器工具函数
```

---

## 环境要求

- Python 3.9+（建议）
- 基本可访问外网（用于下载组件包与 GitHub API 查询）
- 目标服务器
  - Linux（CentOS/Rocky/Alma 等 RHEL 系）
  - 拥有 sudo/root 权限
  - 能通过 SSH 访问；若需跳板机，需提供代理参数

安装依赖：

```bash
pip install -r requirements.txt
```

---

## 主机清单（hosts）

`cli.py` 会从当前工作目录读取名为 `hosts` 的文件（INI 格式，按组组织）。示例：

```
[webservers]
192.168.1.10 user=root password=passw0rd port=22
192.168.1.11 user=ec2-user keyfile="~/.ssh/id_rsa" port=22

[dbservers]
10.0.0.5 user=root keyfile="/path/to/key" proxy=10.0.0.2 proxy_user=jump proxy_password=*** proxy_port=22
```

支持字段：
- user、port、password、keyfile（等价于内部的 key_file）
- vip（虚拟 IP，若提供将优先用于连接）
- proxy、proxy_user、proxy_password、proxy_keyfile、proxy_port（跳板机连接）

---

## 使用方法

通用调用方式：

```bash
python cli.py <module_name> <group>
```

- `<module_name>` 可选：
  - `server_ops` 服务器初始化
  - `middleware_ops` 软件管理（Nginx、Docker）
  - `monitor_ops` 监控部署（mysqld_exporter、Prometheus）
  - `server_check` 服务器巡检（生成 Markdown 报告）
- `<group>`：主机清单中的组名，例如 `webservers`

示例：

```bash
# 服务器初始化（交互式菜单）
python cli.py server_ops webservers

# 软件管理（Nginx、Docker）
python cli.py middleware_ops webservers

# 监控安装（mysqld_exporter、Prometheus）
python cli.py monitor_ops dbservers

# 服务器巡检（生成报告到 server_check_reports/<group>/<YYYYMM>/）
python cli.py server_check webservers
```

---

## 主要模块说明

- server_ops
  - 主机名、Yum 源、包管理、防火墙与 SELinux、内核与系统优化
  - 磁盘分区与挂载：列出未分区裸盘，创建 GPT + LVM，格式化为 XFS 并挂载到 `/data`
  - OpenSSL 升级：执行安全加固/升级
- middleware_ops
  - Nginx：从官网获取稳定版，源码编译安装，支持 `nginx.conf` 模板与 systemd 守护
  - Docker：从官方 static 发行版安装二进制，支持 systemd 守护
- monitor_ops
  - mysqld_exporter：从 GitHub 获取最新版，上传并安装，交互式注入数据库连接参数，配置 systemd
  - Prometheus：从 GitHub 获取最新版，上传并安装，创建数据目录并配置 systemd
- server_check
  - 采集基础信息、资源、服务状态、网络与端口、日志错误，输出 Markdown 报告

---

## 注意事项与最佳实践

- 以 root 或具备 sudo 权限执行目标命令，否则部分操作会失败
- 磁盘分区/LVM 创建会更改磁盘数据，务必确认选择的磁盘与二次确认提示
- 外网依赖：若无法直连，需预先下载包到 `packages/` 再由工具上传
- 跳板机：提供 `proxy` 相关参数可透传连接
- 多台主机执行时，操作按顺序对每台主机执行，失败会提示但不影响其他主机

---

## 开发与贡献

- 欢迎提交 Issue 与 PR
- 代码风格：尽量保持现有模块化与交互式设计

---

## 许可证

本项目使用 MIT License，详见 `LICENSE`。
