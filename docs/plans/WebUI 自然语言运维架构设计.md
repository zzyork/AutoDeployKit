# AutoDeployKit WebUI 自然语言运维架构设计

- 状态：拟定
- 日期：2026-08-06
- 更新：2026-09-28
- 首期用户：内网单用户
- 首期范围：WebUI 资产与 SSH 登录密钥管理、AI 服务器巡检与查看类操作
- 模型接口：OpenAI-compatible API

以下为设计目标，尚未实现；CLI 在过渡期继续独立读取 `hosts`，最终计划移除。

## 1. 背景

AutoDeployKit 当前是交互式 Python CLI，通过 `hosts` 读取目标服务器配置，使用
Paramiko 建立 SSH 连接，再进入各模块的终端菜单执行操作。

当前入口和业务代码具有以下特点：

- `cli.py` 同时负责参数解析、主机解析、SSH 生命周期和模块加载。
- 各模块通过 `run(clients)` 和 `utils/menu_runner.py` 进入交互菜单。
- 业务函数大量使用 `input()`、`getpass()` 和 `print()` 收集参数及输出结果。
- `server_check` 已具备并发巡检、风险摘要和 Markdown 报告能力，是最适合作为首期
  WebUI 工具的模块。
- 项目对 SSH 操作有明确分级：查看类可直接执行；修改/重启类必须确认；移动、删除、
  停止、关闭类禁止执行。

WebUI 不应模拟终端菜单，也不应把模型生成的 shell 命令直接交给 SSH 执行。正确边界是
让模型从后端预注册的结构化工具中选择动作，由后端独立完成参数校验、策略判断和执行。

## 2. 目标与非目标

### 2.1 目标

1. 用户可在浏览器中通过中文自然语言发起服务器巡检。
2. 模型将意图转换为结构化工具调用，不生成或执行任意 shell。
3. 用户在 WebUI 中管理服务器清单；后端只允许选择数据库中已登记、启用的主机或主机组。
4. 浏览器可实时查看连接、巡检和报告生成进度。
5. 巡检报告继续保存到 `server_check/reporters`，并可在页面查看。
6. 保存会话、任务、工具调用和结果状态，形成最小审计记录。
7. WebUI 可生成多组 SSH 登录密钥对，配置主机账号时选择密钥；用户自行将公钥配置到远端。
8. 模型和主机等日常配置通过 WebUI 管理并持久化到数据库。
9. 过渡期保持 CLI 读取 `hosts`，WebUI 读取数据库；两者不做同步，巡检核心仍复用。

### 2.2 非目标

- 首期不开放安装、配置、reload 或 restart 操作。
- 首期不支持移动、删除、停止或关闭类操作。
- 不提供“执行任意命令”工具。
- 不一次性参数化所有现有交互菜单。
- 不实现多用户、RBAC、多租户或公网 SaaS。
- 不引入微服务、Redis、Celery、工作流引擎、MCP 或插件系统。
- 不引入 React、Vue 等前端构建链。
- 不提供浏览器 SSH 终端、任意命令、会话录像或完整堡垒机权限体系。
- 不自动修改远程账号的 `authorized_keys`，不检查用户是否已安装登录公钥。

## 3. 非功能要求

### 3.1 安全

- 默认只允许内网访问，生产部署建议经反向代理提供 HTTPS。
- 单用户口令在 WebUI 设置，数据库仅保存加盐的慢哈希；模型 API key 与 SSH 登录私钥
  加密存入数据库，加密根密钥不得与数据库同存或加入仓库。
- SSH 私钥、密码和代理凭据不得返回浏览器或发送给模型；页面只提供公钥展示与导出。
- 模型工具调用、浏览器输入和远程输出均视为不可信数据。
- 所有工具参数在执行前进行服务端校验；模型提示词不能代替策略校验。
- 报告下载必须限定在 `server_check/reporters` 根目录内，阻止路径穿越。
- 日志和 API 错误不得包含 SSH 凭据、模型密钥或完整异常堆栈。

### 3.2 性能与并发

- 首期只允许一个远程任务运行，其余任务排队。
- 单个巡检任务内部继续使用 `server_check` 现有主机并发，默认最多 5 个线程。
- 聊天接口应在创建任务后快速返回，长任务通过 SSE 推送进度。
- 模型上下文只包含必要的风险摘要和受限长度的输出，不发送完整大日志。

### 3.3 可靠性

- 每台主机独立记录成功或失败；部分主机失败不应丢弃其他主机结果。
- 服务重启后，将未结束任务标记为 `interrupted`，不自动重放 SSH 操作。
- 报告文件写入沿用现有先写正文再合并的方式，最终结果返回明确路径。

## 4. 总体架构

```text
┌───────────────────────────────────────────────────────────┐
│ Browser                                                   │
│  Chat · Tasks · Reports · Assets · Settings               │
└───────────────────────┬───────────────────────────────────┘
                        │ HTTP + SSE
┌───────────────────────▼───────────────────────────────────┐
│ Web Application                                           │
│                                                           │
│  API Routes ── Agent Controller ── OpenAI-compatible API  │
│      │                 │                                  │
│      │          Tool Registry + Policy Gate               │
│      │                 │                                  │
│      └────────── Job Runner + Event Queue                  │
│                        │                                  │
│             Inspection Application Service                │
│                │                   │                      │
│          Asset Registry            Report Store            │
│                │                   │                      │
│          utils/ssh_utils.py  server_check/reporters         │
│                │                                          │
│          Target Linux Servers                             │
│                                                           │
│  SQLite: assets · SSH keys · settings · sessions · jobs    │
└───────────────────────────────────────────────────────────┘
```

首期采用单体、单进程部署。Web API、模型控制器、任务执行器和 SQLite 位于同一 Python
进程内，避免为单用户场景引入分布式组件。

## 5. 组件设计

### 5.1 浏览器界面

首屏直接呈现可用的 AI 聊天工作台，不制作营销页。页面包含：

- 全局侧栏：AI 工作台、任务、报告、主机；设置固定在侧栏底部，仅显示已开放的功能。
- 工作台左侧：历史会话列表。
- 中间：对话消息、工具调用摘要和错误信息。
- 底部：自然语言输入框与发送按钮。
- 工作台右侧：运行时固定高度的逐主机进度，结束后显示风险摘要与报告入口。
- 任务、报告有独立可定位的列表与详情，按状态、目标和时间筛选；报告先显示风险与
  失败主机，按需展开 Markdown 原文。
- 主机页：分组、标签和搜索；主机详情关联任务、报告、登录账号、跳板机与所选登录密钥。
- 设置页：模型地址、模型名、API key、登录口令及 SSH 登录密钥库。

宽屏显示全局侧栏、会话列表、正文及任务详情；中等宽度将会话和任务详情改为抽屉，
窄屏使用单列切换。浅色中性底配青绿操作色、琥珀警告和红色失败，状态同时使用文字；
使用紧凑表格、可见键盘焦点和状态播报，避免功能增长后堆叠卡片或不断扩展顶栏。

前端使用原生 HTML、CSS 和 JavaScript。用户消息通过 `POST /api/chat` 提交，任务进度
通过 SSE 接收。首期不需要 WebSocket，因为浏览器到服务端只有普通请求，只有任务进度
需要服务端单向推送。

### 5.2 Web API

使用 FastAPI 和 Uvicorn。FastAPI 提供请求模型、参数校验、OpenAPI 和流式响应，适合
定义严格的工具参数边界；新增 `fastapi`、`uvicorn` 两项依赖已确认。

首期 API：

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/login` | 校验单用户访问口令并建立会话 |
| `GET/POST` | `/api/hosts` | 查询和登记数据库中的服务器资产 |
| `PATCH` | `/api/hosts/{host_id}` | 编辑或停用资产，保留历史记录 |
| `POST` | `/api/ssh-keys` | 在服务端生成 SSH 登录密钥对，保存加密私钥 |
| `GET` | `/api/ssh-keys` | 列出密钥名称与公钥，绝不返回私钥 |
| `GET/PATCH` | `/api/settings` | 查询和更新模型及单用户配置，不回显 API key |
| `POST` | `/api/chat` | 保存用户消息并启动模型决策 |
| `GET` | `/api/jobs/{job_id}` | 查询任务当前状态 |
| `GET` | `/api/jobs/{job_id}/events` | 通过 SSE 接收任务事件 |
| `GET` | `/api/reports/{report_id}` | 读取允许目录内的巡检报告 |

首次设置管理员口令必须限制为受控初始化入口，不开放任意访问者抢先注册。所有 `/api/*`
路由除登录及受控初始化外都校验服务端会话；敏感配置更新需重新验证身份，写接口防 CSRF。
Cookie 使用 `HttpOnly`、`SameSite=Lax`，在 HTTPS 下启用 `Secure`。

### 5.3 Agent Controller

Agent Controller 负责一次用户消息的有限状态流转：

1. 读取最近对话和允许使用的工具 schema。
2. 调用 OpenAI-compatible `/v1/chat/completions` tool calling 接口。
3. 拒绝未知工具、缺失参数或非法参数。
4. 对合法调用创建后台任务。
5. 任务完成后，将结构化结果作为 `tool` 消息发送给模型生成总结。
6. 保存最终回复并推送给浏览器。

首期每条用户消息最多触发一个远程工具调用。该限制可防止模型循环调用，并足以覆盖
“巡检某组服务器并总结风险”的首期场景。模型接口直接复用项目已有 `requests`，不增加
厂商 SDK。

模型地址、模型名和 API key 在 WebUI 设置后存入数据库；API key 只存密文，不在响应、日志
或模型上下文中回显。单用户口令只存哈希；采用服务端数据库会话与随机令牌，不要求手工配置
`WEBUI_SESSION_SECRET`。加密根密钥是唯一不能与密文同存的启动材料，详见 5.7 和第 9 节。

### 5.4 工具注册表与策略门

工具注册表是模型与运维实现之间的唯一入口。每个工具至少包含：

```json
{
  "name": "inspect_servers",
  "description": "巡检 WebUI 中已登记并启用的服务器并生成报告",
  "risk": "read",
  "input_schema": {
    "type": "object",
    "properties": {
      "host_pattern": {"type": "string"},
      "checks": {
        "type": "array",
        "items": {"type": "string"}
      }
    },
    "required": ["host_pattern"],
    "additionalProperties": false
  }
}
```

策略门不依赖模型判断风险，按后端元数据执行固定规则：

| 风险级别 | 行为 | 首期状态 |
|---|---|---|
| `read` | 参数校验通过后自动执行 | 开放 |
| `modify` | 展示完整动作并等待明确确认 | 不开放 |
| `restart` | 展示完整动作并等待明确确认 | 不开放 |
| `prohibited` | 始终拒绝 | 永久生效 |

禁止把通用 shell 命令作为工具参数。新增只读工具时应优先复用现有巡检 handler 或使用
后端固定命令，用户只能传递经过校验的主机、服务名等数据字段。

### 5.5 首期工具

#### `inspect_servers`

远程只读工具。参数：

- `host_pattern`：仅从数据库中唯一解析已启用的主机标识、组名、已登记地址或 `all`；
  拒绝聊天或模型给出的临时地址、重复标识及歧义匹配。
- `checks`：可选，只允许 `server_check.CHECK_HANDLERS` 已注册的名称。

返回：

```json
{
  "status": "succeeded|partial|failed",
  "hosts": [
    {
      "host": "脱敏或已登记标识",
      "status": "succeeded|failed",
      "alerts": [],
      "report_id": "...",
      "error": null
    }
  ]
}
```

#### `latest_inspection`

本地只读工具。按已登记主机或主机组读取 WebUI 任务索引的最近一次报告，不建立 SSH
连接。它只返回报告标识、生成时间和风险摘要，不接受任意文件路径；CLI 旧报告暂不索引。

### 5.6 任务执行与事件

任务执行器使用标准库线程和内存队列，不引入 Celery。任务状态：

```text
queued -> running -> succeeded
                  -> partial
                  -> failed
                  -> interrupted
```

SSE 事件保持少而稳定：

```text
job.queued
job.started
host.connecting
host.inspecting
host.succeeded
host.failed
job.completed
assistant.message
```

事件中不发送 SSH 凭据、完整异常堆栈或未限制长度的远程输出。浏览器断开 SSE 不取消后台
任务；重新连接后先读取数据库状态，再接收后续事件。

### 5.7 数据存储

使用标准库 `sqlite3` 保存 WebUI 资产、登录密钥、配置、会话和任务；报告继续使用文件系统。
WebUI 数据库与 CLI 的 `hosts` 相互独立，不做同步；真实地址与密钥数据仅保存在本地数据库，
不得提交 Git。主机停用保留历史任务和报告，不自动删除记录。

最小数据表：

```text
conversations(id, title, created_at, updated_at)
messages(id, conversation_id, role, content, created_at)
jobs(id, conversation_id, tool_name, status, arguments_json,
      result_json, error, created_at, started_at, finished_at)
hosts(id, name, address, port, group_name, tags_json, username,
      ssh_key_id, proxy_host_id, enabled, created_at, updated_at)
ssh_keys(id, name, public_key, private_key_ciphertext, created_at)
settings(key, value_or_ciphertext)
admin_auth(password_hash)
sessions(token_hash, expires_at)
```

首期无需单独的 `tool_calls` 表；工具名、参数和结果已包含在 `jobs`。只有出现一条消息调用
多个工具或复杂审批历史时再拆表。首期每台主机配置一个登录账号及所选密钥；只有实际出现
一台主机多账号需求时再拆出账号表。服务端生成多组密钥对，公钥可复制或下载，由用户自行
加入远程账号的 `authorized_keys`；私钥加密入库、仅在后端 SSH 认证时使用。没有配置好
远端公钥时按普通认证失败处理，不增加预检查或确认流程。密钥可被多台主机选用；跳板机
也按资产关联并使用其自身的账号配置。

`jobs.result_json` 按资产 ID 记录每台主机的报告 ID、受限相对路径及生成时间；报告列表
和 `latest_inspection` 只索引 WebUI 任务生成的报告，不扫描任意路径。报告 ID 到文件路径
的映射仅在服务端完成，读取时仍检查路径在固定报告根目录内。

模型 API key 等可逆秘密只存密文，登录口令只存加盐的慢哈希。加密根密钥不得存在同一个
SQLite 文件中；建议首启自动生成并保存在仓库与数据库外、仅服务账号可读的位置，备份时
与数据库分开保护。根密钥托管和首次管理员初始化的具体方式实施前仍需确定。数据库会话
使用随机令牌，数据库只存令牌哈希，避免额外的手工会话密钥配置。

## 6. 现有代码改造边界

### 6.1 主机来源与 SSH 生命周期

过渡期保持两个独立入口，不改 CLI 的 `hosts` 格式，也不维护双向同步：

- CLI 只读取 `hosts`，未来移除 CLI；WebUI 只读取数据库中的资产及加密登录凭据。
- CLI 保持原有主机解析；WebUI 独立校验资产标识唯一性、端口范围、分组与跳板机引用。
- WebUI 可登记主机，但 AI 工具只能选择已启用资产，不接受临时地址或认证信息。
- WebUI 与 CLI 复用 `server_check` 的巡检逻辑及 `utils/ssh_utils.py` 的 SSH 连接实现，
  不通过 CLI 子进程或模拟 stdin 执行。共享连接入口需要接受内存中的解密私钥对象，
  同时保留 CLI 的 `key_file` 接口；不得把明文私钥写入临时文件，跳板机同样适用。

当前 `AGENTS.md`、`CLAUDE.md` 与 `README.md` 仍要求远程 SSH 操作从 `hosts` 读取，
和 WebUI 数据库资产设计冲突。实施 WebUI 数据库 SSH 连接前，必须同步修订这些项目说明，
明确 CLI 走 `hosts`、WebUI 走数据库；规则未修订前不得按数据库配置连接远程主机。

SSH 连接建议由一个上下文管理器统一关闭目标连接和代理连接。首期不做连接池，避免长时间
持有高权限连接。

### 6.2 `server_check`

将巡检核心调整为可编程调用：

- `inspect_server()` 显式接收 `group`，不从 `sys.argv` 读取。
- 返回主机状态、alerts 和报告路径，不只写文件或打印。
- `run()` 保持 CLI 包装职责，继续选择默认报告目录并显示控制台信息。
- 报告根目录固定为 `server_check/reporters`；Web 请求不能覆盖根目录。组名及远端返回的
  hostname 都不能未经约束就用作目录或文件名；Web 报告以受限的资产标识生成路径，并在
  写入前校验解析后的路径仍位于报告根目录内，CLI 原有命名行为保持不变。

首期不全面替换 `utils/output.py`。Web 任务只推送主机级事件，现有详细控制台输出继续供
CLI 和服务日志使用。需要逐步骤展示内部巡检进度时，再把输出回调作为显式参数加入。

### 6.3 现有交互式管理模块

`server_ops`、`middleware_ops`、`software_ops` 和 `monitor_ops` 首期保持不变。后续开放某个
修改类操作时，应把该操作的参数收集和执行逻辑分离：Web 调用显式参数函数，CLI 菜单负责
调用 `input()` 后再传参。禁止通过模拟 stdin 驱动旧菜单。

## 7. 安全设计

### 7.1 信任边界

```text
浏览器输入       -> 不可信
模型工具调用     -> 不可信
目标服务器输出   -> 不可信
数据库资产及密钥 -> 服务端受控，但不得外泄凭据
工具注册表       -> 唯一可信执行入口
```

### 7.2 命令与参数安全

- 不提供任意命令工具。
- `host_pattern` 必须通过 WebUI 数据库中已启用的资产解析。
- `checks` 必须来自固定枚举。
- 后续服务名、端口等参数必须有格式和范围校验，并在组成固定命令时使用 `shlex.quote()`。
- 策略门在模型调用之后、SSH 连接之前执行。
- 项目禁止的移动、删除、停止和关闭类操作不得通过提示词、管理员开关或模型参数绕过。

### 7.3 SSH 主机身份

这里区分两种密钥：WebUI 生成的是客户端用于登录远程账号的密钥对，私钥在 WebUI 本地，
公钥由用户自行安装到远程账号；SSH 服务器用于证明自身身份的主机密钥是另一回事。
首期不增加主机指纹人工核对、远端登录公钥安装检查或相关确认界面。

当前 `utils/ssh_utils.py` 对目标和跳板机都使用 `AutoAddPolicy()` 接受未知主机密钥，
且未持久化可信主机密钥；在该行为下首次连接不能证明服务器身份，存在中间人攻击风险。
此前的“生产环境默认拒绝未知主机密钥、维护外部 known-hosts”提案不再作为本期交互或
部署前置条件。此处不把登录密钥对误称为主机身份校验，也不宣称当前连接已具备该保护。

### 7.4 Prompt Injection 与数据泄露

- 远程日志或报告只作为标记明确的工具结果传给模型。
- 工具结果中的文字不能新增工具、修改系统规则或直接触发第二次执行。
- 首期每条消息最多一次远程工具调用。
- 发送模型前删除 ANSI 控制字符，限制单主机输出和总上下文长度。
- 不向模型发送资产连接详情、SSH 私钥、模型 API key、代理凭据或本地环境变量。

### 7.5 Web 安全

- 使用恒定时间比较校验访问口令。
- 登录和聊天接口做简单的进程内限流。
- 敏感配置更新使用受保护的会话、CSRF 防护及再次验证；密钥和 API key 不进入任务记录。
- 设置 CSP、`X-Content-Type-Options`、`Referrer-Policy` 和 frame 限制。
- 报告正文作为文本或经过安全 Markdown 渲染，禁止直接注入未清洗 HTML。
- 生产环境关闭调试模式和异常堆栈响应。

## 8. 错误处理

| 场景 | 行为 |
|---|---|
| WebUI 资产未登记或已停用 | 拒绝任务，不尝试 SSH |
| SSH 密钥缺失、解密失败或认证失败 | 记录连接失败，不自动修改远程配置 |
| 主机模式无匹配 | 返回参数错误，不调用模型重试执行 |
| 多个近似主机无法唯一确定 | 拒绝任务，要求用户明确选择 |
| 单台 SSH 连接失败 | 记录该主机失败，继续其他主机 |
| 所有 SSH 连接失败 | 任务标记 `failed` |
| 部分巡检失败 | 任务标记 `partial`，保留成功报告 |
| 模型超时或返回非法工具调用 | 不执行工具，返回可理解错误 |
| 浏览器断开 | 后台任务继续，结果可重新读取 |
| 服务进程重启 | 未完成任务标记 `interrupted`，不自动重试 |

## 9. 部署

首期推荐部署为一个进程：

```text
Reverse Proxy (TLS, access restriction)
    -> Uvicorn / FastAPI
        -> SQLite (assets, encrypted secrets, conversations, jobs)
        -> encryption root key (outside SQLite and Git)
        -> server_check/reporters
        -> OpenAI-compatible API
        -> SSH target servers
```

要求：

- 从项目 `.venv` 启动应用。
- SQLite 数据库及加密根密钥只留在服务器本地，不加入 Git；CLI 的 `hosts` 继续独立使用。
- Web 进程使用专用本地账号运行，只授予数据库、根密钥和报告所需的最小权限。
- 反向代理只开放给内网网段；若直接监听，至少限制防火墙来源地址。
- 首期只运行一个 Uvicorn worker，保证内存队列和单任务锁语义一致。

## 10. 测试策略

### 10.1 最小单元测试

- 数据库资产的组、已登记地址、`all`、停用资产及歧义目标解析。
- 生成密钥对后公钥可用、私钥仅以密文入库；密钥解密失败时不建立 SSH 连接。
- 设置接口不回显 API key、SSH 私钥，报告与模型上下文均不包含这些数据。
- 工具拒绝未知字段、未知巡检项和未登记主机。
- 策略门允许 `read`、拒绝未开放和 `prohibited` 工具。
- 报告 ID 无法越过 `server_check/reporters`。
- 报告写入路径不会因资产分组或远端 hostname 越过固定报告根目录。
- 非法模型响应不会创建任务。

### 10.2 集成测试

- 使用假的 SSH client 运行一次数据库资产巡检，断言生成结构化结果和报告。
- WebUI 登记资产、选择生成的密钥以及跳板机时，不调用 CLI 主机解析或连接真实服务器。
- 使用假的 SSH client 验证数据库私钥在内存中传给目标与跳板机，CLI 文件路径接口不变。
- 使用 mock OpenAI-compatible 响应完成“消息 -> 工具 -> 任务 -> 总结”闭环。
- 验证部分主机失败时任务状态为 `partial`。
- 验证 SSE 事件顺序和断线重连后的状态读取。

测试不得连接真实服务器，也不得读取真实 `hosts`；CLI 测试使用临时主机配置，WebUI
测试使用临时数据库和假的 SSH client。

## 11. 分阶段实施

### 阶段 1：可编程巡检核心

1. 让 `server_check` 接收显式主机上下文并返回结构化结果，不依赖 `sys.argv`。
2. 保持 CLI 从 `hosts` 连接和调用巡检的行为不变。
3. 添加 CLI 兼容与巡检结果的最小测试。

### 阶段 2：无模型 Web 闭环

1. 添加 FastAPI、Uvicorn 和原生工作台、主机、任务、报告及设置页面。
2. 添加 SQLite 资产、服务端密钥生成与加密存储、单用户登录和受控首次初始化。
3. 添加单任务执行器和 SSE，以固定 mock 工具调用验证巡检和报告查看。
4. 在首次使用数据库资产建立真实 SSH 连接前，同步修订 `AGENTS.md`、`CLAUDE.md`
   和 `README.md` 中的 `hosts` 来源规则。

### 阶段 3：模型接入

1. 使用 `requests` 接 OpenAI-compatible tool calling。
2. 实现工具 schema 校验、调用次数上限和结果脱敏。
3. 增加模型超时、非法响应和 Prompt Injection 测试。

### 阶段 4：部署加固

1. 配置限流、安全响应头、HTTPS 和内网访问限制。
2. 验证日志、错误响应和报告中不泄露凭据，备份数据库及独立加密根密钥。
3. 核查数据库资产 SSH 已按修订后的项目规则运行，且 CLI 仍独立读取 `hosts`。

## 12. 架构决策记录

### ADR-001：采用单体进程内架构

- 决策：Web API、Agent Controller、任务执行和 SQLite 使用同一 Python 进程。
- 原因：首期为内网单用户，单体能覆盖需求且运维成本最低。
- 替代方案：微服务和消息队列。因没有多用户或横向扩容需求而暂不采用。
- 后果：首期只运行一个 worker；出现多用户和多实例需求时再外置任务队列。

### ADR-002：使用 FastAPI、SSE 和原生前端

- 决策：FastAPI 提供 API，SSE 推送任务事件，原生 HTML/JavaScript 构建页面。
- 原因：严格参数模型和流式响应是核心需求，前端交互规模不足以支撑构建链。
- 替代方案：标准库 HTTP 服务难以稳妥处理认证、校验和流式响应；React/Vue 增加无必要复杂度。
- 后果：新增 FastAPI 和 Uvicorn 两项运行依赖。

### ADR-003：模型只调用后端工具注册表

- 决策：不暴露 shell，不模拟 CLI，不引入通用 Agent 框架或 MCP。
- 原因：工具数量少，直接注册表更容易审计并遵守 SSH 操作分级规则。
- 替代方案：CLI 子进程桥接开发快，但无法稳定处理交互、并发和审批。
- 后果：每个后续开放的旧功能都需要先改为显式参数函数。

### ADR-004：SQLite 保存元数据，文件系统保存报告

- 决策：SQLite 保存资产、登录密钥密文、设置、会话和任务，Markdown 报告沿用现有目录。
- 原因：标准库即可满足单用户场景，避免重复存储报告正文。
- 替代方案：PostgreSQL、Redis。当前没有并发和可用性需求支撑额外组件。
- 后果：必须单独保管加密根密钥；多实例部署前需重新评估数据库和事件队列。

### ADR-005：CLI 与 WebUI 的主机来源分离

- 决策：CLI 继续读 `hosts`，WebUI 使用自己的数据库资产清单，不做同步；未来移除 CLI。
- 原因：允许用户从 WebUI 管理服务器和登录密钥，同时不破坏现有 CLI。
- 后果：实施 WebUI SSH 连接前必须修订 `AGENTS.md`、`CLAUDE.md`、`README.md` 中的
  统一 `hosts` 来源约束。

## 13. 首期验收标准

1. 用户可在 WebUI 登记、分组、停用主机，生成多组登录密钥对并为主机选定密钥；
   用户自行将所选公钥加入远端账号，WebUI 不自动执行远程配置。
2. 用户登录后可输入“巡检 webservers”。
3. 模型只能产生 `inspect_servers` 或 `latest_inspection` 调用。
4. 未登记或停用主机、未知工具和任意命令请求均不会建立 SSH 连接。
5. 页面实时显示每台主机的连接和完成状态。
6. 成功主机在 `server_check/reporters` 下生成 Markdown 报告。
7. 页面展示风险摘要并可读取报告，且无法访问报告目录外文件。
8. 单台主机失败时其他主机仍完成，任务显示 `partial`。
9. 会话与任务可从 SQLite 追溯，记录中不含凭据；API key 与私钥只存密文。
10. 现有 `python cli.py server_check <host_pattern>` 仍从 `hosts` 读取且行为保持可用。

## 14. 实施前待确认

- OpenAI-compatible 服务是否完整支持 `tools` 和 `tool_choice` 字段。
- 已选内网 Linux 单进程部署，经反向代理提供 HTTPS；实施时需确定实际监听地址。
- 加密根密钥的自动生成、独立保管、备份和首次管理员初始化方式需在实施前确定。
- 当前 `AGENTS.md`、`CLAUDE.md` 和 `README.md` 均要求远程 SSH 从 `hosts` 读取，
  需在实现数据库资产 SSH 前同步修订为 CLI 与 WebUI 各自的来源规则。

## 15. 参考依据

- [JumpServer 资产与账号管理](https://docs.jumpserver.org/zh/v4/manual/admin/console/account_management/account_list/)：资产关联登录凭据；登录密钥和服务器主机身份密钥不是同一用途。
- [Grafana 导航调整](https://grafana.com/docs/grafana/latest/whatsnew/whats-new-in-v9-5/)：功能增长时按用途分组、提供侧栏与跨页面定位。
- [NN/g 复杂应用设计指南](https://www.nngroup.com/articles/complex-application-design/)：在保留能力的同时降低界面杂乱，并提供任务记录与上下文详情。
- [CHI 2019 人机 AI 交互指南](https://www.microsoft.com/en-us/research/publication/guidelines-for-human-ai-interaction/)：明确 AI 能力边界，支持解释与纠错。
