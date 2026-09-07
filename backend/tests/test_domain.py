"""Unit tests for the pure domain rules - no database, no network."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models import ConversationMember, Message, MessageType
from app.services.conversation_service import (
    _decode_cursor,
    _encode_cursor,
    dm_key_for,
)
from app.services.rate_limit import SlidingWindowLimiter
from app.services.serializers import message_status, preview_text, receipt_counts


def member(user_id: str, read: int = 0, delivered: int = 0) -> ConversationMember:
    return ConversationMember(
        conversation_id="c1",
        user_id=user_id,
        last_read_seq=read,
        last_delivered_seq=delivered,
    )


def message(seq: int, sender: str = "u1", **kwargs) -> Message:
    return Message(
        conversation_id="c1", sender_id=sender, seq=seq, type=MessageType.TEXT, **kwargs
    )


class TestDmKey:
    def test_is_order_independent(self):
        assert dm_key_for("bbb", "aaa") == dm_key_for("aaa", "bbb")

    def test_is_stable(self):
        assert dm_key_for("aaa", "bbb") == "aaa:bbb"


class TestReceipts:
    def test_sender_is_never_their_own_recipient(self):
        members = [member("u1", read=5, delivered=5), member("u2")]
        recipients, delivered, read = receipt_counts(message(5), members)
        assert (recipients, delivered, read) == (1, 0, 0)

    def test_high_water_mark_covers_earlier_messages(self):
        # u2 has read up to seq 10, so every message at or below 10 is read.
        members = [member("u1"), member("u2", read=10, delivered=10)]
        for seq in (1, 5, 10):
            _, _, read = receipt_counts(message(seq), members)
            assert read == 1, seq
        _, _, read = receipt_counts(message(11), members)
        assert read == 0

    def test_group_status_needs_every_recipient(self):
        members = [member("u1"), member("u2", read=7, delivered=7), member("u3", delivered=7)]
        recipients, delivered, read = receipt_counts(message(7), members)
        assert (recipients, delivered, read) == (2, 2, 1)
        # Delivered to both, read by only one -> double tick, not blue.
        assert message_status(recipients, delivered, read) == "delivered"

    @pytest.mark.parametrize(
        "recipients,delivered,read,expected",
        [
            (0, 0, 0, "sent"),
            (1, 0, 0, "sent"),
            (1, 1, 0, "delivered"),
            (1, 1, 1, "read"),
            (3, 3, 3, "read"),
            (3, 3, 2, "delivered"),
        ],
    )
    def test_status_ladder(self, recipients, delivered, read, expected):
        assert message_status(recipients, delivered, read) == expected


class TestPreview:
    def test_deleted_message_shows_a_tombstone(self):
        msg = message(1, content="secret")
        msg.deleted_at = datetime.now(UTC)
        assert preview_text(msg) == "This message was deleted"

    def test_long_text_is_truncated(self):
        assert len(preview_text(message(1, content="x" * 500))) == 140

    def test_image_preview(self):
        msg = message(1)
        msg.type = MessageType.IMAGE
        assert preview_text(msg) == "Photo"


class TestCursor:
    def test_round_trips(self):
        now = datetime.now(UTC)
        encoded = _encode_cursor(now, "conv-1")
        decoded_ts, decoded_id = _decode_cursor(encoded)
        assert decoded_id == "conv-1"
        assert decoded_ts == now

    def test_rejects_garbage(self):
        from app.core.errors import ValidationError

        with pytest.raises(ValidationError):
            _decode_cursor("not-a-cursor!!")


class TestRateLimiter:
    def test_allows_up_to_the_limit_then_blocks(self):
        limiter = SlidingWindowLimiter(limit=3, window_seconds=60)
        assert [limiter.allow("u1") for _ in range(4)] == [True, True, True, False]

    def test_is_per_key(self):
        limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
        assert limiter.allow("u1") is True
        assert limiter.allow("u2") is True
        assert limiter.allow("u1") is False
