---
name: agno-platform-engineer
description: 使用 Agno SDK 3.x 与 AgentOS 设计、实现、迁移、调试、测试和部署生产级 Agent 平台。用户提到 Agno、Ango、AgentOS、Agent、Team、Workflow、Tools、MCP、Skills、Session、State、Memory、Learning、Knowledge/RAG、Guardrails、HITL、REST/SSE、鉴权、RBAC、多用户、多租户、Tracing、Evals、Scheduler、vLLM、本地模型或从 Phidata/旧版 Agno 迁移时使用。
license: Apache-2.0
compatibility: 适用于 Python 3.9+ 与 Agno 3.x；Agno API 变化较快，涉及版本敏感实现时应访问 docs.agno.com/mcp 或当前官方文档核验。
metadata:
  author: OpenAI
  version: "1.0.0"
  language: "zh-CN"
  verified-agno-version: "3.0.5"
  verified-agno-commit: "d829138ae9f28a0dd6967fdfae3c74de11501496"
  verified-date: "2026-09-03"
---

# Agno 平台工程 Skill

把用户口中的 `Ango`、`ango agent` 等上下文相关写法视为 **Agno**，但不要因此打断任务。默认目标不是写一个只能演示的聊天脚本，而是交付可验证、可持久化、可观测、可扩展且边界清楚的 Agent 应用。

## 一、启动时必须完成

1. 判断任务模式：新建、扩展、迁移、排错、代码审查、性能优化、部署或架构设计。
2. 检查项目与 Agno 版本：
   ```bash
   python scripts/inspect_agno_project.py /path/to/project
   ```
   如果脚本不在当前目录，先定位本 Skill 根目录再执行。
3. 阅读与任务直接相关的参考文件，禁止凭旧版记忆混写 API：
   - 版本、升级、旧代码：`references/00-version-and-migration.md`
   - 架构选择：`references/01-architecture-decisions.md`
   - Agent 基础与结构化输出：`references/02-agent-core.md`
   - 云模型、本地模型、vLLM：`references/03-models-and-local-inference.md`
   - 工具、Guardrails、HITL：`references/04-tools-guardrails-hitl.md`
   - Session、State、Memory、Learning：`references/05-sessions-state-memory-learning.md`
   - Knowledge/RAG：`references/06-knowledge-rag.md`
   - Team、Workflow：`references/07-teams-workflows.md`
   - AgentOS、REST、SSE、MCP、接口：`references/08-agentos-api-interfaces.md`
   - JWT、RBAC、多租户：`references/09-security-multitenancy.md`
   - Tracing、Evals、可靠性：`references/10-observability-evals.md`
   - Docker、Postgres、并发、队列、部署：`references/11-deployment-operations.md`
   - AI 伴侣/多 Persona：`references/12-companion-app-blueprint.md`
   - 故障排查：`references/13-troubleshooting.md`
   - 验收清单：`references/14-testing-checklists.md`
4. 版本或参数仍不确定时，优先查询当前官方文档 MCP：`https://docs.agno.com/mcp`。不得用旧博客覆盖当前代码与官方文档。
5. 在修改前写出最小实施方案：所选 primitive、状态边界、数据库、模型、工具权限、用户隔离、验证命令。

## 二、先选对 Primitive

| 需求 | 默认选择 | 不应升级的情况 |
|---|---|---|
| 一个模型可完成，配若干工具/知识/记忆 | `Agent` | 不要为了“看起来高级”拆 Team |
| 需要模型动态委派给多个专长角色 | `Team` | 固定步骤用 Workflow 更稳 |
| 顺序、并行、条件、循环、路由、重试、人工审批必须由代码控制 | `Workflow` | 纯对话不要先画复杂图 |
| 需要 REST/SSE/MCP、会话管理、鉴权、追踪、调度、控制台 | `AgentOS` | 单次本地脚本不必启动服务 |

默认从 **一个 Agent + 明确工具 + DB + 评测** 开始。只有评测证明质量收益高于成本、延迟和故障面时，才升级为 Team 或 Workflow。

## 三、核心边界必须说清

- **Agent**：一次模型驱动执行单元；负责推理、调用工具、使用上下文并产生结果。
- **Team**：由 leader 动态决定调用哪些成员、如何综合；适合专家协作和对抗观点。
- **Workflow**：代码定义执行拓扑；适合确定性流程、并行、分支、循环、审批和可恢复任务。
- **AgentOS**：运行时与服务层；把 Agent/Team/Workflow 暴露为 API，并统一管理会话、记忆、知识、评测、追踪和权限。
- **DB**：统一持久层；当前版本使用 `db=`，不要复活旧 `storage=`/`memory=` 架构。
- **session_id**：一条对话线程或任务线程；相同 ID 才延续该线程历史。
- **user_id**：用户身份；长期记忆和多用户数据边界依赖它。每次运行都必须明确传递或由可信 JWT 注入。
- **session_state**：当前线程的结构化可变状态，例如购物车、进度、开关。
- **Memory**：跨 Session 的用户事实与偏好。
- **Knowledge**：可检索的文档事实；不是用户记忆，也不是实时业务系统。
- **Learning**：从反馈与运行中沉淀的长期改进数据。
- **Context Provider**：运行时拉取实时外部上下文；适合 Slack、Drive、DB、MCP 等变化数据。
- **Skill**：渐进加载的操作知识包；适合流程、规范、脚本和参考资料，不等同于 RAG 文档库。

## 四、生产默认值

除非用户明确给出不同约束，否则采用以下默认值：

1. Python 3.12、`uv`、Agno 3.x；依赖按 extras 精确安装，不安装无关的 `all`。
2. 显式设置稳定的 `id`、`name` 和模型 ID；不依赖会变化的默认模型。
3. 开发用 SQLite；生产、多副本、多用户用 PostgreSQL。
4. 在模块级创建并复用 Agent/Team/Workflow/DB/Knowledge/Toolkit；禁止在请求循环或用户循环中反复实例化。
5. 服务端优先 `arun()`；聊天 UI 用流式响应；机器消费结果用 `output_schema`。
6. 每次请求使用稳定的 `user_id` 与按线程生成的 `session_id`。
7. 默认自动记忆 `update_memory_on_run=True`；只有需要模型在对话中主动“记住/忘记”时才用 `enable_agentic_memory=True`，两者不要同时开启。
8. 自动记忆也要限制内容、监控数量并定期整理；不得把临时闲聊、敏感数据或整段对话无差别写入记忆。
9. Knowledge 显式配置 embedder、vector DB、collection/table 名、chunking、检索数量和租户策略。
10. 工具使用窄参数、严格类型、清晰 docstring、超时、幂等键和错误分类；有副作用的工具启用确认或审批。
11. 多用户生产服务启用 JWT 和 `AuthorizationConfig(user_isolation=True)`；仅 `authorization=True` 不等于用户数据隔离。
12. `AgentOS(tracing=True)`；关键路径建立 accuracy、reliability、performance 与自定义质量评测。
13. 外部调用设置超时、有限重试、指数退避；写操作不得盲目自动重试。
14. 生产中关闭代码热重载，限制 CORS，密钥只从环境或 Secret Manager 读取。
15. 显式决定 Agno telemetry；有隐私要求时设置 `AGNO_TELEMETRY=false`。

## 五、标准实施流程

### 1. 盘点

检查：

- `pyproject.toml`、lockfile、Python/Agno 版本；
- 现有 Agent/Team/Workflow/AgentOS；
- 模型能力：tool calling、structured output、streaming、multimodal；
- DB、vector DB、迁移状态；
- `user_id/session_id` 来源；
- 工具的读写权限、超时、幂等性；
- 现有测试、评测和 tracing；
- 是否混入 `phi.*`、旧 `storage=`、旧 Knowledge 或 v2/v3 参数。

### 2. 写清验收标准

至少定义：

- 代表性输入与期望输出；
- 必须/禁止调用的工具；
- 最大延迟、最大工具次数、最大成本；
- 用户隔离与权限场景；
- 失败、超时、拒绝审批、重试后的行为；
- 需要持久化和不得持久化的数据。

### 3. 交付最小纵向切片

按这个顺序实现：

1. 单 Agent 与一个真实工具；
2. 结构化输出或可验证文本；
3. DB 与 Session；
4. user_id 和权限边界；
5. Memory/Knowledge，仅在需求明确后添加；
6. AgentOS API；
7. tracing 与 eval；
8. Team/Workflow，仅在确有收益后添加。

可从 `templates/production_agentos/` 复制完整起点，或运行：

```bash
python scripts/scaffold_agno_app.py /path/to/new-app
```

### 4. 验证循环

每次修改后执行：

```bash
python -m compileall -q src tests
pytest -q
ruff check .
ruff format --check .
python scripts/inspect_agno_project.py . --strict
```

服务类项目还要执行：

```bash
curl -fsS http://localhost:7777/health
curl -fsS http://localhost:7777/openapi.json >/dev/null
```

然后用 `templates/production_agentos/requests.http` 或等价 curl 验证：新 Session、续聊、不同用户、流式、工具失败、HITL、取消和恢复。

### 5. 输出结果

最终回复必须包含：

```markdown
## 架构选择
- Primitive：Agent / Team / Workflow
- Runtime：脚本 / AgentOS
- 状态：Session / State / Memory / Knowledge / Learning
- 数据与隔离：...

## 实现
- 修改文件：...
- 关键行为：...

## 验证
- 已运行：...
- 结果：...

## 风险与后续
- 未验证项：...
- 生产风险：...
```

不得只贴代码而不说明运行方式、身份边界和验证结果。

## 六、实现约束

### Agent 与实例生命周期

- Agent 配置对象是长期复用对象，不是“每个用户一个 Agent 实例”。
- 用户差异通过运行参数、数据库数据、依赖注入、Session State、Memory、Knowledge filter 或 factory 处理。
- 不要在 `for user in users:`、FastAPI handler、消息消费循环中构造 Agent。
- 自定义工具里若保存可变成员，必须保证线程/协程安全。AgentOS 会复制运行对象，但模型、数据库、Knowledge、MCP handle 和部分工具可能共享引用。

### 输入输出

- UI 文本可以自然语言；程序链路必须使用 Pydantic `input_schema`/`output_schema` 或明确 JSON schema。
- Schema 保证形状，不保证事实正确；事实仍须来自工具或 Knowledge，并在测试中核对。
- 不要用正则从自由文本“抢救”关键业务字段。

### 工具

- 一个工具完成一个明确动作；参数名、类型和 docstring 都是模型的工具协议。
- 查询与写入分开；预览与提交分开；敏感写入用 `@tool(requires_confirmation=True)`。
- 写工具要接受业务幂等键，先检查重复再提交。
- 工具不要吞掉异常并返回“成功”；将可恢复错误、拒绝、不可恢复错误分开。
- 外部 API 原始输出应裁剪；搜索型 Agent 可考虑 `compress_tool_results=True`。

### 多用户与安全

- 不信任客户端提交的 `user_id`。生产中由 JWT `sub` 绑定，开启 `user_isolation=True`。
- JWT 必须验证签名、算法、过期时间和 audience；Scopes 采用最小权限。
- 普通用户不得获得 `agent_os:admin`。
- CORS 是浏览器策略，不是鉴权；MCP、REST 和 WebSocket 都必须落在统一鉴权策略内。
- Prompt 防护不是权限控制。工具和数据库必须在服务端再次校验租户和资源归属。

### 本地模型

- vLLM 优先使用 `agno.models.vllm.VLLM`；其他 OpenAI-compatible 服务用 `OpenAILike`。
- 启用工具调用前先确认服务端 parser、chat template 与模型本身支持 function calling。
- 先做工具可靠性评测，再开放写工具；“能生成 JSON”不等于稳定工具调用。

## 七、最容易踩的坑

1. **混用教程年代**：`phi.*`、Playground、`storage=`、`AgentMemory`、旧 Knowledge 类属于旧架构。
2. **只开 authorization**：用户隔离默认关闭；多租户必须额外启用 `user_isolation=True`。
3. **user_id 缺失**：记忆可能落到默认用户，造成串用户。
4. **把 Session 当用户**：换线程后历史应断开，但长期 Memory 应继续跟随同一 user_id。
5. **同时开两种 Memory 模式**：Agentic 模式会覆盖自动模式，且可能显著放大 token 消耗。
6. **每次请求重建 Agent**：增加延迟、连接数和不可控资源使用。
7. **无稳定 ID**：重命名组件后会影响 API、会话查询、监控与权限配置。
8. **生产用单文件 SQLite**：多副本写入和迁移风险高。
9. **把 Knowledge 当实时数据库**：订单、余额、设备状态等应通过工具或 Context Provider 实时读取。
10. **结构化输出即正确**：Schema 只证明格式合法。
11. **Team 代替 Workflow**：模型动态委派无法保证固定顺序与事务边界。
12. **Workflow 代替一切**：过早编排增加上下文复制、延迟和故障点。
13. **盲目重试写操作**：网络超时后服务端可能已成功，必须配幂等键或查询确认。
14. **工具返回巨量文本**：会迅速耗尽上下文；分页、筛选、摘要或压缩。
15. **没有并发测试**：单用户成功不代表共享 Toolkit、连接池、Session State 在并发下安全。
16. **升级后直接清旧数据**：v3 DB 迁移必须先验证新 runs 表，再执行破坏性 cleanup。

## 八、完成定义

只有同时满足以下条件才算完成：

- 版本与 API 已核验；
- Primitive 选择有理由；
- 代码可导入、可运行；
- Session、user_id 与状态边界明确；
- 敏感工具有权限与审批；
- 关键失败路径被测试；
- 多用户无串数据；
- tracing 可定位模型、工具和步骤耗时；
- 至少有一组可重复 eval；
- 提供启动、调用、测试和回滚说明。
