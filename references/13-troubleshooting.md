# 故障排查手册

## 1. 通用排查顺序

```text
1. 记录原始错误、时间、环境、版本
2. 找 request_id / run_id / session_id / user_id
3. 运行 inspect_agno_project.py
4. 确认安装版本与当前代码 API 一致
5. 最小化为单 Agent / 单工具 / 单请求
6. 查看 trace 的 model/tool/db/knowledge/memory spans
7. 判断是否可稳定复现
8. 修复后加入回归测试
```

先判断故障层：

```text
import/config
model provider
Agent prompt/schema
Tool
DB/session/memory
Knowledge/vector
Team/Workflow
AgentOS API/stream
Auth/multitenancy
deployment/concurrency
```

## 2. `ModuleNotFoundError: agno...`

检查：

```bash
python -VV
which python
python -m pip show agno
python -c 'import agno; print(agno.__file__)'
```

常见原因：

- 安装到另一个 venv；
- IDE interpreter 不同；
- optional extra 未安装；
- 本地文件名 `agno.py` 遮蔽包；
- 项目里仍使用 `phi.*`。

修复：

```bash
uv add agno
uv run python your_file.py
```

按功能加 extra，如 `agno[os,mcp,postgres]`。

## 3. 旧参数报错

症状：

```text
unexpected keyword argument 'storage'
no module named phi
cannot import AgentMemory
knowledge_base is invalid
```

处理：

```bash
grep -RInE 'from phi|import phi|storage=|AgentMemory|knowledge_base=|Playground' .
```

对照 `00-version-and-migration.md` 整体迁移，不要用 `**kwargs` 吞掉错误。

## 4. AgentOS 无法启动

先最小化：

```python
agent_os = AgentOS(id="debug", agents=[assistant], db=db)
app = agent_os.get_app()
```

检查：

- `agno[os]` extra；
- component IDs 重复；
- model/tool 在构造时异常；
- DB URL/driver；
- custom `base_app` 路由冲突；
- MCP optional dependency；
- authorization key；
- scheduler 缺 internal token；
- Python module path 与 `app="module:app"` 不一致。

运行：

```bash
uv run python -m your_package.app
curl -v http://localhost:7777/health
```

## 5. `/health` 正常但 Agent run 失败

`/health` 只说明进程活着。查看 run 错误和 trace：

- model API key/base URL；
- provider 429/401/404；
- 模型 ID；
- tool schema；
- DB persistence；
- output schema；
- context length。

用一个无工具、无 DB、最短 prompt 的 Agent 测模型，再逐层加回功能。

## 6. 401 与 403

### 401

身份验证失败：缺 token、签名错误、过期、audience/issuer/algorithm 不匹配。

### 403

身份有效但缺 scope，或资源所有权不属于用户。

调试时仅记录：

```text
subject hash
issuer
audience
scope names
expiry
error category
```

不要记录完整 token。

## 7. 开启 JWT 后仍串用户

检查：

```python
AuthorizationConfig(user_isolation=True)
```

再检查自定义工具和业务 DB 是否服务端 filter user/tenant。AgentOS 隔离不能替代业务表隔离。

并发测试 user A/B：

```text
create sessions
write memories
list sessions
fetch run
cancel/continue
private knowledge search
```

任何跨用户返回都视为发布阻断。

## 8. Memory 没记住

检查：

- run 是否有明确 `user_id`；
- `update_memory_on_run=True` 或 `enable_agentic_memory=True`；
- 两种模式是否误同时开启；
- DB 可写；
- MemoryManager model 可调用；
- 对话内容是否符合抽取规则；
- 新 session 是否仍使用同一 user ID；
- 是否读错数据库/环境。

用明确句测试：

```text
“请记住：我长期不吃香菜。”
```

然后新 session 读取 memory 列表，不要只看自然语言回答猜是否保存。

## 9. Memory 过多、成本暴涨

常见原因：

- 每轮自动提取且 prompt 太宽；
- Agentic Memory 反复调用工具；
- 两种 memory source 双写；
- 全部历史每轮进入 MemoryManager；
- 无 dedupe/update；
- 临时事实也保存。

措施：

- 缩窄抽取指令；
- 选择一种模式；
- 限制 history；
- 更便宜的 memory model；
- 监控每用户 memory count；
- 定期 dedupe/cleanup；
- 建立“不应保存”eval。

## 10. Session 没续上

检查：

- 相同 `session_id`；
- 相同 component ID；
- 相同 DB；
- `add_history_to_context=True`；
- `num_history_runs`；
- user_id 所有权一致；
- 部署是否指向不同环境 DB。

Session 持久化存在不等于自动把历史加入模型 context；两者要分别配置。

## 11. Session State 丢失

检查：

- Agent 有 DB；
- 每次使用同一 session ID；
- 工具通过 `run_context.session_state` 修改；
- 没有把新 dict 在每轮覆盖持久状态；
- 并发 run 没有 last-write-wins 冲突；
- state 值可序列化。

同 session 多请求并发时应排队或加版本/CAS。

## 12. Knowledge 搜不到

逐层检查：

```text
source exists
reader produced documents
chunker produced chunks
embedder succeeds and dimension matches
vector insert committed
collection/path is correct
search query executes
filters match tenant/user
max_results > 0
agent actually calls search
```

直接调用 Knowledge/vector search，先排除 Agent 决策问题。记录 source ID、chunk count 和 ingestion status。

## 13. RAG 返回错误用户文档

立即停用相关 private search，检查：

- tenant/user filter 是否由服务端强制；
- 旧 collection 是否缺 user_id；
- cache key 是否含用户；
- shared 与 private collection 是否混用；
- user ID 是否来自可信 JWT；
- vector DB adapter 是否真正支持 filter；
- v2→v3 vector migration 是否执行。

此类问题属于数据泄漏事故，不只是“召回不准”。

## 14. Structured output 验证失败

检查：

- 模型是否原生支持 structured output；
- provider adapter 是否支持该模式；
- schema 是否太复杂；
- field 描述是否清晰；
- Optional 是否正确；
- enum 使用 `Literal`；
- output schema 与 markdown/自由文本指令是否冲突；
- tool结果是否缺数据。

将 schema 简化为两个字段测试，再逐步恢复。不要用 regex 静默解析失败文本。

## 15. 模型不调用工具

检查：

- 模型支持 function/tool calling；
- adapter 与服务端 parser；
- 工具名称/描述/参数是否清晰；
- instructions 是否明确必须调用；
- 工具太多或重叠；
- 输入是否真的需要工具；
- model context 是否被长历史淹没。

为必须调用的 case 建 reliability eval。必要时改为代码固定调用，而不是继续堆 prompt。

## 16. 模型反复调用工具

措施：

- 工具返回明确完成状态；
- instructions 定义停止条件；
- tool-call limit；
- 工具结果缩短；
- 查询工具接受批量参数；
- 对同参数缓存；
- 评测最大调用次数。

如果业务步骤固定，转 Workflow。

## 17. 工具参数乱填

- 使用严格类型、`Literal`、范围；
- 资源 ID 不靠自由文本；
- 关键字段缺失时要求澄清；
- server-side validate；
- identity 不作为模型参数；
- 对高风险写入先 preview；
- 参数 hash 绑定确认。

## 18. HITL 停住无法继续

保存：

- run ID；
- session ID；
- component ID；
- requirements；
- 原工具参数；
- approval decision。

检查 continue route/API 所需字段是否使用当前 v3 形式；旧 `updated_tools` 等参数可能已变化。审批 UI 必须处理 reject/timeout/cancel，而非只支持 approve。

## 19. 重试导致重复写入

症状：重复邮件、扣款、记录、通知。

修复：

- 客户端 request ID；
- AgentOS/queue Idempotency-Key；
- 工具业务幂等键；
- DB unique constraint；
- uncertain timeout 后先查询；
- workflow execution record；
- 写操作默认不自动重试。

Prompt 写“不要重复”没有事务保证。

## 20. Team 太慢或太贵

Trace 每个 member 和 leader：

- 调用次数；
- token；
- latency；
- 重复工作；
- 最终答案真正使用的内容。

优化：

- 减少成员；
- 专属窄角色；
- 成员输出 schema/长度限制；
- 并行用 Workflow `Parallel`；
- leader 用更便宜模型或减少上下文；
- 与单 Agent baseline 比较；
- 没收益就退回单 Agent。

## 21. Workflow 卡循环

每个 Loop 必须：

```text
max_iterations
structured exit condition
progress metric
no-progress detection
time/token budget
terminal failure state
```

不要让另一个自由文本 Agent 判断“是否足够好”且无限重试。

## 22. Workflow resume 后重复步骤

检查：

- DB/checkpoint；
- stable workflow/step IDs；
- side-effect execution record；
- 幂等 key；
- 代码版本是否改变 step topology；
- old run 是否由兼容版本恢复。

部署改变 Workflow 图时，对未完成 runs 做兼容策略，不能默认新代码可继续旧 topology。

## 23. SSE 客户端一直 loading

检查：

- 是否解析终态 event；
- `Content-Type`；
- 代理是否缓冲；
- Nginx/Cloudflare timeout；
- 客户端 AbortController；
- error event 是否被当普通 data 忽略；
- response newline framing；
- server run 是否已失败。

关闭反向代理 buffering，并在客户端对 completed/error/cancelled/paused 都结束 loading。

## 24. 流式断开后重复回答

不要断开即重新 POST 同一写请求。保存 run ID，优先：

- reconnect/tail existing event stream；
- 查询 run status；
- 只有确认未创建 run 才重新提交；
- 新提交带相同 idempotency key。

## 25. CORS 错误

浏览器控制台 CORS 失败时检查：

- exact origin：scheme/host/port；
- OPTIONS preflight；
- Authorization header allow；
- credentials 与 wildcard；
- 反向代理是否删 header；
- 环境变量解析是否把多个 origin 当一个字符串。

curl 成功而浏览器失败通常是 CORS，但仍不说明 API 安全。

## 26. MCP 连接不上

检查：

- 安装 `agno[mcp,os]`；
- 使用 `mcp=`；
- `/mcp` 路径；
- transport；
- client config；
- Host/Origin allowlist；
- OAuth/JWT/PAT；
- MCPConfig 是否最终零工具；
- tool name collision；
- tools/list 是否成功。

先用最小 `mcp=True`，再收窄配置。

## 27. MCP 发布工具时报 HITL 相关错误

直接 MCP custom tool 不经过 Agent 的 FunctionCall 审批循环。带 confirmation/user input/external execution 的工具不应直接发布。

改为：

- 把包含该工具的 Agent/Workflow 作为 MCP tool；或
- 移除 direct publication，只在 REST/Agent loop 使用；或
- 将工具拆为无副作用 preview 与经过服务端审批的 commit API。

## 28. SQLite locked

常见于多线程/多进程/并发写。开发可减少并发；生产改 PostgreSQL。不要靠无限重试隐藏架构问题。

## 29. PostgreSQL 连接耗尽

检查：

```text
replicas × workers × pool_size + overflow
background workers
migration jobs
stale connections
long transactions
```

复用 DB 对象，设置 pool timeout，缩短事务，监控 `pg_stat_activity`。

## 30. vLLM 404/模型不可用

检查：

```bash
curl -sS http://VLLM_HOST:8000/v1/models
```

确保 adapter 的 model ID 与 served model name 一致，base URL 含 `/v1`（按服务配置），API key 占位满足 server 要求。

## 31. vLLM 不会工具调用

需要三件事同时成立：

1. 模型训练/模板支持 tool calling；
2. vLLM 启动参数启用对应 parser/chat template；
3. Agno adapter 发送兼容协议。

先用原始 OpenAI-compatible curl 测 tool call，再测 Agno。普通 JSON 输出成功不能证明 function calling 成功。

## 32. 上下文过长

来源：

- history runs 太多；
- tool result 巨大；
- memory 全量注入；
- RAG top-k/chunk 大；
- Team member transcript；
- system instructions 重复。

优化：

- 缩短 history；
- tool pagination/trim/compress；
- relevant memory only；
- RAG eval 后调 top-k；
- member schema；
- context compression；
- 记录每类 context token。

## 33. 升级后历史丢失

不要立刻重建空 DB。检查：

- 环境变量指向的 DB；
- v2→v3 migration；
- runs 独立表；
- component IDs 是否变化；
- schema/table names；
- user isolation filter；
- vector migration；
- cleanup 是否过早。

从备份复制到隔离环境复现，禁止直接在生产反复试 cleanup。

## 34. 最小复现模板

故障报告至少提供：

```text
Agno version
Python version
OS/runtime
minimal dependencies
minimal code
exact command
expected result
actual error/traceback
model/provider
DB type
whether auth/memory/knowledge/stream enabled
```

删除 token、用户数据和 proprietary prompt。最小复现应能在新 venv 启动。
