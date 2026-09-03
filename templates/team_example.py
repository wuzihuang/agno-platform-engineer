"""A small Team with opposing specialist roles.

Install:
    uv add 'agno[openai]'
"""

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIResponses
from agno.team import Team


db = SqliteDb(id="team-db", db_file="tmp/team.db")
member_model = OpenAIResponses(id="gpt-5.5")

proponent = Agent(
    id="proposal-proponent",
    name="Proponent",
    role="Find the strongest evidence for the proposal",
    model=member_model,
    instructions="Separate evidence from assumptions.",
)

critic = Agent(
    id="proposal-critic",
    name="Critic",
    role="Find risks, missing evidence, and counterexamples",
    model=member_model,
    instructions="Be specific and do not invent facts.",
)

review_team = Team(
    id="proposal-review-team",
    name="Proposal Review Team",
    model=OpenAIResponses(id="gpt-5.5"),
    members=[proponent, critic],
    db=db,
    instructions=[
        "Ask both members to analyze the supplied proposal independently.",
        "Synthesize agreements, disagreements, unknowns, and a recommendation.",
    ],
    show_members_responses=True,
    markdown=True,
)


if __name__ == "__main__":
    review_team.print_response(
        "Evaluate a proposal to replace a support form with an AI assistant.",
        stream=True,
    )
