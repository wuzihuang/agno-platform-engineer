"""Agent with a typed Pydantic output.

Install:
    uv add 'agno[openai]'
"""

from typing import Literal

from agno.agent import Agent
from agno.models.openai import OpenAIResponses
from pydantic import BaseModel, Field


class TriageResult(BaseModel):
    category: Literal["billing", "technical", "account", "other"]
    urgency: Literal["low", "normal", "high"]
    summary: str = Field(min_length=1, max_length=240)
    needs_human: bool
    next_action: str = Field(min_length=1, max_length=240)


triage_agent = Agent(
    id="support-triage",
    name="Support Triage",
    model=OpenAIResponses(id="gpt-5.5"),
    instructions=[
        "Classify only from the user's message.",
        "Use needs_human=true for security, payment disputes, or uncertain high-impact cases.",
        "Do not invent account facts.",
    ],
    output_schema=TriageResult,
)


if __name__ == "__main__":
    run = triage_agent.run("I was charged twice and need someone to investigate.")
    result: TriageResult = run.content
    print(result.model_dump_json(indent=2))
