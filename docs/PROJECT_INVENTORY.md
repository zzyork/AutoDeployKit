# AutoDeployKit 项目清单

> 这是源码仓库的目录、文件、模块和功能导航索引。Agent 开始任务时必须先读取本文件，再按任务需要读取 `README.md`、项目指令和具体实现。

## 使用规则

- 本文件是仓库级定位入口，不替代 `README.md` 的安装和使用说明，也不替代设计文档。
- 只收录 Git 已跟踪且计划推送的仓库文件及其所在目录，以 `git ls-files` 核验；未跟踪、被忽略、仅在本机或仓库外存在、明确不推送的路径一律不记录。新增文件纳入版本控制后再登记。
- 每次仓库变更都必须同步更新本文件；至少检查目录、文件、模块、功能、入口、关键符号和状态是否仍准确。纯文本或注释变更也要在“变更记录”中登记。
- 新增、删除、移动或重命名目录/文件，新增或移除模块、功能、入口、接口、脚本、配置或测试时，必须在同一次变更中更新对应清单项。
- Agent 的定位顺序：读取根目录 `AGENTS.md`/`CLAUDE.md` -> 读取本文件 -> 按“功能索引”定位模块和文件 -> 读取 `README.md` 确认公开用法 -> 搜索实现、入口和调用方。
- 清单只描述源码结构和公开用途，不记录真实服务器地址、账号、密码、私钥、模型密钥、报告正文或其他运行时秘密。
- 本文件的路径使用仓库相对路径；关键符号以当前源码名称记录，行号不作为稳定定位依据。

## 目录索引

| 目录 | 类型 | 用途 |
| --- | --- | --- |
| `middleware_ops/` | Python 模块 | Nginx、MySQL、Redis、RabbitMQ 中间件管理 |
| `monitor_ops/` | Python 模块 | Prometheus、各类 exporter 监控安装 |
| `server_check/` | Python 模块和数据目录 | CLI 服务器巡检、配置和报告输出 |
| `server_ops/` | Python 模块 | 服务器初始化、系统配置和 OpenSSL 管理 |
| `software_ops/` | Python 模块 | Docker、Minio、Supervisor、JDK 管理 |
| `utils/` | Python 支撑模块 | SSH、文件传输、菜单、输出、发行版和软件检测 |
| `config/` | 配置模板 | Linux、Docker、MySQL、Nginx、Prometheus 等服务模板 |
| `scripts/` | 运维脚本 | 离线巡检、漏洞检查和 pip 引导 |
| `docs/` | 项目文档 | 项目清单 |

## 根目录文件

| 文件 | 用途 |
| --- | --- |
| `AGENTS.md` | 源码仓库维护、Agent 操作和远程操作约束 |
| `docs/PROJECT_INVENTORY.md` | 本清单；目录、文件、功能、模块和入口的权威导航 |
| `.gitignore` | 忽略缓存、环境、凭据、运行时报告和构建产物 |
| `cli.py` | CLI 主入口，详见“入口索引” |
| `pyproject.toml` | 项目元数据和 Python 工具配置 |
| `README.md`、`README.en.md` | 中文和英文公开使用说明 |
| `hosts.example` | CLI 主机清单格式示例；含仅供人工查看的可选 `remark` 备注，不含真实资产 |
| `LICENSE` | MIT 许可证 |

## 入口索引

| 入口 | 调用方式 | 说明 |
| --- | --- | --- |
| `cli.py:main` | `python cli.py <module_name> <host_pattern>`；安装后为 `autodeploykit` | 读取本地主机配置，建立 SSH 连接，动态导入 `<module_name>.main` 并调用 `run(clients)` |
| `server_ops/main.py:run` | `server_ops` | 服务器初始化菜单 |
| `middleware_ops/main.py:run` | `middleware_ops` | 中间件管理菜单 |
| `software_ops/main.py:run` | `software_ops` | 软件管理菜单 |
| `monitor_ops/main.py:run` | `monitor_ops` | 监控管理菜单 |
| `server_check/main.py:run` | `server_check` | 并发执行 CLI 巡检并写入报告 |
| `scripts/server_check_offline.sh` | Shell 直接调用 | 离线巡检辅助脚本 |
| `scripts/check_nginx_cve_2026_42945.py:main` | Python 直接调用 | Nginx CVE 检查 |
| `scripts/generate_nginx_vulnerability_report.py:main` | Python 直接调用 | 生成 Nginx 漏洞报告 |

## 功能索引

| 功能 | 首选模块/文件 | 当前状态 |
| --- | --- | --- |
| 主机清单解析和 SSH 连接 | `cli.py`、`utils/ssh_utils.py` | CLI 已接入；主机配置格式参见 `hosts.example`；可选 `remark` 仅供人工查看，不进入连接配置 |
| 主机名设置 | `server_ops/hostname_ops.py` | CLI 菜单已接入 |
| 软件包和 DNF 仓库管理 | `server_ops/pkg_ops.py` | CLI 菜单已接入 |
| firewalld/SELinux 管理 | `server_ops/firewall_ops.py` | CLI 菜单已接入 |
| 内核 limits/sysctl 调优 | `server_ops/kernel_optimize_ops.py` | CLI 菜单已接入 |
| 磁盘分区、LVM 和挂载 | `server_ops/disk_partition_ops.py` | CLI 菜单已接入；具有破坏性 |
| NTP、vimrc、SELinux 系统优化 | `server_ops/system_optimize_ops.py` | CLI 菜单已接入 |
| OpenSSL 升级和 libssl 修复 | `server_ops/openssl_upgrade.py` | CLI 菜单已接入 |
| Nginx 安装、升级、备份、回滚 | `middleware_ops/nginx_manager.py` | CLI 菜单已接入 |
| MySQL 安装、升级、备份、回滚 | `middleware_ops/mysql_manager.py` | CLI 菜单已接入 |
| Redis 安装、备份、回滚 | `middleware_ops/redis_manager.py` | CLI 菜单已接入 |
| RabbitMQ 安装 | `middleware_ops/rabbitmq_manager.py` | CLI 菜单已接入；README 标明升级、备份、回滚尚未接入菜单 |
| Prometheus 安装 | `monitor_ops/prometheus_monitor.py` | CLI 菜单已接入 |
| node-exporter 安装 | `monitor_ops/node_exporter.py` | CLI 菜单已接入 |
| mysqld-exporter 安装 | `monitor_ops/mysql_exporter.py` | CLI 菜单已接入 |
| redis-exporter 安装 | `monitor_ops/redis_exporter.py` | CLI 菜单已接入 |
| Docker 和 Compose 管理 | `software_ops/docker_manager.py` | CLI 菜单已接入；Docker 安装前校验配置模板并检查命令结果 |
| Minio 管理 | `software_ops/minio_manager.py` | CLI 菜单已接入 |
| Supervisor 管理和 ini 管理 | `software_ops/supervisor_manager.py` | CLI 菜单已接入；远程修改受根目录规则约束 |
| JDK 查询和安装 | `software_ops/jdk_manager.py` | CLI 菜单已接入 |
| CLI 服务器巡检 | `server_check/main.py` | 已接入；默认报告目录参见 `README.md` |
| Nginx 漏洞检查和报告 | `scripts/check_nginx_cve_2026_42945.py`、`scripts/generate_nginx_vulnerability_report.py` | 独立脚本，不属于 CLI 菜单 |

## CLI 模块和文件

### `server_ops/`：服务器初始化

| 文件 | 模块职责 | 关键符号 |
| --- | --- | --- |
| `server_ops/main.py` | 注册服务器初始化菜单 | `operations`、`run` |
| `server_ops/hostname_ops.py` | 校验并设置主机名 | `is_valid_hostname`、`manage_hostname` |
| `server_ops/pkg_ops.py` | 基础依赖、软件包和 DNF 仓库操作 | `manage_packages`、`manage_dnf_repos`、`list_dnf_repos`、`add_dnf_repo`、`modify_dnf_repo_url`、`delete_dnf_repo` |
| `server_ops/firewall_ops.py` | firewalld 规则和 SELinux 操作 | `manage_firewall_selinux`、`manage_firewalld`、`list_rules`、`add_rules`、`delete_rules` |
| `server_ops/kernel_optimize_ops.py` | limits、sysctl 检查和调优 | `check_and_optimize_limits`、`check_and_optimize_sysctl`、`kernel_optimize` |
| `server_ops/disk_partition_ops.py` | 分区、LVM、挂载和磁盘占用检查 | `list_unmounted_disks`、`create_lvm_and_mount`、`manage_disk_partition` |
| `server_ops/system_optimize_ops.py` | NTP、vimrc、SELinux 优化 | `configure_ntpdate`、`optimize_vimrc`、`disable_selinux`、`manage_system_optimize` |
| `server_ops/openssl_upgrade.py` | OpenSSL 1.1/3 升级和运行库修复 | `upgrade_openssl_1_1_1`、`upgrade_openssl_v3`、`fix_libssl_so3`、`manage_ssl` |
| `server_ops/__init__.py` | 包标识 | 无公开入口 |

### `middleware_ops/`：中间件管理

| 文件 | 模块职责 | 关键符号 |
| --- | --- | --- |
| `middleware_ops/main.py` | 注册中间件菜单 | `operations`、`run` |
| `middleware_ops/nginx_manager.py` | Nginx 安装、升级、备份、回滚 | `install_nginx`、`upgrade_nginx`、`backup_nginx`、`rollback_nginx`、`list_nginx_backups`、`manage_nginx` |
| `middleware_ops/mysql_manager.py` | MySQL 安装、升级、备份、回滚 | `install_mysql`、`upgrade_mysql8`、`backup_mysql`、`rollback_mysql`、`list_mysql_backups`、`manage_mysql` |
| `middleware_ops/redis_manager.py` | Redis 安装、备份、回滚 | `install_redis`、`backup_redis`、`rollback_redis`、`list_redis_backups`、`manage_redis` |
| `middleware_ops/rabbitmq_manager.py` | RabbitMQ 安装及版本相关配置 | `install_rabbitmq`、`upgrade_rabbitmq`、`backup_rabbitmq`、`rollback_rabbitmq`、`list_rabbitmq_backups`、`manage_rabbitmq` |
| `middleware_ops/__init__.py` | 包标识 | 无公开入口 |

### `monitor_ops/`：监控管理

| 文件 | 模块职责 | 关键符号 |
| --- | --- | --- |
| `monitor_ops/main.py` | 注册监控菜单 | `operations`、`run` |
| `monitor_ops/prometheus_monitor.py` | Prometheus 安装和管理 | `install_prometheus`、`manage_prometheus` |
| `monitor_ops/node_exporter.py` | node-exporter 安装、端口和指标检查 | `install_node_exporter`、`manage_node_exporter` |
| `monitor_ops/mysql_exporter.py` | mysqld-exporter 安装 | `install_mysqld_exporter`、`manage_mysql_exporter` |
| `monitor_ops/redis_exporter.py` | redis-exporter 安装 | `install_redis_exporter`、`manage_redis_exporter` |
| `monitor_ops/__init__.py` | 包标识 | 无公开入口 |

### `software_ops/`：软件管理

| 文件 | 模块职责 | 关键符号 |
| --- | --- | --- |
| `software_ops/main.py` | 注册软件菜单 | `operations`、`run` |
| `software_ops/docker_manager.py` | Docker、Compose 安装、Docker 配置校验和失败检查 | `install_docker`、`install_docker_compose`、`manage_docker` |
| `software_ops/minio_manager.py` | Minio 安装和管理 | `install_minio`、`manage_minio` |
| `software_ops/supervisor_manager.py` | Supervisor 安装和 ini 增删改 | `install_supervisor`、`configure_ini`、`add_ini`、`modify_ini`、`delete_ini`、`manage_supervisor` |
| `software_ops/jdk_manager.py` | JDK 版本查询、下载和安装 | `get_current_jdk_version`、`get_foojay_jdk_package`、`install_jdk`、`manage_jdk` |
| `software_ops/__init__.py` | 包标识 | 无公开入口 |

## 巡检模块和文件

| 文件 | 模块职责 | 关键符号 |
| --- | --- | --- |
| `server_check/main.py` | 注册检查项、执行 CLI 巡检、写 Markdown 报告 | `CHECK_HANDLERS`、`inspect_server`、`choose_report_path`、`run` |
| `server_check/common.py` | 默认巡检配置和配置合并 | `DEFAULT_CONFIG`、`load_config` |
| `server_check/server_info.py` | 主机基础信息 | `server_info` |
| `server_check/server_resources.py` | CPU、内存、磁盘、Swap 资源 | `system_resources` |
| `server_check/security.py` | 安全配置检查 | `security_info` |
| `server_check/services.py` | systemd 服务状态 | `service_status` |
| `server_check/network.py` | 网络和监听端口 | `network_info` |
| `server_check/docker.py` | Docker 状态和容器信息 | `docker_status` |
| `server_check/supervisor.py` | Supervisor 状态 | `supervisor_status` |
| `server_check/error_logs.py` | journal 和日志文件错误汇总 | `log_error` |
| `server_check/monitors.py` | 监控服务状态 | `monitors` |
| `server_check/config.json` | 巡检配置覆盖项 | JSON 配置，不含凭据 |
| `server_check/__init__.py` | 包标识 | 无公开入口 |

## 共享模块和文件

| 文件 | 模块职责 | 关键符号 |
| --- | --- | --- |
| `utils/ssh_utils.py` | Paramiko 连接、跳板机、命令执行和关闭 | `ssh_connect`、`close_ssh_client`、`run_command`、`run_command_live` |
| `utils/file_utils.py` | 下载、上传、校验、远端文件比较和版本/EOL 查询 | `download_file`、`upload_file`、`remote_download_or_upload`、`compare_file_content`、`get_stable_version`、`get_eol_date` |
| `utils/linux_distro.py` | 解析 `/etc/os-release` 和识别发行版系列 | `get_linux_distribution` |
| `utils/software_check.py` | 检查软件是否安装、进程是否运行 | `check_software_started` |
| `utils/server_utils.py` | IP 地址校验 | `is_valid_ip` |
| `utils/menu_runner.py` | 多主机菜单循环和操作分发 | `run_menu` |
| `utils/choice.py` | 是/否确认和菜单选择 | `confirm_yes_no`、`menu_choice` |
| `utils/output.py` | CLI 输出缓冲、日志和状态输出 | `buffer_output`、`log`、`print_info`、`print_success`、`print_warning`、`print_error`、`print_header`、`print_step` |
| `utils/__init__.py` | 包标识 | 无公开入口 |

## 配置、部署和文档文件

| 文件或目录 | 用途 |
| --- | --- |
| `pyproject.toml` | 项目元数据、依赖、命令入口、打包、ruff 和 mypy 配置 |
| `config/docker/` | Docker daemon、service、socket 模板 |
| `config/linux/` | vimrc、sysctl 和软件源模板 |
| `config/minio/` | Minio 配置和 systemd service 模板 |
| `config/mysql/` | MySQL 配置和 systemd service 模板 |
| `config/nginx/` | Nginx 配置和 systemd service 模板 |
| `config/prometheus/` | Prometheus、node、MySQL、Redis exporter 配置和 service 模板 |
| `config/redis/` | Redis systemd service 模板 |
| `config/supervisor/` | Supervisor 配置、service 和程序 ini 模板 |
| `README.md` | 中文项目介绍、功能、环境、安装和使用说明 |
| `README.en.md` | 英文项目说明 |
| `LICENSE` | MIT 许可证 |
| `monitor.html` | 独立监控页面资源，当前不属于 Python CLI 主入口 |

### `config/` 具体文件

| 目录 | 文件 |
| --- | --- |
| `config/docker/` | `daemon.json`（有效 JSON）、`docker.service`、`docker.socket` |
| `config/linux/` | `.vimrc`、`sysctl.conf`、`temp.repo` |
| `config/minio/` | `minio.conf`、`minio.service` |
| `config/mysql/` | `my.cnf`、`mysqld.service` |
| `config/nginx/` | `nginx.conf`、`nginx.service` |
| `config/prometheus/` | `mysqld-exporter.service`、`mysqld_exporter.conf`、`node-exporter.service`、`prometheus.service`、`prometheus.yml`、`redis-exporter.service` |
| `config/redis/` | `redis.service` |
| `config/supervisor/` | `program.ini`、`supervisord.conf`、`supervisord.service` |

## 变更记录

- 2026-10-27：明确所有远程操作仅允许分批次通过 SSH 组件执行单条命令，每次检查结果后再继续，禁止拼接或包装执行多条命令；移除不存在且未被 Git 跟踪的 `CLAUDE.md` 清单项。
- 2026-10-26：在 `hosts.example` 和中英文使用说明中补充可选 `remark="备注内容"` 及引号用法；复用现有解析器忽略未使用字段的行为，备注不进入主机连接配置。
