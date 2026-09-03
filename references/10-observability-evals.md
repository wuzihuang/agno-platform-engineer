# 可观测性、Tracing、Evals 与可靠性

## 1. 为什么普通日志不够

一次 Agent run 可能包含：

```text
request parsing
→ session/history load
→ memory retrieval
→ model call
→ tool calls
→ retries
→ knowledge search
→ model synthesis
→ memory update
→ persistence
→ stream delivery
```

只记录最终 200/500 无法回答“慢在哪、为什么错、是否串用户、为何没调用工具”。需要 run 级 trace、结构化事件、指标和可重复 eval。

## 2. 开启 AgentOS tracing

```python
agent_os = AgentOS(
    db=db,
    agents=[assistant],
    tracing=True,
)
```

Trace 应覆盖 Agent、Team、Workflow、模型和工具 span。生产前确认 trace DB 与 UI 能看到：

- run/session/user/component IDs；
- model/provider；
- model latency、token usage；
- tool name、duration、status；
- workflow step；
- error type；
- first-token time；
- total duration。

## 3. 独立脚本 tracing

不通过 AgentOS 时，可按当前 Agno tracing API 初始化。典型形态：

```python
from agno.tracing import setup_tracing

setup_tracing(db=db)
```

具体导入和参数对版本敏感；先通过当前 docs MCP 核验。不要在测试中把生产 trace 发到同一数据库。

## 4. OpenTelemetry

需要统一观测栈时安装相应 extra：

```bash
uv add 'agno[opentelemetry]'
```

把 Agno spans 导出到现有 OTLP collector，再连接 Jaeger、Tempo、Datadog、New Relic、Phoenix、Langfuse 等。原则：

- 使用标准 trace/span ID；
- 将 HTTP request span 与 Agent run span 关联；
- 不把完整 prompt 默认作为 span attribute；
- 大工具结果不要塞进 attribute；
- provider request ID 放入受控 metadata；
- sampling 规则区分成功与失败。

## 5. 建议指标

### 请求层

```text
requests_total{route,status}
request_duration_seconds
active_requests
rate_limit_rejections
```

### Run 层

```text
runs_total{component,status}
run_duration_seconds
run_time_to_first_token_seconds
run_queue_wait_seconds
run_cancel_total
run_pause_total
run_resume_total
```

### Model 层

```text
model_calls_total{provider,model,status}
model_latency_seconds
input_tokens_total
output_tokens_total
cached_tokens_total
model_fallback_total
structured_output_validation_failure_total
```

### Tool 层

```text
tool_calls_total{tool,status}
tool_latency_seconds
tool_timeout_total
tool_retry_total
tool_confirmation_total
tool_duplicate_prevented_total
```

### Memory/Knowledge

```text
memory_writes_total
memory_recall_total
memory_conflict_total
knowledge_search_latency_seconds
knowledge_results_count
knowledge_empty_search_total
ingestion_jobs_total{status}
```

### Quality/Business

```text
task_success_rate
user_correction_rate
handoff_rate
abstention_rate
cost_per_successful_task
```

不要把“HTTP 200”当 task success。

## 6. SLI/SLO 示例

```text
Availability: 99.9% run requests accepted/answered without platform error
TTFT p95: < 2.0 s
End-to-end p95: < 10 s for normal chat
Tool success: > 99% for read-only internal APIs
Cross-user leakage: 0
Structured output validity: > 99.5%
Memory extraction precision: > 95%
RAG citation correctness: > 95%
```

SLO 要按产品和模型成本调整。伴侣对话更关注 TTFT、自然度和记忆融合；业务 Agent 更关注动作成功、准确性和审计。

## 7. Evals 的分层

### Unit tests

确定性函数、schema、权限、工具参数、幂等。

### Contract tests

模型 provider、外部 API、AgentOS REST/SSE、MCP、数据库。

### Agent Evals

回答质量、工具选择、工具参数、召回、拒答、结构化输出。

### System simulations

完整多轮场景、并发、故障注入、用户分层、成本。

### Production monitoring

真实流量的采样、用户反馈、错误聚类、漂移。

## 8. Accuracy Eval

Agno 提供 accuracy eval primitive。典型测试结构应至少包含：

```python
from agno.eval.accuracy import AccuracyEval

case = AccuracyEval(
    name="account-summary-grounded",
    agent=assistant,
    input="Summarize account acc_123",
    expected_output="Summary must only use the supplied account facts.",
)

case.run(print_results=True)
```

具体构造参数随版本核验。评判可以是：

- exact/semantic expected output；
- LLM judge；
- 自定义 evaluator；
- schema + deterministic assertions。

高风险事实优先使用确定性断言，不能全部交给同一个模型自评。

## 9. Reliability Eval

Reliability 关注“做法是否符合预期”，而非只看最终措辞：

```text
必须调用 get_order
禁止调用 cancel_order
最多调用 search 2 次
必须在 write 前调用 validate
必须产生 confirmation requirement
```

测试示例语义：

```python
from agno.eval.reliability import ReliabilityEval

response = assistant.run("What does policy P-104 say?")
case = ReliabilityEval(
    name="requires-search",
    agent_response=response,
    expected_tool_calls=["search_knowledge_base"],
)
result = case.run(print_results=True)
```

Team 使用 `team_response=`。工具参数还可通过当前版本支持的 expected-tool-argument 配置进行断言。核心是先获得真实 RunOutput，再把 tool sequence 变成可验证行为。

## 10. Performance Eval

记录：

- TTFT；
- total latency；
- model/tool latency breakdown；
- input/output tokens；
- number of calls；
- concurrency；
- cost；
- memory/CPU；
- queue delay。

性能测试必须固定：模型、温度、prompt、工具 mock/真实模式、网络区域和并发。不要拿两次偶然请求比较框架快慢。

## 11. 结构化输出评测

Schema valid 只是第一层：

```text
1. JSON/schema validity
2. required fields present
3. enums/ranges valid
4. facts match tool source
5. null used instead of fabrication
6. cross-field consistency
7. downstream business rule validity
```

例：`total` 必须等于 items sum；currency 必须与账户一致；资源 ID 必须属于该用户。

## 12. Tool-call 测试

每个工具建立：

### Positive cases

模型应调用工具且参数正确。

### Negative cases

普通知识问题不应调用昂贵工具；无权限时不应调用写工具。

### Ambiguous cases

模型应先询问或输出 preview，而非猜关键参数。

### Failure cases

429、timeout、5xx、malformed response、partial success、重复请求。

### Adversarial cases

用户和工具结果中含 prompt injection。

## 13. Memory Evals

离线测试集：

```yaml
- conversation: "我长期不吃香菜"
  should_store: true
  expected_fact: "用户不吃香菜"
- conversation: "我今天中午吃了面"
  should_store: false
- conversation: "我现在可以吃一点香菜了"
  should_update: true
- conversation: "忘掉我的饮食偏好"
  should_delete: true
```

指标：precision、recall、duplicate、conflict update、delete success、cross-session recall、natural integration、cross-user leakage。

## 14. RAG Evals

分开测 retrieval 与 generation：

```text
Retrieval:
- hit@k
- recall@k
- MRR/nDCG
- tenant filter correctness
- source freshness

Generation:
- groundedness
- citation correctness
- completeness
- correct abstention
- conflict handling
```

如果 retrieval 没召回，不能只改回答 prompt；如果召回正确但答案错，才重点调 synthesis。

## 15. Team Evals

与单 Agent baseline 比较：

- 最终质量；
- 成员调用是否符合预期；
- 是否重复委派；
- 成员意见是否被 leader 正确综合；
- token/latency/cost；
- 单成员失败后的行为。

没有显著质量收益就删除 Team，而不是因为代码已经写了就保留。

## 16. Workflow Evals

测试每条路径：

```text
happy path
validation failure
condition true/false
router branches
parallel child failure
loop reaches goal
loop reaches max iterations
HITL approve/reject/timeout
resume after restart
side-effect idempotency
cancel
```

步骤输出用结构化 fixture，不必每个测试都真的调用付费模型。

## 17. LLM Judge 的使用规则

Judge 适合自然度、完整性、风格和复杂语义，不适合作为唯一真值。至少：

- judge prompt 版本化；
- 隐藏候选顺序或随机化；
- 多 judge/多次采样检查一致性；
- 用人工标注集校准；
- 输出理由和置信度；
- 不让被测 Agent 与 judge 看到彼此私有 chain-of-thought；
- 对安全与事实使用确定性校验补充。

## 18. 回归集组织

```text
evals/
├── datasets/
│   ├── chat.yaml
│   ├── tools.yaml
│   ├── memory.yaml
│   ├── rag.yaml
│   └── security.yaml
├── scorers/
├── baselines/
├── run_offline.py
└── report.py
```

每条 case 包含：

```text
id
category
input/messages
user/session setup
fixtures
expected behavior
forbidden behavior
scorers
max latency/cost
owner
```

## 19. CI 策略

### 每个 PR

- unit/contract mock；
- 小规模 deterministic eval；
- skill/project inspector；
- schema/import tests。

### 主分支或 nightly

- 真实 provider/tool tests；
- 较大 eval suite；
- 多模型对比；
- concurrency/load；
- security simulations。

### 发布前

- staging migration；
- full system eval；
- rollback；
- shadow/canary。

设置阈值，不能只是生成漂亮报告：

```text
fail if task_success decreases > 2 percentage points
fail if cross-user leakage > 0
fail if p95 latency increases > 20%
fail if cost/success increases > 25% without approved exception
```

## 20. 生产反馈闭环

```text
Trace/feedback
  ↓ redact + sample
Failure taxonomy
  ↓ label
Regression case
  ↓ fix prompt/tool/model/code
Offline eval
  ↓ canary
Production monitor
```

不要直接把所有用户聊天自动变训练数据。先处理授权、隐私、脱敏、保留和可删除性。

## 21. 故障定位顺序

```text
1. 找到 request_id/run_id/session_id
2. 确认身份与组件版本
3. 看 run 终态
4. 看 model/tool/knowledge/memory spans
5. 对比同输入离线复现
6. 判断是数据、模型、工具、编排、权限还是流式客户端
7. 加回归 case
```

修一次线上 bug 却不增加 regression case，通常还会再次发生。
