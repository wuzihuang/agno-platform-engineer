"""Human-in-the-loop tool confirmation.

Install:
    uv add 'agno[openai]'

The first run pauses before the tool executes. A production client should
persist run_id/session_id/requirements and resolve them through AgentOS.
"""

from agno.agent import Agent
from agno.models.openai import OpenAIResponses
from agno.tools import tool


@tool(requires_confirmation=True)
def delete_draft(draft_id: str) -> str:
    """Delete one draft after the user confirms the exact draft ID."""
    # Replace with an idempotent business-service call.
    return f"Deleted draft {draft_id}"


assistant = Agent(
    id="hitl-assistant",
    model=OpenAIResponses(id="gpt-5.5"),
    tools=[delete_draft],
    instructions=[
        "Use delete_draft only when the user explicitly asks to delete a draft.",
        "Before the tool call, explain which draft will be deleted.",
    ],
)


if __name__ == "__main__":
    run = assistant.run(
        "Delete draft draft_123.",
        user_id="demo-user",
        session_id="demo-hitl-session",
    )
    print(run)
    print("Active requirements:", run.active_requirements)
