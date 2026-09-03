"""Minimal Agno Agent.

Install:
    uv add 'agno[openai]'
Set:
    export OPENAI_API_KEY=...
Run:
    uv run python minimal_agent.py
"""

from agno.agent import Agent
from agno.models.openai import OpenAIResponses


assistant = Agent(
    id="minimal-assistant",
    name="Minimal Assistant",
    model=OpenAIResponses(id="gpt-5.5"),
    instructions=[
        "Lead with the answer.",
        "State uncertainty and never invent missing facts.",
    ],
    markdown=True,
)


if __name__ == "__main__":
    assistant.print_response("Explain Agno in three sentences.", stream=True)
