"""Full-text search index DDL, shared by the migration and create_all.

Alembic owns the schema in production, but the test suite and the create_all
fallback build tables straight from the metadata - and an FTS5 virtual table
plus its triggers is not something SQLAlchemy metadata can express. Keeping the
statements here means both paths get an identical index instead of search
working in production and silently degrading in tests.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

SQLITE_UP = [
    # `content=` makes this an external-content table: FTS5 stores the index
    # only, not a second copy of every message body.
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
    USING fts5(content, content='messages', content_rowid='rowid')
    """,
    """
    CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages
    BEGIN
        INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
    END
    """,
    # A 'delete' row is how an external-content FTS5 table retracts a document.
    """
    CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages
    BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content)
        VALUES ('delete', old.rowid, old.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages
    BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content)
        VALUES ('delete', old.rowid, old.content);
        INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
    END
    """,
    "INSERT INTO messages_fts(rowid, content) SELECT rowid, content FROM messages",
]

SQLITE_DOWN = [
    "DROP TRIGGER IF EXISTS messages_fts_update",
    "DROP TRIGGER IF EXISTS messages_fts_delete",
    "DROP TRIGGER IF EXISTS messages_fts_insert",
    "DROP TABLE IF EXISTS messages_fts",
]

POSTGRES_UP = [
    """
    CREATE INDEX IF NOT EXISTS idx_messages_content_fts
    ON messages
    USING GIN (to_tsvector('english', coalesce(content, '')))
    """,
]

POSTGRES_DOWN = ["DROP INDEX IF EXISTS idx_messages_content_fts"]


def statements_for(dialect: str, *, up: bool = True) -> list[str]:
    if dialect == "sqlite":
        return SQLITE_UP if up else SQLITE_DOWN
    if dialect == "postgresql":
        return POSTGRES_UP if up else POSTGRES_DOWN
    return []  # other dialects fall back to a LIKE scan in search_service


def ensure_search_index(connection: Connection) -> None:
    """Idempotent; safe to run on every boot."""
    for statement in statements_for(connection.dialect.name):
        connection.execute(text(statement))
