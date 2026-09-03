"""Load this Skill into an Agno Agent.

The path supplied to LocalSkills is the PARENT directory containing the
agno-platform-engineer folder.
"""

from pathlib import Path

from agno.agent import Agent
from agno.models.openai import OpenAIResponses
from agno.skills import LocalSkills, Skills


SKILLS_PARENT = Path(__file__).resolve().parents[1]
skills = Skills(loaders=[LocalSkills(str(SKILLS_PARENT))])

engineering_agent = Agent(
    id="agno-engineer",
    model=OpenAIResponses(id="gpt-5.5"),
    skills=skills,
    instructions=[
        "For Agno platform work, load agno-platform-engineer first.",
        "Read only references needed for the current task.",
        "Verify version-sensitive APIs against the installed Agno version.",
    ],
)


if __name__ == "__main__":
    engineering_agent.print_response(
        "Design a production AgentOS service for 10,000 users.",
        stream=True,
    )
