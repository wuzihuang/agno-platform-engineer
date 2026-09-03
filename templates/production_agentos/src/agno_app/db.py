"""Shared database objects.

Create these once at module/application scope. Do not create a database or
connection pool inside a request handler.
"""

from agno.db.postgres import PostgresDb

from agno_app.settings import settings


db = PostgresDb(
    id="agent-platform-db",
    db_url=settings.database_url,
)
