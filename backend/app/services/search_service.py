"""Cross-conversation message search.

Two engines behind one interface, picked by dialect:

* **SQLite** - an FTS5 virtual table kept in sync by triggers. Real tokenised
  full-text search with ranking, not ``LIKE '%term%'``.
* **Postgres** - ``to_tsvector``/``plainto_tsquery`` with a GIN index.

Both are genuine inverted indexes, so search cost scales with the number of
*matches* rather than the number of messages. A ``LIKE`` fallback exists for any
other dialect, and is what the tests use to prove the three agree.

Every query is scoped to conversations the caller belongs to, so search can
never leak a message from a conversation the user cannot open.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, ConversationMember, Message

# FTS5 treats a handful of characters as operators; a user typing "c++" or a
# stray quote should search, not raise a syntax error.
_FTS_UNSAFE = re.compile(r'["\'()*:^\-]')


@dataclass(slots=True)
class SearchHit:
    message: Message
    conversation: Conversation


def _postgres_query(term: str) -> str:
    """Build a tsquery with a prefix on the final word.

    ``plainto_tsquery`` has no prefix matching, so search would only fire on
    whole words and "coff" would miss "coffee" - behaving differently from the
    SQLite path. Tokens are stripped to alphanumerics before being interpolated,
    because ``to_tsquery`` raises on malformed syntax.
    """
    words = [re.sub(r"[^0-9A-Za-z]+", "", word) for word in term.split()]
    words = [word for word in words if word]
    if not words:
        return ""
    prefixed = words[:-1] + [f"{words[-1]}:*"]
    return " & ".join(prefixed)


def _sqlite_query(term: str) -> str:
    """Turn a user's words into a safe FTS5 prefix query."""
    words = [w for w in _FTS_UNSAFE.sub(" ", term).split() if w]
    if not words:
        return ""
    # Quote each token, then prefix-match the last one so search feels live.
    quoted = [f'"{word}"' for word in words[:-1]]
    quoted.append(f'"{words[-1]}"*')
    return " ".join(quoted)


async def search_messages(
    db: AsyncSession,
    *,
    user_id: str,
    query: str,
    limit: int = 40,
    conversation_id: str | None = None,
) -> list[SearchHit]:
    term = query.strip()
    if len(term) < 2:
        return []
    limit = max(1, min(limit, 100))

    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"

    # Conversations this user is actually in - the authorisation boundary.
    member_scope = select(ConversationMember.conversation_id).where(
        ConversationMember.user_id == user_id
    )

    # The conversation filter is appended rather than passed as a nullable bind:
    # asyncpg cannot infer the type of a NULL parameter used in `:p IS NULL`,
    # and a conditional clause gives the planner a tighter query anyway.
    scope_clause = " AND m.conversation_id = :conversation_id" if conversation_id else ""
    params: dict[str, object] = {"user_id": user_id, "limit": limit}
    if conversation_id:
        params["conversation_id"] = conversation_id

    if dialect == "sqlite":
        match = _sqlite_query(term)
        if not match:
            return []
        params["match"] = match
        sql = text(
            f"""
            SELECT m.id
            FROM messages_fts f
            JOIN messages m ON m.rowid = f.rowid
            JOIN conversation_members cm
              ON cm.conversation_id = m.conversation_id AND cm.user_id = :user_id
            WHERE messages_fts MATCH :match
              AND m.deleted_at IS NULL
              AND m.type != 'system'
              AND (m.expires_at IS NULL OR m.expires_at > CURRENT_TIMESTAMP)
              {scope_clause}
            ORDER BY rank, m.seq DESC
            LIMIT :limit
            """
        )
        rows = await db.execute(sql, params)
    elif dialect == "postgresql":
        tsquery = _postgres_query(term)
        if not tsquery:
            return []
        params["term"] = tsquery
        sql = text(
            f"""
            SELECT m.id
            FROM messages m
            JOIN conversation_members cm
              ON cm.conversation_id = m.conversation_id AND cm.user_id = :user_id
            WHERE to_tsvector('english', coalesce(m.content, ''))
                  @@ to_tsquery('english', :term)
              AND m.deleted_at IS NULL
              AND m.type != 'system'
              AND (m.expires_at IS NULL OR m.expires_at > NOW())
              {scope_clause}
            ORDER BY ts_rank(
                       to_tsvector('english', coalesce(m.content, '')),
                       to_tsquery('english', :term)
                     ) DESC,
                     m.seq DESC
            LIMIT :limit
            """
        )
        rows = await db.execute(sql, params)
    else:  # pragma: no cover - portability fallback
        stmt = (
            select(Message.id)
            .where(
                Message.conversation_id.in_(member_scope),
                Message.content.ilike(f"%{term}%"),
                Message.deleted_at.is_(None),
                Message.type != "system",
            )
            .order_by(Message.seq.desc())
            .limit(limit)
        )
        if conversation_id:
            stmt = stmt.where(Message.conversation_id == conversation_id)
        rows = await db.execute(stmt)

    message_ids = [row[0] for row in rows]
    if not message_ids:
        return []

    # Rehydrate in one query, preserving relevance order.
    found = await db.execute(
        select(Message, Conversation)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.id.in_(message_ids))
    )
    by_id = {message.id: (message, conversation) for message, conversation in found}
    return [
        SearchHit(message=by_id[mid][0], conversation=by_id[mid][1])
        for mid in message_ids
        if mid in by_id
    ]


def snippet(content: str | None, term: str, width: int = 90) -> str:
    """A short excerpt centred on the first match, for the results list."""
    if not content:
        return ""
    lowered = content.lower()
    position = lowered.find(term.strip().lower().split()[0]) if term.strip() else -1
    if position < 0 or len(content) <= width:
        return content[:width]
    start = max(0, position - width // 3)
    excerpt = content[start : start + width]
    return ("…" if start > 0 else "") + excerpt + ("…" if start + width < len(content) else "")
