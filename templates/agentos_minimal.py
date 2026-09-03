"""Serve a persistent Agent through AgentOS.

Install:
    uv add 'agno[os,openai]'
Run:
    uv run python agentos_minimal.py
Open:
    http://localhost:7777/docs
"""

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIResponses
from agno.os import AgentOS


db = SqliteDb(id="agentos-db", db_file="tmp/agentos.db")
assistant = Agent(
    id="assistant",
    model=OpenAIResponses(id="gpt-5.5"),
    db=db,
    add_history_to_context=True,
    num_history_runs=5,
)

agent_os = AgentOS(
    id="minimal-agent-os",
    db=db,
    agents=[assistant],
    tracing=True,
)
app = agent_os.get_app()


if __name__ == "__main__":
    agent_os.serve(app="agentos_minimal:app", reload=True)
