"""A deterministic sequential Workflow.

Install:
    uv add 'agno[openai]'
"""

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIResponses
from agno.workflow import Step, Workflow


db = SqliteDb(id="workflow-db", db_file="tmp/workflow.db")
model = OpenAIResponses(id="gpt-5.5")

extractor = Agent(
    id="requirements-extractor",
    model=model,
    instructions="Extract requirements, constraints, and unresolved questions only.",
)
reviewer = Agent(
    id="requirements-reviewer",
    model=model,
    instructions="Find contradictions and risky assumptions in the supplied requirements.",
)
writer = Agent(
    id="plan-writer",
    model=model,
    instructions="Produce a concise implementation plan from the supplied analysis.",
    markdown=True,
)

workflow = Workflow(
    id="requirements-plan-workflow",
    name="Requirements Plan Workflow",
    db=db,
    steps=[
        Step(name="Extract", agent=extractor),
        Step(name="Review", agent=reviewer),
        Step(name="Write Plan", agent=writer),
    ],
)


if __name__ == "__main__":
    workflow.print_response(
        "Build a multi-user support agent with durable sessions and strict tenant isolation.",
        stream=True,
    )
