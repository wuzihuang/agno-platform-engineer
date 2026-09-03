# Teams 与 Workflows

## 1. Team：leader 动态协调

最小形态：

```python
from agno.agent import Agent
from agno.team import Team

researcher = Agent(
    id="researcher",
    name="Researcher",
    role="Gather verifiable evidence",
    model=member_model,
    tools=[search_tool],
)

critic = Agent(
    id="critic",
    name="Critic",
    role="Find unsupported claims and missing risks",
    model=member_model,
)

team = Team(
    id="research-team",
    name="Research Team",
    model=leader_model,
    members=[researcher, critic],
    instructions=[
        "Use both members for high-stakes research.",
        "Synthesize disagreements explicitly.",
        "Do not invent evidence absent from member results.",
    ],
    db=db,
    show_members_responses=True,
    add_history_to_context=True,
    num_history_runs=3,
    markdown=True,
)
```

Team leader 本身也会消耗模型调用。总成本大致是成员调用 + leader 综合 + 可能的重复委派。

## 2. Team 成员设计

每个成员应有：

- 单一 role；
- 专属工具/Knowledge；
- 清楚的输入和输出；
- 不重叠或有意对抗的职责；
- 可单独评测的标准。

差的拆分：

```text
Agent A: 帮忙研究
Agent B: 也帮忙研究
Agent C: 想得更深入
```

好的拆分：

```text
Evidence collector → 返回来源与事实
Risk critic        → 只找反例、缺口、权限风险
Decision writer    → 根据已给事实输出 schema
```

## 3. Team Skills

Skill 可直接给 leader：

```python
from agno.skills import LocalSkills, Skills

team = Team(
    model=leader_model,
    members=[implementer],
    skills=Skills(loaders=[LocalSkills("/path/to/skills")]),
)
```

也可只给某个成员。选择：

- leader 需要领域知识做路由：Team-level；
- 成员执行时才需要：member-level；
- 二者都需要：两边都配，但避免重复加载和冲突规则。

## 4. Team Session 与 Memory

Team 的 history 参数主要影响 leader。成员的会话/上下文行为不要靠猜，要通过 trace 检查实际消息。

多用户调用仍必须：

```python
team.run(message, user_id=user_id, session_id=session_id)
```

Team 增加了更多模型上下文和共享工具风险，必须测试不同用户并发。

## 5. Team 的失败模式

- leader 未调用应调用成员；
- 重复调用同一成员；
- 成员结果过长导致 leader 丢信息；
- 成员使用了越权工具；
- leader 把成员猜测当事实；
- 成员间循环委派；
- 同一个任务比单 Agent 更慢但质量无提升。

为此建立：

- expected member/tool calls；
- 最大 delegation 次数；
- 成员结构化输出；
- trace；
- 单 Agent baseline 对照。

## 6. Workflow：显式步骤

顺序 Workflow：

```python
from agno.workflow import Step, Workflow

collect = Step(
    name="Collect Evidence",
    agent=research_agent,
    description="Gather source-backed facts",
)

analyze = Step(
    name="Analyze",
    agent=analysis_agent,
    description="Analyze only the provided evidence",
)

write = Step(
    name="Write",
    agent=writer_agent,
    description="Produce the final structured brief",
)

workflow = Workflow(
    id="research-pipeline",
    name="Research Pipeline",
    description="Evidence → analysis → final brief",
    db=db,
    steps=[collect, analyze, write],
)
```

v3 `Workflow` 构造器使用关键字参数。

## 7. Step 类型

一个 Step 可以由：

- `agent=`；
- `team=`；
- `executor=` Python callable；

驱动。选择原则：

- 需要 LLM 推理：Agent；
- 需要动态专家协作：Team；
- 纯验证/转换/数据库动作：普通 Python executor。

能用确定性代码完成的校验不要浪费一次模型调用。

## 8. 高级控制流

Agno Workflow 支持或提供相应 primitives：

- `Parallel`：多个步骤并发；
- `Condition`：按代码条件选择；
- `Router`：动态选择路径；
- `Loop`：重复到满足条件或上限；
- 嵌套 `Steps`；
- HumanReview/HITL。

这些 API 在版本间容易变化。实现前从当前 docs MCP 读取对应 reference，并先写最小测试。核心规则：

- Parallel 必须设置资源上限；
- Condition 使用结构化字段，不解析自由文本；
- Router 输出限定 enum；
- Loop 必须有最大次数、退出条件和失败状态；
- side effect 放在审批后；
- 每步输出尽量小、结构化且可持久化。

## 9. 数据流

不要依赖“下一步自然会看懂上一段长文本”。为步骤定义明确 contract：

```python
class EvidenceBundle(BaseModel):
    claims: list[Claim]
    source_ids: list[str]
    gaps: list[str]

class Decision(BaseModel):
    outcome: Literal["approve", "reject", "needs_review"]
    reasons: list[str]
```

如果某一步只需要其中三个字段，就只传三个字段。

## 10. Workflow HITL

```python
from agno.workflow.types import HumanReview

commit_step = Step(
    name="Commit",
    executor=commit_change,
    human_review=HumanReview(
        requires_confirmation=True,
        confirmation_message="Apply this change?",
        timeout=3600,
    ),
)
```

审批前展示：

- 将执行的动作；
- 资源 ID；
- diff/预览；
- 风险；
- 幂等键；
- 审批超时后的行为。

## 11. 恢复与幂等

Workflow 被重试或恢复时，已经执行过的 side effect 可能再次到达。每个写步骤必须：

```text
workflow_run_id + step_id + business_resource_id
```

形成稳定幂等键，或在业务 DB 维护 execution record。

不要将“Step 状态 completed”作为外部支付/邮件/部署一定成功的唯一证据；执行后读取外部系统确认。

## 12. Team vs Workflow 对比

| 维度 | Team | Workflow |
|---|---|---|
| 下一步决定者 | 模型 leader | 代码/条件 |
| 执行顺序 | 动态 | 显式 |
| 并行保证 | 不保证 | 可显式 |
| 审计可预测性 | 中 | 高 |
| 灵活探索 | 高 | 中 |
| 事务边界 | 弱 | 可明确放置 |
| 成本可预测性 | 较低 | 较高 |
| 适合对话 | 是 | 视情况 |
| 适合业务流程 | 仅非关键协作 | 是 |

## 13. 推荐组合

### 产品 Copilot

```text
AgentOS → single Agent → tools + memory + knowledge
```

### 研究报告

```text
Workflow
  ├─ Parallel[web researcher, internal knowledge researcher]
  ├─ Critic Agent
  ├─ Writer Agent
  └─ HumanReview
```

### 企业支持

```text
AgentOS → Team leader
          ├─ Billing specialist (read-only billing tools)
          ├─ Product specialist (Knowledge)
          └─ Escalation specialist
```

### 高风险动作

```text
Agent proposes → deterministic validation → HumanReview → idempotent executor
```

## 14. 评测

Team：

- 路由准确率；
- 必须成员调用率；
- 不必要成员调用率；
- 综合完整性；
- 成本与延迟。

Workflow：

- step success rate；
- branch correctness；
- retry distribution；
- loop convergence；
- paused/resume success；
- duplicate side-effect rate；
- end-to-end completion rate。
