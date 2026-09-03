"""Agentic search over a local Knowledge collection.

Install:
    uv add 'agno[google]' chromadb
Set:
    export GOOGLE_API_KEY=...

Change DOCUMENT_PATH before running.
"""

from pathlib import Path

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.knowledge.embedder.google import GeminiEmbedder
from agno.knowledge.knowledge import Knowledge
from agno.models.google import Gemini
from agno.vectordb.chroma import ChromaDb
from agno.vectordb.search import SearchType


DOCUMENT_PATH = Path("docs/product.md")

contents_db = SqliteDb(
    id="knowledge-contents-db",
    db_file="tmp/knowledge-contents.db",
)

knowledge = Knowledge(
    name="Product Documentation",
    contents_db=contents_db,
    max_results=5,
    vector_db=ChromaDb(
        name="product_docs",
        collection="product_docs_v1",
        path="tmp/chroma",
        persistent_client=True,
        search_type=SearchType.hybrid,
        embedder=GeminiEmbedder(id="gemini-embedding-001"),
    ),
)

assistant = Agent(
    id="product-docs-agent",
    model=Gemini(id="gemini-3.6-flash"),
    knowledge=knowledge,
    search_knowledge=True,
    instructions=[
        "Search Knowledge before answering product-documentation questions.",
        "Answer only from retrieved evidence and say when evidence is insufficient.",
        "Keep source identifiers in the answer.",
    ],
    markdown=True,
)


if __name__ == "__main__":
    if not DOCUMENT_PATH.exists():
        raise SystemExit(f"Create {DOCUMENT_PATH} before running this example")

    knowledge.insert(name="Product Docs", path=str(DOCUMENT_PATH))
    assistant.print_response("Summarize the product's main capability.", stream=True)
