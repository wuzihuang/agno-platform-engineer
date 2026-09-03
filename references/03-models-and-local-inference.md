# 模型、网关与本地推理

## 1. 模型选择先看能力，不只看榜单

建立能力矩阵：

| 能力 | 是否必须 | 验证方式 |
|---|---:|---|
| Tool calling | Agent 有工具时必须 | reliability eval：工具名与参数 |
| Streaming | 聊天 UI 常需 | 首 token、断线、取消测试 |
| Structured output | 程序消费时必须 | schema pass rate |
| Multimodal | 有图/音/视频时 | 每种媒体真实样本 |
| Long context | 长文/历史时 | 有效召回而非只看标称长度 |
| Reasoning | 复杂计划可选 | 质量收益/成本/延迟对比 |
| Async client | 服务端推荐 | 并发压测 |
| Retry/timeout | 生产必须 | 故障注入 |

不要假设同一 provider 的所有模型都支持相同功能。

## 2. 显式模型对象

生产代码建议显式类而不是只用字符串，以便配置 timeout、retry、base URL：

```python
from agno.models.openai import OpenAIResponses

model = OpenAIResponses(
    id="gpt-5.5",
    timeout=60,
    max_retries=2,
)
```

参数名随 provider adapter 可能不同，查询对应 reference。将模型 ID 放环境变量：

```python
import os

MODEL_ID = os.environ["AGNO_MODEL_ID"]
```

不要写“默认模型一定可用”。模型 ID、价格和能力会变化。

## 3. Model-as-string

原型可以：

```python
agent = Agent(model="openai:gpt-5.5")
```

优点是简洁；缺点是高级 client 配置、IDE 类型提示和 provider 特有能力不如显式对象清楚。生产模板默认显式对象。

## 4. vLLM

### 服务端

工具调用必须同时满足：

1. 模型经过 function/tool calling 训练；
2. vLLM 启用 auto tool choice；
3. 选择适配模型的 tool-call parser；
4. chat template 能正确表达 tools；
5. Agno adapter 与模型 ID 指向同一 served model。

官方示例形态：

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --dtype float16 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.9
```

这只是示例。Qwen、Llama、Mistral 等可能需要不同 parser/template；以模型和当前 vLLM 文档为准。

### Agno 客户端

```python
import os

from agno.agent import Agent
from agno.models.vllm import VLLM

model = VLLM(
    id=os.environ["VLLM_MODEL_ID"],
    base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1/"),
    api_key=os.getenv("VLLM_API_KEY", "local"),
)

agent = Agent(id="local-agent", model=model)
```

当前 adapter 默认读取 `VLLM_API_KEY`，即使服务端未设置 API key，也可给一个占位值。

### 部署验证

先直接检查模型服务器：

```bash
curl -fsS http://localhost:8000/v1/models
```

再做三层测试：

1. 纯文本回答；
2. 单工具、严格参数；
3. 多工具与错误修复。

不要在第 1 层成功后直接开放支付、删除、发消息等写工具。

## 5. 任意 OpenAI-compatible endpoint

```python
import os

from agno.models.openai.like import OpenAILike

model = OpenAILike(
    id=os.environ["MODEL_ID"],
    base_url=os.environ["OPENAI_COMPATIBLE_BASE_URL"],
    api_key=os.environ["OPENAI_COMPATIBLE_API_KEY"],
)
```

如果 provider 实现 Open Responses API，可使用 `OpenResponses`。不要混淆 Chat Completions compatible 与 Responses compatible；工具、stream event 和 structured output 可能不同。

## 6. Ollama、LM Studio、llama.cpp

Agno 有相应 local provider adapter。选择原则：

- 桌面开发：Ollama/LM Studio 简单；
- GGUF/CPU 或小规模本地：llama.cpp；
- GPU 高吞吐服务：vLLM；
- 已有统一 OpenAI-compatible 网关：OpenAILike。

生产时不要把桌面 UI 进程当高可用推理服务。

## 7. 主模型、记忆模型、压缩模型、评测模型分层

```text
Main model       → 用户回答与工具决策
Memory model     → 记忆提取/合并，通常可更便宜
Compression model→ 工具结果压缩
Evaluator model  → 离线/抽样评分，尽量与被评模型解耦
Embedding model  → Knowledge 向量，版本必须稳定
```

这些模型可以不同，但必须分别监控成本与失败。Embedding 变更通常需要重建索引，不能像聊天模型一样直接热切换。

## 8. Fallback 设计

可接受：

```text
Primary 同 provider 高质量模型
  ↓ rate limit / provider error
Backup 同能力模型
```

高风险：

```text
Primary 支持严格 structured output + tools
  ↓
Backup 只支持普通文本
```

Fallback 前检查：

- tool calling 格式；
- structured output；
- multimodal；
- context length；
- system prompt 支持；
- safety behavior；
- 数据驻留和合规。

## 9. 超时与重试分层

```text
HTTP connect timeout     短
HTTP read timeout        根据模型 SLA
Provider retry           1–2 次，处理 429/5xx
Agent tool retry         只处理可恢复参数错误
Workflow retry           节点级，并记录 attempt
Business write retry     仅幂等或带幂等键
```

避免每一层都重试 3 次造成指数放大。

## 10. 模型上线门槛

至少跑：

- 50–100 条代表性对话；
- 20+ 条必须调用工具的 case；
- 20+ 条禁止调用工具的 case；
- 参数边界、空值、中文、长文本；
- 3–10 并发和目标上下文长度；
- 断流、429、5xx、超时；
- structured output schema pass rate；
- 不同用户和 Session 隔离；
- 单轮 token、TTFT、总时长、成本。
