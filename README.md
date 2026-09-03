# agno-platform-engineer

这是一个面向 **Agno SDK 3.x + AgentOS** 的 Agent Skill。它不是一篇线性教程，而是一套供 Codex、Claude Code、Cursor、Agno Agent 或其他兼容 Agent Skills 的编码 Agent 渐进加载的工程手册。

## 内容

- `SKILL.md`：始终加载的决策规则、实施流程、默认值与高风险坑点。
- `references/`：按主题加载的详细说明与当前 API 示例。
- `templates/`：最小 Agent、Knowledge、Team、Workflow、Evals，以及完整生产 AgentOS 模板。
- `scripts/inspect_agno_project.py`：扫描版本、旧 API、实例生命周期、多用户与生产风险。
- `scripts/scaffold_agno_app.py`：复制生产模板并生成新项目。
- `scripts/validate_skill.py`：验证 Skill frontmatter、目录、引用、脚本与模板语法。

## 安装到兼容 Agent Skills 的编码 Agent

将整个目录复制到项目的 Skill 搜索目录，例如：

```text
<project>/.agents/skills/agno-platform-engineer/
```

不同宿主也可能使用自己的 Skills 目录；保持 `agno-platform-engineer/SKILL.md` 的层级不变。

建议同时为编码 Agent 配置 Agno 当前文档 MCP：

```text
https://docs.agno.com/mcp
```

示例配置见 `templates/agno-docs.mcp.json.example`。

## 在 Agno Agent 中加载

将本目录放进一个父级 `skills/` 目录，然后：

```python
from agno.agent import Agent
from agno.skills import LocalSkills, Skills

agent = Agent(
    model="openai:gpt-5.5",
    skills=Skills(loaders=[LocalSkills("/absolute/path/to/skills")]),
    instructions=[
        "遇到 Agno 平台开发任务时，先加载 agno-platform-engineer。",
        "只按需读取 reference，不要一次加载全部文件。",
    ],
)
```

也可以把同一个 `Skills` 实例传给 `Team(skills=...)`，让 Team leader 直接使用本 Skill。

## 先验证 Skill

```bash
cd agno-platform-engineer
python scripts/validate_skill.py .
```

## 新建一个生产模板

```bash
python scripts/scaffold_agno_app.py ../my-agent-platform
cd ../my-agent-platform
cp .env.example .env
uv sync
```

模板默认提供：

- 单个可复用 Agent；
- PostgreSQL 持久化；
- 可开关的自动用户记忆；
- JWT + `user_isolation` 的生产开关；
- REST/SSE 与可选 MCP；
- tracing；
- Pydantic 结构化输出；
- 只读工具与需确认的写工具示例；
- Docker Compose、HTTP 调用样例与 smoke tests。

## 版本基线

本 Skill 于 **2026-09-03** 依据 Agno 仓库 `main` 的 commit
`d829138ae9f28a0dd6967fdfae3c74de11501496` 编写；当时仓库
`libs/agno/pyproject.toml` 标记版本为 `3.0.5`。Agno 变化较快，实际项目应先运行检查脚本，并用官方文档 MCP 校准版本敏感 API。

## License

Apache-2.0。代码模板与 Skill 内容可在该许可证下复用。Agno 项目本身也采用 Apache-2.0；各模型、数据库、工具及服务仍受其各自许可证和服务条款约束。
