# Tools、Guardrails 与 Human-in-the-Loop

## 1. Tool 是安全边界，不只是函数包装

模型通过函数名、参数类型和 docstring 理解工具。工具实现同时承担：

- 输入校验；
- 身份和资源归属校验；
- 超时、重试与限流；
- 幂等；
- 事务；
- 审计；
- 错误分类；
- 输出裁剪。

不要把这些责任全部交给系统提示词。

## 2. 普通函数工具

```python
from typing import Literal


def get_order(order_id: str, detail: Literal["summary", "full"] = "summary") -> dict:
    """Return an order visible to the authenticated user.

    Args:
        order_id: Stable order identifier such as ord_123.
        detail: Amount of detail to return.
    """
    ...
```

函数参数不要使用 `**kwargs` 承载业务协议；模型需要明确 schema。

## 3. 使用 RunContext

需要 Session State 或运行上下文时：

```python
from agno.run import RunContext


def add_item(run_context: RunContext, sku: str, quantity: int = 1) -> str:
    """Add an item to the current session cart."""
    if quantity < 1 or quantity > 10:
        return "quantity must be between 1 and 10"

    cart = list(run_context.session_state.get("cart", []))
    cart.append({"sku": sku, "quantity": quantity})
    run_context.session_state["cart"] = cart
    return f"Added {quantity} × {sku}"
```

不要把当前用户写进 Toolkit 实例字段。并发请求可能共享同一个工具对象。

## 4. Tool decorator

Decorator 可声明名称、描述和 HITL：

```python
from agno.tools import tool


@tool(
    name="submit_order",
    description="Submit the already validated cart as an order",
    requires_confirmation=True,
)
def submit_order(cart_id: str, idempotency_key: str) -> str:
    """Commit an order exactly once after explicit confirmation."""
    ...
```

有副作用操作的推荐拆分：

```text
validate_input       read-only
preview_change       read-only
request_confirmation pause
commit_change        write + idempotent + audited
verify_result        read-only
```

## 5. Toolkit 最小权限

内建 Toolkit 通常允许 `include_tools`、`exclude_tools` 或类似参数。默认只开放需要的函数：

```python
tools=[
    GithubTools(
        include_tools=[
            "get_repository",
            "get_pull_requests",
            "list_issues",
        ]
    )
]
```

读写工具混在同一 Toolkit 时，显式排除 delete/create/update 等危险函数，或给特定函数加 confirmation。

## 6. Tool 输出设计

推荐返回小而稳定的结构：

```python
return {
    "status": "ok",
    "record_id": order.id,
    "state": order.state,
    "updated_at": order.updated_at.isoformat(),
}
```

避免：

- 返回整张数据库表；
- 返回 HTML、日志或 SDK 对象的完整 repr；
- 在错误时返回看似成功的自然语言；
- 将 Secret、access token、内部堆栈传回模型。

搜索工具应支持 query、filters、limit、cursor，并限制最大结果数。

## 7. 错误处理

分类：

| 类型 | 行为 |
|---|---|
| 用户参数可修复 | 给模型明确错误，让其修正一次 |
| 需要用户信息 | HITL user input 或返回 `needs_user` |
| 权限不足 | 立即拒绝，不让模型重试绕过 |
| not found | 明确返回，不编造 |
| rate limit / 短暂 5xx | 有限退避重试 |
| 写操作结果未知 | 用 idempotency key 查询确认，不盲重放 |
| 永久业务错误 | 结束该动作并说明 |

Agno 提供工具执行异常，例如 `RetryAgentRun` 和 `StopAgentRun`。`RetryAgentRun` 是让当前模型工具循环根据反馈重试，并非重启整个 Agent run。使用时限制次数，避免无限修复循环。

## 8. Tool call limit

对能自主调用多个工具的 Agent 设置合理上限：

```python
agent = Agent(
    tools=[...],
    tool_call_limit=8,
)
```

记忆工具、搜索工具和 Team delegation 都可能放大调用数。上限应按任务评测，而非随意设很大。

## 9. Guardrails

Agno Guardrails 通过 pre-hooks 运行，可用于 PII、prompt injection、moderation 等输入检查：

```python
from agno.agent import Agent
from agno.guardrails import PIIDetectionGuardrail, PromptInjectionGuardrail

agent = Agent(
    model=model,
    pre_hooks=[
        PIIDetectionGuardrail(),
        PromptInjectionGuardrail(),
    ],
)
```

Guardrail 的定位：

- 阻止或变换明显不安全输入；
- 保护模型上下文；
- 建立可观测的安全事件。

Guardrail 不能替代：

- JWT/RBAC；
- 数据库 row-level authorization；
- 工具 allowlist；
- 业务交易校验；
- 输出端隐私检查。

### 自定义 Guardrail

继承 `BaseGuardrail`，同时实现 sync 与 async：

```python
from agno.exceptions import CheckTrigger, InputCheckError
from agno.guardrails import BaseGuardrail
from agno.run.agent import RunInput


class TenantCommandGuardrail(BaseGuardrail):
    def check(self, run_input: RunInput) -> None:
        if isinstance(run_input.input_content, str) and "ignore tenant" in run_input.input_content.lower():
            raise InputCheckError(
                "Input attempts to bypass tenant boundaries",
                check_trigger=CheckTrigger.INPUT_NOT_ALLOWED,
            )

    async def async_check(self, run_input: RunInput) -> None:
        self.check(run_input)
```

异步实现如果包含 I/O，不要简单调用同步阻塞代码。

## 10. 用户确认 HITL

### 标记敏感工具

```python
from agno.tools import tool


@tool(requires_confirmation=True)
def delete_document(document_id: str) -> str:
    """Permanently delete a document after confirmation."""
    ...
```

### Agent 必须配置 DB 才能按 run_id 继续

```python
agent = Agent(
    id="document-agent",
    model=model,
    tools=[delete_document],
    db=db,
)
```

### 暂停、确认、继续

```python
run = agent.run(
    "Delete document doc_123",
    user_id="u_1",
    session_id="s_1",
)

if run.is_paused:
    for requirement in run.active_requirements:
        if requirement.needs_confirmation:
            # UI/管理员确认后，而不是模型自己确认。
            requirement.confirm()   # 或 requirement.reject()

    run = agent.continue_run(
        run_id=run.run_id,
        requirements=run.requirements,
    )
```

Async 使用 `await agent.acontinue_run(...)`。生产 UI 不应在服务进程里调用 `input()`，而应持久化 paused run，并通过 approvals/continue API 恢复。

## 11. Workflow HITL

v3 将 Step 的人工审核配置放入 `HumanReview`：

```python
from agno.workflow.step import Step
from agno.workflow.types import HumanReview

publish = Step(
    name="publish",
    executor=publish_article,
    human_review=HumanReview(
        requires_confirmation=True,
        confirmation_message="Publish this article?",
        timeout=3600,
    ),
)
```

Workflow 可在：

- 执行前要输入；
- 执行前确认；
- 执行后审核输出；
- 外部执行工具；
- 管理员审批；

等位置暂停。审核拒绝后的 retry/abort/edit 行为必须写清楚。

## 12. 外部 Tool Execution

某些动作不应由 Agent 进程直接执行，例如：

- 手机端生物识别确认；
- 企业审批系统；
- 用户浏览器 OAuth；
- 受控部署流水线。

此时 Agent 生成结构化 tool request 并暂停，外部系统执行后把结果带回 continue。不要为“方便”把高权限凭据塞进 Agent 容器。

## 13. Side-effect 安全清单

```text
[ ] 工具最小权限
[ ] server-side 身份与资源归属校验
[ ] 预览和提交分离
[ ] 明确 confirmation/approval
[ ] idempotency key
[ ] 事务或补偿策略
[ ] 超时后可查询实际状态
[ ] 敏感参数脱敏日志
[ ] 操作人、run_id、session_id、resource_id 可审计
[ ] 失败不会被自然语言包装成成功
[ ] 评测包含“不得调用”与恶意提示 case
```
