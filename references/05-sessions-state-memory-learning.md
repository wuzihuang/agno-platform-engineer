# Session、State、Memory 与 Learning

## 1. 四类数据不要混

| 类型 | 范围 | 示例 | 真相来源 |
|---|---|---|---|
| Session history | 一条对话线程 | 本轮前 5 次问答 | Agno DB |
| Session state | 一条线程内结构化可变状态 | 购物车、任务步骤、小游戏分数 | Agno DB / 业务 DB |
| User memory | 同一用户跨线程长期事实/偏好 | 喜欢简短回答、职业、稳定兴趣 | Agno Memory tables/store |
| Learning | 从反馈或执行中抽取的改进知识 | 某类任务的成功策略 | Learning store |
| Business data | 产品真实状态 | 订阅、余额、订单、健康记录 | 业务数据库/API |

业务数据不能因为“Agent 会记住”就复制为 Memory 真相。

## 2. user_id 与 session_id

```python
run = agent.run(
    "继续刚才的话题",
    user_id="user_123",          # 人
    session_id="chat_20260903", # 线程
)
```

相同 `user_id` + 不同 `session_id`：

- Session history 不共享；
- User Memory 可以共享；
- 业务数据按 user_id/tenant 读取；
- Session State 默认不共享。

相同 `session_id` 不应跨用户复用。生产中由 JWT `sub` 注入/绑定 `user_id`，不要信任表单字段。

## 3. Session history

```python
agent = Agent(
    db=db,
    add_history_to_context=True,
    num_history_runs=5,
)
```

三件事分开：

1. DB 是否保存 run；
2. 当前 run 是否恢复指定 Session；
3. 历史是否加入模型上下文。

历史保存在 DB 不代表必须全部发给模型。常用策略：最近 N 次 + Session summary + 结构化 state。

## 4. Session State

初始化：

```python
agent = Agent(
    db=db,
    session_state={"cart": [], "stage": "browsing"},
    add_session_state_to_context=True,
)
```

工具读写：

```python
from agno.run import RunContext


def set_stage(run_context: RunContext, stage: str) -> str:
    """Update the current workflow stage in session state."""
    allowed = {"browsing", "review", "submitted"}
    if stage not in allowed:
        return f"invalid stage; choose one of {sorted(allowed)}"
    run_context.session_state["stage"] = stage
    return stage
```

注意：

- 构造器的 `session_state` 是默认值，不是安全的全局“当前状态”；
- 工具必须从当前 `RunContext` 访问；
- 大型对象、连接、Secrets 不放 state；
- 并发更新同一 Session 需要版本号/锁/业务事务；
- 高频业务状态更适合业务 DB。

## 5. 自动 Memory：生产默认

```python
agent = Agent(
    db=db,
    update_memory_on_run=True,
)
```

官方生产建议通常优先该模式，因为记忆处理不占主对话的工具循环。仍会产生额外模型调用，因此要监控。

适合：

- 每轮结束抽取少量稳定信息；
- 用户不需要即时看到/控制本轮 memory tool；
- 希望对话主上下文更稳定。

## 6. Agentic Memory

```python
agent = Agent(
    db=db,
    enable_agentic_memory=True,
)
```

适合：

- 用户说“记住这个”“忘掉这个”；
- Agent 必须在当前对话中主动管理记忆；
- 需要复杂的 memory decision。

风险：每次 memory 操作可能触发嵌套 LLM 调用，并加载大量已有 memories。用户有 100+ memories 时，token 和延迟会显著增加。

不要同时开启：

```python
# 不推荐：agentic 会覆盖 automatic 的行为预期
Agent(
    update_memory_on_run=True,
    enable_agentic_memory=True,
)
```

## 7. MemoryManager

```python
from agno.memory import MemoryManager

memory_manager = MemoryManager(
    db=db,
    model=cheap_memory_model,
    additional_instructions=[
        "只保存跨数周仍有价值的稳定偏好。",
        "不要保存密码、token、精确住址、支付信息。",
        "临时情绪和一次性安排不保存为长期记忆。",
        "发现冲突偏好时更新而不是重复创建。",
    ],
)

agent = Agent(
    db=db,
    model=main_model,
    memory_manager=memory_manager,
    update_memory_on_run=True,
)
```

记忆模型可以更便宜，但要通过 precision/recall 和错误记忆率验证。

## 8. Memory 写入准则

建议保存：

- 用户明确要求记住的非敏感信息；
- 长期稳定偏好；
- 长期目标与约束；
- 产品需要跨 Session 延续且用户可理解的关系信息。

谨慎或不保存：

- 密码、API key、验证码；
- 支付卡、政府证件；
- 精确地址；
- 未经明确产品设计的健康、政治、宗教等敏感画像；
- 临时情绪、今天吃了什么等低价值噪音；
- 模型推断但用户未确认的身份属性；
- 完整聊天原文的重复副本。

## 9. Memory 维护

每个用户至少监控：

- memory count；
- 新增/更新/删除速率；
- memory LLM token 与延迟；
- 重复率、冲突率；
- 用户纠正率；
- 召回使用率；
- 过期与删除 SLA。

定期：

- 合并重复；
- 标记来源和更新时间；
- 淘汰过期信息；
- 对冲突信息保留最新确认版本；
- 提供查看、编辑、删除和导出能力。

## 10. Memory 评测

构造至少四组：

1. 应保存：明确长期偏好；
2. 不应保存：临时事实；
3. 应更新：用户改变偏好；
4. 应删除：用户要求忘记。

指标：

```text
memory extraction precision
memory extraction recall
duplicate rate
conflict resolution accuracy
deletion success
cross-session recall accuracy
cross-user leakage = 0
natural integration score
memory operation token/latency
```

## 11. 外部 Memory（例如 Mem0）

Agno 自带 Memory 与外部服务不要无计划双写，否则会出现：

- 两个来源冲突；
- 删除一边未删除另一边；
- 同一事实重复注入；
- user_id 命名空间不一致；
- 成本和延迟难以归因。

可选集成方式：

1. 将 Mem0 作为 Agent tools：添加、搜索、列出、删除；
2. 通过 Mem0 MCP 接入；
3. 自定义 Context Provider 在 run 前召回；
4. 用普通业务层统一管理，Agno Memory 关闭。

选择一种 memory source of truth。必须映射：

```text
app_user_id → external_memory_user_id
session_id  → external run/thread metadata
tenant_id   → namespace/filter
```

删除和导出要覆盖所有副本。

## 12. Learning

最小启用形态：

```python
agent = Agent(
    model=model,
    db=db,
    learning=True,
)
```

Learning 适合沉淀：

- 用户明确反馈的输出偏好；
- 某类任务的成功模板；
- 工具选择经验；
- 经评测确认的改进。

不要让未经审核的单次模型输出自动变成全局规则。区分：

- user-level learning；
- component-level learning；
- global/shared learning。

多租户环境必须明确 namespace 和审核流程。

## 13. AI 伴侣的建议边界

```text
Session history  → 最近对话，短期连贯
Session state    → 当前情绪状态、小游戏、当前话题、当日配额
Memory           → 用户长期偏好、重要关系事实、明确纪念日
Business DB      → 订阅、元气、语音时长、照片额度、Persona 配置
Knowledge        → 人设手册、产品规则、共享故事素材
Learning         → 经验证的交互偏好和成功策略
```

不要把订阅余额或配额写进 Memory；每次通过业务工具读取实时值。
