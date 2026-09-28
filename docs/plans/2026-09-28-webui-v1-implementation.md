# WebUI 第一版代码实施计划

> 状态：实施基线，尚未实现 WebUI。本文取代同目录的 WebUI 早期架构草案中与本文不一致的主机来源、凭据、报告位置和部署方式；不得按旧草案执行。

**目标：** 内网单用户在浏览器管理数据库资产、SSH 登录密钥和密码，通过自然语言发起只读巡检，查看逐主机进度及历史报告。CLI 代码、`hosts` 读取和报告路径行为不变。

**架构：** 单进程 FastAPI/Uvicorn + 原生 HTML/CSS/JavaScript + SQLite + Markdown 报告。WebUI 只从数据库选择已登记且启用的资产，所有远程连接通过 `utils/ssh_utils.py`；一次只运行一个远程任务，单任务最多并发巡检 5 台。模型只可请求后端固定工具，不能提交 shell 命令。

**依赖：** 复用 Paramiko、requests、SQLite 和标准库；WebUI 在项目的 `web` 可选依赖中声明 FastAPI、Uvicorn，以及直接使用的 `cryptography`，CLI 基础依赖不额外安装 Web 框架。CLI 继续声明 Python >=3.9；安装脚本要求系统预先提供 Python 3.14 正式版，不下载、不替换系统 Python。删除 `pip` 运行依赖（安装器不是应用运行库），保证项目元数据不再和 Python 3.9 冲突；WebUI 用 Python 3.14 建立独立虚拟环境并验收依赖。

## 已确认的边界

- CLI 仅使用源码工作区的 `hosts` 和现有参数、报告路径行为；WebUI **不读取、不预览、不导入、不依赖** `hosts`。因此不创建本机辅助导入命令、不复制 `hosts`、不支持导入旧私钥文件。资产和跳板机均在页面登记，可选 WebUI 生成的 SSH 登录密钥或手填密码；密码与私钥仅以密文入库。用户自行将生成的公钥配置到远端账号。
- WebUI 数据目录由安装脚本设定，默认 `/var/lib/autodeploykit`，数据库、报告、应用日志分别放在其下的固定子路径；加密根密钥另置于 `/etc/autodeploykit/master.key`。报告根目录是 `WEBUI_DATA_DIR/reports`，Web 请求不能指定根目录。CLI 的报告路径不变。
- 客户自管 Linux：仅交付 wheel 和安装脚本，目标机不要求存在项目源码目录。安装目录默认 `/opt/autodeploykit`，只允许服务账号和管理员读取、服务账号不可写代码；客户 root 仍可查看或提取本机代码，文件权限及二进制打包不能提供商业源码保密保证。第一版不引入商业授权或远端商业核心。
- 安装目录内的 `AGENTS.md` 与 `CLAUDE.md` 从 `config/webui/` 专用模板安装，内容只描述数据库资产、Web 报告路径和既有 SSH 命令分级，不复制源码仓库的 CLI 指令；这些文本不是运行时安全控制，应用自身必须强制执行。源码仓库的同名文件只约束源码仓库和 CLI 工作流。
- WebUI 只开放只读巡检 `inspect_servers` 与本地报告索引 `latest_inspection`；不开放安装、配置、重启、停止、删除或任意命令。Web 的 Docker 检查使用 `docker --context default ...`，不切换当前 context；CLI 行为保持不变。
- 内网单用户；Web 服务仅绑定 `127.0.0.1`，同机反向代理负责 HTTPS 和网段限制，Uvicorn 仅一个 worker。管理员口令通过本机交互输入，不开放抢注入口。目标及跳板机沿用现有 `AutoAddPolicy` 的主机身份风险，正式部署前明确记录风险接受和受控内网边界，不宣称登录密钥解决该问题。

## 阶段 1：规则、依赖与巡检核心

**文件：** `AGENTS.md`、`CLAUDE.md`、`README.md`、`pyproject.toml`、`.gitignore`、`server_check/main.py`、`server_check/common.py`、`server_check/docker.py`、`server_check/monitors.py`、`server_check/services.py`、`utils/ssh_utils.py`、`utils/output.py`、`tests/test_webui_inspection.py`。

1. 先写假 SSH 的 CLI 兼容测试与 Web 巡检失败/越界测试。CLI 继续从 `hosts` 读取主机，`run(clients)` 保留 `sys.argv` 分组、`MAX_WORKERS`、`load_config()`、目录选择与 Docker context 切换；SSH 新参数只能追加在既有位置参数之后并提供兼容默认值。
2. 在源码仓库规则中明确：工作区内的 AI/CLI 远程操作仍须从 `hosts` 读取目标、经 `utils/ssh_utils.py` 执行，Agent 执行巡检仍按源码规则保存 `server_check/reporters`；CLI 程序本身的目录选择功能不变。已安装 WebUI 仅用数据库已启用资产，报告写 `WEBUI_DATA_DIR/reports`，操作权限不低于现有 SSH 分级规则。WebUI 部署前完成这一步；只改文档不能代替运行时校验。
3. `inspect_server` 显式接受资产/组/检查项、报告目标和配置，返回逐主机 `{status, alerts, report_id, error}`；CLI 包装保留旧路径，Web 不读取 `sys.argv`、`SERVER_CHECK_REPORT_DIR`、`SERVER_CHECK_CONFIG` 或请求指定的目录/日志路径/服务名。Web 配置只使用经过审计的固定检查项、阈值、服务和日志路径，明确允许的远端命令及其参数；不把 `CHECK_HANDLERS` 全表直接当成安全白名单。
4. 审计 Web 允许的所有 handler。`monitors` 的远端 exporter 名称先做格式约束与引用，`services` 的候选名仅使用固定枚举并引用；任何动态参数不得拼接为可执行片段。Web 的远程命令不执行 `source /etc/profile` 或隐式登录 shell，避免只读检查被 profile 的副作用改变；CLI 保持原执行方式。若某检查无法证明只读或越权风险，则从 Web 固定集合中排除并说明，不以模型提示词代替策略门。Web 调用共享巡检 handler 时，`utils/output.py` 不得把原始 stdout/stderr、异常或含远端数据的日志写入只读安装目录和 systemd journal；只把受限状态与脱敏错误写数据目录，CLI 默认 `output.log` 行为不变。
5. 在 `utils/ssh_utils.py` 的 Web 专用调用路径上规定连接/跳板隧道/单命令的总截止时间、stdout/stderr 同时排空及总字节上限；超时或超限关闭通道和所有已建立连接并将该主机记失败，后续任务可继续。每台的检查次数与总时长也要有上界；CLI 默认调用参数和现有行为不变。
6. Web 报告文件名包含随机且唯一的报告 ID，不采用会覆盖历史文件的“主机+月份”命名；目录、临时文件、最终文件和按 ID 读取时均限定到固定根目录，拒绝越界、符号链接和重复文件名，使用独占创建或等效方式。CLI 原命名不变。报告权限仅服务账号可读；远端进程参数和错误日志可能含秘密，**只有已登录管理员的报告接口**可按需返回原文，其余 API、模型上下文、服务日志和任务状态只存预定义的风险类别、级别、数量及报告 ID 等受限字段，不复制远端原句，绝不回显托管密码、私钥或模型密钥。
7. 测试恶意 exporter 名/服务名/日志路径、profile 副作用、卡住或持续写 stderr 的命令、跳板连接中途失败、重复巡检和报告路径符号链接；测试只读安装目录下成功与失败巡检均不创建 `output.log`，错误或远端数据不进入服务日志。运行既有 CLI 离线回归，不连接真实服务器。

## 阶段 2：数据库、凭据与单用户认证

**文件：** `webui/storage.py`、`webui/security.py`、`webui/assets.py`、`utils/ssh_utils.py`、`tests/test_webui_assets.py`、`tests/test_webui_security.py`。

1. SQLite 表包括 `admin_auth`、`sessions`、`settings`、`ssh_keys`、`hosts`、`conversations`、`messages`、`jobs`。主机存展示名、地址/端口、组/标签、启用状态、账号、所选密钥 ID 或加密密码及可选跳板机认证；不接受任意请求地址作为工具目标。名称、组、地址、端口与目标资产 ID 做服务端校验，重复/歧义匹配拒绝，停用保留任务历史。SQLite 每线程独立连接、关键写入事务化。
2. 安装脚本在建数据库前创建服务账号及数据/配置目录；以特权安装身份原子生成根密钥并设定仅管理员与服务账号可读的权限，数据目录仅服务账号可写。首次建库时写入一个用根密钥认证加密的固定校验值；每次启动先验证该值，已有数据库但密钥缺失或被替换时即使库内尚无凭据也拒绝启动，绝不自动重建密钥或覆盖库。随后本机用 `getpass` 交互设置首个管理员口令，再启动服务；非交互首次安装需明确中止。口令用带盐慢哈希，可逆凭据使用 `cryptography` 的认证加密；备份和恢复分别验证数据库、报告和根密钥。
3. `ssh_connect` 接受内存密钥或密码作为目标/跳板认证，保留 CLI 文件路径接口；Web 连接禁用 Paramiko 的 SSH agent 和本机密钥搜索（`allow_agent=False`、`look_for_keys=False`），不接受文件私钥路径，所选认证方式必须完整且互斥；CLI 默认认证行为不变。连接关闭覆盖成功、错误和超时。WebUI 可生成多组 Ed25519 登录密钥对，页面只展示公钥和密码是否已配置，不回显私钥或密码；敏感变更要求重新输入管理员口令。
4. 会话令牌仅在 HttpOnly/SameSite Cookie 中，数据库存令牌哈希；HTTPS 代理下开启 Secure，所有写接口校验 Origin 与 CSRF，登录及聊天限流，设置 CSP 等安全响应头。管理员初始化仅本机命令，不提供匿名初始化 API。
5. 用临时数据库和假的 SSH client 验证密文入库、手填密码与生成密钥在目标/跳板传递、目标与跳板均禁用 SSH agent 和本机私钥搜索、生成私钥可在内存解析且公钥匹配、停用/歧义资产拒绝连接、秘密不在 API/错误/模型上下文中；不读取真实 `hosts`。

## 阶段 3：任务、API 与前端

**文件：** `webui/app.py`、`webui/api.py`、`webui/jobs.py`、`webui/tools.py`、`webui/agent.py`、`webui/static/index.html`、`webui/static/app.css`、`webui/static/app.js`、`tests/test_webui_api.py`。

1. 任务创建先持久化 `queued`，后台单工作线程决定模型工具调用并执行远程操作；单条消息最多一次远程工具调用。逐台记录连接、巡检、成功/失败及报告 ID；任务状态 `queued -> running -> succeeded|partial|failed`，重启标记未完成任务为 `interrupted`，不自动重放；模型总结失败保留结构化结果。
2. API：`POST /api/login`、`POST /api/logout`、`GET/POST /api/hosts`、`PATCH /api/hosts/{id}`、`GET/POST /api/ssh-keys`、`GET/PATCH /api/settings`、`POST /api/chat`、`GET /api/conversations`、`GET /api/jobs`、`GET /api/jobs/{id}`、`GET /api/jobs/{id}/events`、`GET /api/reports`、`GET /api/reports/{id}`。无 `/api/hosts/import`，所有业务 API 要求登录；报告仅用服务端 ID 索引受限路径，不接受任意文件路径。SSE 重连先给持久化状态快照再推新事件，断线不取消任务。
3. 使用 requests 调用已确认支持 `tools`/`tool_choice` 的 OpenAI-compatible 服务；严格验证工具名、字段及取值，`latest_inspection` 不建 SSH，拒绝任意命令与模型提供的临时主机。模型调用有超时、上下文长度上限；发送模型的摘要只由预定义的风险类别、级别、数量和报告 ID 组成，绝不转发远端告警原句、原始日志或凭据。用包含测试秘密和指令的远端输出验证模型上下文没有原文且不会触发第二次工具调用。
4. 原生前端首屏是工作台，侧栏可达会话、任务、报告、主机及设置；手动登记和停用资产、选择密钥或填密码、实时逐主机状态、风险摘要与纯文本报告均有操作入口。桌面/移动布局、键盘焦点和状态播报验收，不以未清洗 HTML 呈现远端报告。
5. 用临时数据库、模拟模型和假 SSH 验证“登记 -> 巡检 -> 部分失败 -> SSE 断线恢复 -> 报告”，并验证非法模型响应绝不触发 SSH。

## 阶段 4：wheel-only 安装与交付

**文件：** `pyproject.toml`、`scripts/install_webui.sh`、`README.md`、`config/webui/AGENTS.md`、`config/webui/CLAUDE.md`、`.gitignore`、`tests/test_webui_packaging.py`。

1. 构建环境重设 `pyproject.toml` 的 wheel 文件选择，明确包含已有 `cli:main` 对应的顶层 `cli.py`、`webui`、共用 `server_check`/`utils`、静态资源及 `config/webui/` 规则模板，并连同安装脚本作为交付包；目标机只接收交付包，不要求源码仓库。安装脚本先验证 Linux/systemd 和 Python 3.14（含 venv/pip），再创建 `/opt/autodeploykit`（可改绝对路径）及仓库外数据/配置目录、服务账号，建立独立 `.venv`，从 wheel 的 `web` 可选依赖非 editable 安装并验证静态资源可读取。依赖包须可从管理员配置的包索引或本地 wheel 缓存取得，不可取得时明确失败，不擅自修改系统 Python；不使用 `pip -e .`，不自动删除已有源码目录，旧源码由部署者在安装验收后自行处理。
2. 将 WebUI 专用 `AGENTS.md`、`CLAUDE.md` 安装到安装目录；文件权限和服务账号访问遵循最小权限。systemd 的 `WorkingDirectory` 指向安装目录，服务账号仅能读取代码、根密钥，写数据库/报告/日志到数据目录；服务固定 `127.0.0.1`、一个 worker。首次安装先完成根密钥与管理员口令初始化，再启动服务；升级不覆盖配置/密钥/数据库，修改已有服务前展示差异并确认。反向代理 HTTPS 由管理员配置，不在脚本内创建。
3. 验证只用交付包在无源码目录的 Linux 环境安装，运行时代码目录只读，资产和报告仍可用；验证重复安装、已有库无密钥、已有库密钥被替换均拒绝启动，普通用户不能读代码/密钥或数据库。验收 wheel 中 `cli:main` 可导入、静态文件和已安装规则文件均存在；不能把这些规则文件当作后端校验的替代物。
4. README 明确当前 CLI 仍按原方法使用；WebUI 尚未实现前不宣称其可运行。实现时补充安装、升级、备份、恢复、HTTPS 和 SSH 身份风险说明。开源社区版与商业版的分发架构在出现具体差异时另行设计，第一版不引入无实现的产品开关。

## 正式执行前与验收

- 第一阶段须先修订仓库规则与 WebUI 已安装规则：源码工作区仍受 `hosts`/CLI 规则约束；**已经安装的 WebUI** 只能用数据库资产并写数据目录。现有源码仓库规则修改前，不得以 WebUI 名义连接远程服务器；所有 SSH 命令分级和禁止类操作持续有效。
- `.gitignore` 必须允许 `tests/test_webui_*.py` 被跟踪，且测试只使用假主机配置。WebUI 使用 Python 3.14 的安装验收；CLI 使用 Python 3.9 的元数据解析与旧功能回归验收。可运行验证命令：`.venv/bin/python -m unittest discover -s tests -p 'test_webui_*.py'`（Windows 开发环境改用 `.venv\Scripts\python.exe`）、`bash -n scripts/install_webui.sh`，预期均通过；打包产物需在无源码目录测试。
- 不运行真实服务器 SSH 作为本计划的自检。实施完成后正式远程验收须单独符合当前有效的目标资产、凭据和 SSH 权限规则；若服务端已安装还应检查报告、风险项及建议，不提交任何真实服务器信息。
