# 项目启动指令

- 每个新对话或开始处理本仓库任务时，必须先读取本文件，并遵守其中的偏好与安全规则。
- 在未读取这些项目指令前，不要执行依赖项目规则的操作。

# Memory

## Preferences
- 只有当需要调用本仓库模块或流程时，才先加载本地目录 `.venv` 下的虚拟环境。
- 检查 `.venv` 是否存在时，必须读取项目根目录的目录列表或直接读取 `.venv` 路径进行确认；不要使用可能忽略隐藏目录的 glob 结果作为唯一判断依据。
- 如果调用本仓库模块或流程时经上述方式确认 `.venv` 不存在，则先询问用户是安装虚拟环境还是直接使用本地 Python 环境；待用户确认后，再进行安装依赖、模块调用等后续操作。
- 如果调用本仓库模块或流程时 `.venv` 存在但无法加载，则先提示用户，并停止后续依赖该环境的操作。
- 所有需要远程ssh服务器的操作，必须先从 `hosts` 文件读取目标服务器的 SSH 配置信息。
- 如果 `hosts` 中不存在对应服务器配置、存在多个近似或同名条目、或 SSH 信息不足以执行操作，则直接中止并提示用户，不继续执行。
- 在成功读取 `hosts` 中的 SSH 配置后，优先检查本仓库是否已有可执行该操作的模块或流程。
- 如果仓库中存在对应模块或流程，优先调用该模块或流程执行。
- 如果仓库中不存在对应模块或流程，先向用户输出计划采用的安装/操作流程，并询问是否按该流程执行；得到确认后再继续执行。
- 当用户说“巡检”时，默认调用 `server_check` 模块执行对应巡检流程。
- 通过 SSH 连接到服务器执行命令时，任何查看类命令无需确认，可直接执行。
- 通过 SSH 连接到服务器执行命令时，任何修改类或重启类命令都必须先征求用户确认，未确认前不得执行。
- 通过 SSH 连接到服务器执行命令时，任何移动、删除、停止、关闭类命令一律禁止执行。
- 禁止在git仓库中添加任何涉及到真实服务器的信息。
- 使用结束巡检模块后，对巡检报告进行分析。

## SSH 命令执行分级规则

- 查看类命令：仅用于读取信息，不改变系统、服务、文件、数据库、容器状态，可直接执行，无需确认。
  - 示例：`ls`、`cat`、`grep`、`find`、`pwd`、`df`、`du`、`free`、`ps`、`top`、`ss`、`netstat`、`ip a`、`systemctl status`、`journalctl`、`docker ps`、`docker logs`、数据库 `SELECT/SHOW`、`git status/log/diff`

- 修改/重启类命令：任何会写入、覆盖、安装、变更配置、修改权限、变更数据、reload 或 restart 的命令，必须先征求用户确认。
  - 示例：`vim`、`sed -i`、`tee`、`>`、`>>`、`chmod`、`chown`、`apt/yum/pip install`、`systemctl restart`、`systemctl reload`、`docker restart`、数据库 `INSERT/UPDATE/ALTER/CREATE`、`git commit/push`

- 移动/删除/停止/关闭类命令：任何会移动、删除、终止进程、停止服务、关闭系统、删除容器或删除数据的命令，一律禁止执行。
  - 示例：`mv`、`rm`、`rmdir`、`unlink`、`kill`、`pkill`、`killall`、`systemctl stop`、`shutdown`、`poweroff`、`reboot`、`docker stop`、`docker rm`、`docker compose down`、数据库 `DELETE/DROP/TRUNCATE`、`git reset --hard`、`git clean -fd`

- 兜底规则：如果某条命令是否会产生修改存在歧义，则默认按“修改类命令”处理，先确认后再执行。

## Supervisor 子应用创建流程

- 当用户要求“新建 supervisor 子应用”“从已有后端子应用抄配置”或类似操作时，必须按本流程处理。
- 在连接目标服务器后，先只执行查看类命令收集信息，不要立即写入配置：
  - 检查 `supervisord` / `supervisorctl` 是否存在及服务状态。
  - 读取 `/etc/supervisord.conf` 的 `files=` include 配置，确认 ini 目录，常见为 `/etc/supervisord.d`。
  - 查看已有后端应用 ini 配置摘要，重点关注 `command`、`directory`、`user`、`autostart`、`startsecs`、`autorestart`、`stdout_logfile` 等字段。
  - 检查目标 ini 是否已存在；如已存在，停止操作并询问用户，不得覆盖。
  - 检查目标应用目录、日志目录是否存在，并查看相关端口占用情况。
- 根据已有同类后端配置生成新 ini 草案：
  - `[program:<应用名>]` 与文件名 `<应用名>.ini` 保持一致。
  - 优先复用同环境、同 Java 版本、同 jar 命名习惯的后端应用配置。
  - 端口应避开已占用端口；若端口无法从上下文确定，必须询问用户确认。
  - 不要擅自创建应用目录、上传 jar 或变更业务文件，除非用户明确要求。
- 在写入远程 ini 文件、执行 `supervisorctl update`、`systemctl reload/restart` 等任何修改/重启类操作前，必须向用户展示拟写入的完整配置和拟执行动作，并取得明确确认。
- 用户确认后，才可将 ini 写入目标 include 目录，并执行 `supervisorctl update` 应用配置。
- 写入后必须验证：
  - 读取新建 ini 内容确认配置落地。
  - 执行 `supervisorctl status <应用名>` 查看状态。
  - 如果出现 `BACKOFF`、`FATAL` 等状态，只做查看和说明；常见原因包括应用目录或 jar 尚未部署、端口冲突、启动参数错误。不得擅自删除、移动、停止服务或修改业务文件。
- 最终回复用户时，说明已操作的服务器、ini 路径、核心配置、`supervisorctl update` 结果和当前状态。
