"""Agno client for a vLLM OpenAI-compatible server.

Set:
    export VLLM_BASE_URL=http://localhost:8000/v1/
    export VLLM_API_KEY=local-token
    export VLLM_MODEL_ID=Qwen/Qwen2.5-7B-Instruct

The served model name must match VLLM_MODEL_ID. Tool calling additionally
requires a compatible model, chat template, and vLLM tool-call parser.
"""

import os

from agno.agent import Agent
from agno.models.vllm import VLLM


model_id = os.getenv("VLLM_MODEL_ID", "Qwen/Qwen2.5-7B-Instruct")

assistant = Agent(
    id="local-vllm-assistant",
    model=VLLM(
        id=model_id,
        base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1/"),
        api_key=os.getenv("VLLM_API_KEY", "local-token"),
        enable_thinking=False,
    ),
    instructions="Answer concisely and do not invent facts.",
    markdown=True,
)


if __name__ == "__main__":
    assistant.print_response("Explain KV cache in two paragraphs.", stream=True)
