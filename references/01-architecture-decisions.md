# 架构选择：Agent、Team、Workflow 与 AgentOS

## 1. 不要先问“用几个 Agent”，先问“哪个决策必须由谁控制”

- 由模型在运行时决定下一步：Agent loop 或 Team delegation。
- 由代码保证顺序、分支、重试和审批：Workflow。
- 由 API 层处理会话、权限、观测和多客户端：AgentOS。
- 由业务服务保证交易、权限和幂等：普通应用代码与数据库，不交给 LLM。

## 2. 决策树

```text
任务是否可由一个模型在一个工具循环内完成？
├─ 是 → Agent
│   ├─ 需要服务化？→ Agent + AgentOS
│   └─ 只做脚本？→ Agent
└─ 否
    ├─ 执行拓扑能否事先明确？
    │   ├─ 是 → Workflow
    │   │   ├─ 某一步需要动态专家协作？→ Workflow 中放 Team/Agent step
    │   │   └─ 需要服务化？→ Workflow + AgentOS
    │   └─ 否 → Team
    │       ├─ leader 动态路由/综合
    │       └─ 仍需服务化？→ Team + AgentOS
```

## 3. Agent：默认起点

适合：

- 一个清晰角色；
- 1–10 个边界明确的工具；
- 对话、RAG、数据查询、简单动作；
- 通过 prompt + tool + schema 就能稳定完成。

典型架构：

```text
Client → AgentOS → Agent
                    ├─ Model
                    ├─ Read tools
                    ├─ Confirmed write tools
                    ├─ DB (sessions/memory)
                    └─ Knowledge / context providers
```

单 Agent 的优势不是“简单”，而是：更低延迟、更少上下文复制、更容易评测、更少协调失败。

## 4. Team：动态专家协作

适合：

- 用户问题本身决定应该找哪个专家；
- 需要多个独立观点后由 leader 综合；
- 专家有不同工具/知识/权限；
- 任务需要协商、批判或对抗测试。

常见模式：

### Router

leader 根据请求选择一个成员。适合客服领域路由、数据源路由。

### Parallel perspectives

多个成员独立分析，再由 leader 综合。适合研究、风险审查、创意探索。

### Worker + checker

一个成员产出，一个成员验证。必须用 eval 证明 checker 真能降低错误，而非仅增加成本。

### Specialist tools

每个成员只拥有自己的工具集合，降低误调用面。

不要把固定的“研究→写作→审核→发布”交给 Team leader 随机组织；这属于 Workflow。

## 5. Workflow：显式执行图

适合：

- 固定顺序；
- 并行 fan-out / 汇总；
- 条件分支；
- 循环到质量阈值；
- 失败重试、断点恢复；
- 人工审批；
- 需要审计每一步输入输出。

```text
Input
  ↓
Validate ──fail──> Reject
  ↓ pass
Parallel[Research A, Research B, Retrieve internal facts]
  ↓
Synthesize
  ↓
Human review ──reject/feedback──> Revise loop
  ↓ approve
Commit side effect
```

Workflow 的节点可以是：

- Agent
- Team
- Python executor
- 嵌套 Steps
- Parallel
- Condition
- Router
- Loop

固定业务约束应写在 graph/code 中，而不是只写在系统提示词中。

## 6. AgentOS：运行时，不是另一种 Agent

AgentOS 负责：

- 注册 Agent/Team/Workflow；
- REST 与 SSE；
- 可选 MCP、A2A、AG-UI、Slack、Telegram、WhatsApp 等接口；
- Session、Memory、Knowledge、Learning；
- Traces、metrics、evals、approvals；
- Scheduler、background run、queue；
- JWT、scopes、service accounts、用户隔离；
- AgentOS UI/Control Plane 连接。

业务代码仍应独立维护：账户、订单、支付、配额、订阅、敏感资料，不因为使用 AgentOS 就迁进 Agent Session。

## 7. 选择升级的评测门槛

### Agent → Team

至少证明一项：

- 质量指标显著提升；
- 专家路由准确率提高；
- 风险遗漏率下降；
- 单 Agent 无法安全持有所有工具权限；
- 并行成员能在 SLA 内降低总时长。

同时记录：token、端到端延迟、失败率、调用次数和单位任务成本。

### Agent/Team → Workflow

当以下任一约束不能只靠 prompt 保证时升级：

- 固定步骤必须执行；
- 一个动作只能在验证/审批后执行；
- 需要并行后 join；
- 需要断点继续；
- 需要状态机式审计；
- 需要不同错误的不同补偿策略。

## 8. 推荐项目结构

```text
src/app/
├── app.py                 # AgentOS + FastAPI app
├── settings.py            # env/config
├── db.py                  # DB factories/singletons
├── models.py              # model adapters
├── agents/
│   ├── assistant.py
│   └── specialists.py
├── teams/
│   └── research.py
├── workflows/
│   └── publish.py
├── tools/
│   ├── read_tools.py
│   └── write_tools.py
├── knowledge/
│   ├── store.py
│   └── ingest.py
├── schemas/
│   └── outputs.py
├── security/
│   └── authorization.py
└── evals/
    ├── cases.py
    └── run.py
```

保持 Agent 配置与请求 handler 分离。Handler 只解析可信身份、构造本次运行参数、调用长期复用对象并返回结果。

## 9. 常见错误架构

### 每用户一个 Agent 对象

错误：实例数与用户数线性增长，模型/工具/连接重复，部署难以水平扩展。

正确：共享配置对象，运行时传 `user_id`、`session_id`、dependencies；用户数据进入 DB。

### 所有数据都写 Memory

错误：Memory 成为无 schema 的用户数据库，成本与隐私风险不断增长。

正确：业务事实在业务 DB；Memory 只保存少量高价值长期偏好；Session State 保存线程临时状态。

### Team 作为并行任务引擎

错误：leader 仍可能串行、跳过成员或重复委派。

正确：必须并行时用 Workflow `Parallel` 或普通 async 并发，并设置上限。

### Workflow 承担事务

错误：LLM 节点成功不代表支付/订单事务完成。

正确：最终 side-effect 由具备幂等和事务保证的业务工具执行，Workflow 只编排其调用条件。
