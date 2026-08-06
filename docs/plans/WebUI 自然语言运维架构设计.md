# AutoDeployKit WebUI 自然语言运维架构设计

- 状态：拟定
- 日期：2026-08-06
- 首期用户：内网单用户
- 首期范围：服务器巡检与查看类操作
- 模型接口：OpenAI-compatible API

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
3. 后端只允许选择 `hosts` 中已配置的主机或主机组。
4. 浏览器可实时查看连接、巡检和报告生成进度。
5. 巡检报告继续保存到 `server_check/reporters`，并可在页面查看。
6. 保存会话、任务、工具调用和结果状态，形成最小审计记录。
7. 保持现有 CLI 可用，WebUI 与 CLI 复用相同的主机解析和巡检服务。

### 2.2 非目标

- 首期不开放安装、配置、reload 或 restart 操作。
- 首期不支持移动、删除、停止或关闭类操作。
- 不提供“执行任意命令”工具。
- 不一次性参数化所有现有交互菜单。
- 不实现多用户、RBAC、多租户或公网 SaaS。
- 不引入微服务、Redis、Celery、工作流引擎、MCP 或插件系统。
- 不引入 React、Vue 等前端构建链。

## 3. 非功能要求

### 3.1 安全

- 默认只允许内网访问，生产部署建议经反向代理提供 HTTPS。
- 使用环境变量配置的单用户访问口令，不在仓库保存口令或模型密钥。
- SSH 密码、私钥路径和代理凭据不得返回浏览器或发送给模型。
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
│  Chat UI · Task progress · Report viewer                  │
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
│          Host Registry             Report Store            │
│                │                   │                      │
│             Paramiko       server_check/reporters          │
│                │                                          │
│          Target Linux Servers                             │
│                                                           │
│  SQLite: conversations · messages · jobs                  │
└───────────────────────────────────────────────────────────┘
```

首期采用单体、单进程部署。Web API、模型控制器、任务执行器和 SQLite 位于同一 Python
进程内，避免为单用户场景引入分布式组件。

## 5. 组件设计

### 5.1 浏览器界面

首屏直接呈现可用的聊天工作台，不制作营销页。页面包含：

- 左侧：历史会话列表。
- 中间：对话消息、工具调用摘要和错误信息。
- 底部：自然语言输入框与发送按钮。
- 任务区域：固定高度的进度列表，显示主机级状态，避免内容变化导致布局跳动。
- 报告区域：风险摘要和 Markdown 原文入口。

前端使用原生 HTML、CSS 和 JavaScript。用户消息通过 `POST /api/chat` 提交，任务进度
通过 SSE 接收。首期不需要 WebSocket，因为浏览器到服务端只有普通请求，只有任务进度
需要服务端单向推送。

### 5.2 Web API

建议使用 FastAPI 和 Uvicorn。FastAPI 提供请求模型、参数校验、OpenAPI 和流式响应，适合
定义严格的工具参数边界。该选择会新增 `fastapi`、`uvicorn` 依赖，实施前需明确确认。

首期 API：

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/login` | 校验单用户访问口令并建立会话 |
| `GET` | `/api/hosts` | 返回可选主机组及脱敏主机标识 |
| `POST` | `/api/chat` | 保存用户消息并启动模型决策 |
| `GET` | `/api/jobs/{job_id}` | 查询任务当前状态 |
| `GET` | `/api/jobs/{job_id}/events` | 通过 SSE 接收任务事件 |
| `GET` | `/api/reports/{report_id}` | 读取允许目录内的巡检报告 |

所有 `/api/*` 路由除登录外都必须校验服务端会话。Cookie 使用 `HttpOnly`、`SameSite=Lax`，
在 HTTPS 下启用 `Secure`。

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

环境变量：

```text
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
WEBUI_PASSWORD
WEBUI_SESSION_SECRET
```

### 5.4 工具注册表与策略门

工具注册表是模型与运维实现之间的唯一入口。每个工具至少包含：

```json
{
  "name": "inspect_servers",
  "description": "巡检 hosts 中已配置的服务器并生成报告",
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

- `host_pattern`：必须能由 `hosts` 唯一解析；支持组名、已登记 IP、逗号分隔 IP 或 `all`。
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

本地只读工具。按已登记主机或主机组读取 `server_check/reporters` 下最近一次报告，不建立
SSH 连接。它只返回报告标识、生成时间和风险摘要，不接受任意文件路径。

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

使用标准库 `sqlite3` 保存元数据，报告继续使用文件系统。

最小数据表：

```text
conversations(id, title, created_at, updated_at)
messages(id, conversation_id, role, content, created_at)
jobs(id, conversation_id, tool_name, status, arguments_json,
     result_json, error, created_at, started_at, finished_at)
```

首期无需单独的 `tool_calls` 表；工具名、参数和结果已包含在 `jobs`。只有出现一条消息调用
多个工具或复杂审批历史时再拆表。

## 6. 现有代码改造边界

### 6.1 主机解析与 SSH 生命周期

从 `cli.py` 提取可复用函数，但不改变 `hosts` 格式：

- 主机解析失败时抛出明确异常，不在共享函数中 `sys.exit()`。
- CLI 捕获异常后打印并退出；Web API 捕获异常后返回 4xx。
- WebUI 只接受 `hosts` 中已存在的目标，禁止用户提交临时 IP、用户名或密码。
- 连接始终从工作区 `hosts` 读取 SSH 配置。

SSH 连接建议由一个上下文管理器统一关闭目标连接和代理连接。首期不做连接池，避免长时间
持有高权限连接。

### 6.2 `server_check`

将巡检核心调整为可编程调用：

- `inspect_server()` 显式接收 `group`，不从 `sys.argv` 读取。
- 返回主机状态、alerts 和报告路径，不只写文件或打印。
- `run()` 保持 CLI 包装职责，继续选择默认报告目录并显示控制台信息。
- 报告根目录固定为 `server_check/reporters`；Web 请求不能覆盖根目录。

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
hosts 配置       -> 服务端受控，但不得外泄
工具注册表       -> 唯一可信执行入口
```

### 7.2 命令与参数安全

- 不提供任意命令工具。
- `host_pattern` 必须通过主机注册表解析。
- `checks` 必须来自固定枚举。
- 后续服务名、端口等参数必须有格式和范围校验，并在组成固定命令时使用 `shlex.quote()`。
- 策略门在模型调用之后、SSH 连接之前执行。
- 项目禁止的移动、删除、停止和关闭类操作不得通过提示词、管理员开关或模型参数绕过。

### 7.3 SSH 主机身份

当前 `utils/ssh_utils.py` 使用 `AutoAddPolicy()` 自动接受未知主机密钥。WebUI 长期运行会放大
中间人攻击风险。实施时应支持加载项目外的 known-hosts 文件，并在生产环境默认拒绝未知或
变化的主机密钥。known-hosts 可能包含真实服务器信息，不得加入 Git。

### 7.4 Prompt Injection 与数据泄露

- 远程日志或报告只作为标记明确的工具结果传给模型。
- 工具结果中的文字不能新增工具、修改系统规则或直接触发第二次执行。
- 首期每条消息最多一次远程工具调用。
- 发送模型前删除 ANSI 控制字符，限制单主机输出和总上下文长度。
- 不向模型发送 `hosts` 原文、SSH 密码、私钥路径、代理凭据或本地环境变量。

### 7.5 Web 安全

- 使用恒定时间比较校验访问口令。
- 登录和聊天接口做简单的进程内限流。
- 设置 CSP、`X-Content-Type-Options`、`Referrer-Policy` 和 frame 限制。
- 报告正文作为文本或经过安全 Markdown 渲染，禁止直接注入未清洗 HTML。
- 生产环境关闭调试模式和异常堆栈响应。

## 8. 错误处理

| 场景 | 行为 |
|---|---|
| `hosts` 不存在或无法读取 | 拒绝任务，明确提示路径问题 |
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
        -> SQLite
        -> server_check/reporters
        -> hosts and external known-hosts
        -> OpenAI-compatible API
        -> SSH target servers
```

要求：

- 从项目 `.venv` 启动应用。
- `hosts`、known-hosts、`.env` 和 SQLite 数据库保留在服务器本地，不加入 Git。
- Web 进程使用专用本地账号运行，只授予读取 `hosts`、写入报告和数据库所需权限。
- 反向代理只开放给内网网段；若直接监听，至少限制防火墙来源地址。
- 首期只运行一个 Uvicorn worker，保证内存队列和单任务锁语义一致。

## 10. 测试策略

### 10.1 最小单元测试

- 主机组、单 IP、多 IP、`all` 和不存在主机的解析。
- 工具拒绝未知字段、未知巡检项和未登记主机。
- 策略门允许 `read`、拒绝未开放和 `prohibited` 工具。
- 报告 ID 无法越过 `server_check/reporters`。
- 非法模型响应不会创建任务。

### 10.2 集成测试

- 使用假的 SSH client 运行一次巡检，断言生成结构化结果和报告。
- 使用 mock OpenAI-compatible 响应完成“消息 -> 工具 -> 任务 -> 总结”闭环。
- 验证部分主机失败时任务状态为 `partial`。
- 验证 SSE 事件顺序和断线重连后的状态读取。

测试不得连接真实服务器，也不得读取真实 `hosts`；使用临时主机配置和假的 SSH client。

## 11. 分阶段实施

### 阶段 1：可编程巡检核心

1. 提取无 `sys.exit()` 的主机解析函数。
2. 让 `server_check` 接收显式参数并返回结构化结果。
3. 保持现有 CLI 行为兼容。
4. 添加主机解析和巡检结果的最小测试。

### 阶段 2：无模型 Web 闭环

1. 添加 FastAPI、Uvicorn 和原生聊天页面。
2. 添加 SQLite、单任务执行器和 SSE。
3. 使用固定 mock 工具调用验证巡检和报告查看。

### 阶段 3：模型接入

1. 使用 `requests` 接 OpenAI-compatible tool calling。
2. 实现工具 schema 校验、调用次数上限和结果脱敏。
3. 增加模型超时、非法响应和 Prompt Injection 测试。

### 阶段 4：部署加固

1. 添加单用户登录、限流和安全响应头。
2. 配置外部 known-hosts、HTTPS 和内网访问限制。
3. 验证日志、错误响应和报告中不泄露凭据。

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

- 决策：SQLite 保存会话和任务，Markdown 报告沿用现有目录。
- 原因：标准库即可满足单用户场景，避免重复存储报告正文。
- 替代方案：PostgreSQL、Redis。当前没有并发和可用性需求支撑额外组件。
- 后果：多实例部署前需要重新评估数据库和事件队列。

## 13. 首期验收标准

1. 用户登录后可输入“巡检 webservers”。
2. 模型只能产生 `inspect_servers` 或 `latest_inspection` 调用。
3. 未登记主机、未知工具和任意命令请求均不会建立 SSH 连接。
4. 页面实时显示每台主机的连接和完成状态。
5. 成功主机在 `server_check/reporters` 下生成 Markdown 报告。
6. 页面展示风险摘要并可读取报告，且无法访问报告目录外文件。
7. 单台主机失败时其他主机仍完成，任务显示 `partial`。
8. 会话、任务参数、状态和时间可从 SQLite 追溯，记录中不含凭据。
9. 现有 `python cli.py server_check <host_pattern>` 行为保持可用。

## 14. 实施前待确认

- OpenAI-compatible 服务是否完整支持 `tools` 和 `tool_choice` 字段。
- WebUI 的实际部署操作系统、监听地址和反向代理方式。
- 生产环境 known-hosts 文件位置和维护方式。
- 是否接受新增 `fastapi`、`uvicorn` 两项依赖。
