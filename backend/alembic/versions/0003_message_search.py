"""message full-text search

Dialect-aware on purpose: SQLite gets an FTS5 virtual table kept in sync by
triggers, Postgres gets a GIN index over to_tsvector. Both are real inverted
indexes; neither is a LIKE scan. One migration handles both, which is what keeps
"SQLite now, Postgres later" a config change rather than a fork.

Revision ID: 0003_message_search
Revises: 0002_attachments_disappearing
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa

import app.db.base  # noqa: F401  (custom UTCDateTime column type)
from app.db.search_index import statements_for

revision = "0003_message_search"
down_revision = "0002_attachments_disappearing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in statements_for(op.get_bind().dialect.name, up=True):
        op.execute(sa.text(statement))


def downgrade() -> None:
    for statement in statements_for(op.get_bind().dialect.name, up=False):
        op.execute(sa.text(statement))
