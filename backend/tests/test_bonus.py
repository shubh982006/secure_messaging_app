"""Attachments and disappearing messages."""

from __future__ import annotations

import asyncio
import io
import uuid

import pytest

from tests.conftest import register

pytestmark = pytest.mark.asyncio

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000100ffff0300000600"
    "05570c2f0000000049454e44ae426082"
)


@pytest.fixture
async def pair(client):
    alice = await register(client, "+919999900601", "Alice")
    bob = await register(client, "+919999900602", "Bob")
    conversation = (await client.post(
        "/api/v1/conversations",
        json={"type": "direct", "user_id": bob["id"]},
        headers=alice["headers"],
    )).json()
    return alice, bob, conversation


class TestAttachments:
    async def test_upload_returns_usable_metadata(self, client, pair, tmp_path, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "media_root", str(tmp_path))
        alice, _bob, _conversation = pair

        response = await client.post(
            "/api/v1/attachments",
            files={"file": ("photo.png", io.BytesIO(PNG_1PX), "image/png")},
            data={"width": "1", "height": "1"},
            headers=alice["headers"],
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["kind"] == "image"
        assert body["mime_type"] == "image/png"
        assert body["size_bytes"] == len(PNG_1PX)
        assert body["url"].startswith("/media/")
        # The client's filename must never become the stored path.
        assert "photo.png" not in body["url"]
        assert body["name"] == "photo.png"

    async def test_disallowed_type_is_refused(self, client, pair, tmp_path, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "media_root", str(tmp_path))
        alice, _bob, _conversation = pair

        response = await client.post(
            "/api/v1/attachments",
            files={"file": ("evil.sh", io.BytesIO(b"#!/bin/sh\nrm -rf /"), "application/x-sh")},
            headers=alice["headers"],
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

    async def test_oversized_upload_is_refused(self, client, pair, tmp_path, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "media_root", str(tmp_path))
        monkeypatch.setattr(settings, "max_upload_bytes", 1024)
        alice, _bob, _conversation = pair

        response = await client.post(
            "/api/v1/attachments",
            files={"file": ("big.png", io.BytesIO(b"x" * 4096), "image/png")},
            headers=alice["headers"],
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "FILE_TOO_LARGE"

    async def test_upload_requires_auth(self, client, tmp_path, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "media_root", str(tmp_path))
        response = await client.post(
            "/api/v1/attachments",
            files={"file": ("photo.png", io.BytesIO(PNG_1PX), "image/png")},
        )
        assert response.status_code == 401

    async def test_message_carries_its_attachments(self, client, pair):
        alice, _bob, conversation = pair
        sent = (await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={
                "type": "image",
                "content": "look at this",
                "client_msg_id": str(uuid.uuid4()),
                "attachments": [
                    {
                        "url": "/media/abc123.png",
                        "name": "photo.png",
                        "mime_type": "image/png",
                        "size_bytes": 512,
                        "width": 800,
                        "height": 600,
                    }
                ],
            },
            headers=alice["headers"],
        )).json()

        assert sent["type"] == "image"
        assert len(sent["attachments"]) == 1
        assert sent["attachments"][0]["width"] == 800

        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=alice["headers"],
        )).json()
        attachment = page["messages"][0]["attachments"][0]
        assert attachment["url"] == "/media/abc123.png"
        assert attachment["name"] == "photo.png"

    async def test_deleting_a_message_hides_its_attachments(self, client, pair):
        alice, _bob, conversation = pair
        sent = (await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={
                "type": "image",
                "content": "oops",
                "client_msg_id": str(uuid.uuid4()),
                "attachments": [{"url": "/media/x.png", "mime_type": "image/png"}],
            },
            headers=alice["headers"],
        )).json()

        await client.delete(f"/api/v1/messages/{sent['id']}", headers=alice["headers"])
        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=alice["headers"],
        )).json()
        assert page["messages"][0]["attachments"] == []


class TestDisappearingMessages:
    async def test_off_by_default(self, client, pair):
        _alice, _bob, conversation = pair
        assert conversation["disappear_seconds"] == 0

    async def test_any_member_can_set_the_window(self, client, pair):
        _alice, bob, conversation = pair
        response = await client.patch(
            f"/api/v1/conversations/{conversation['id']}",
            json={"disappear_seconds": 86400},
            headers=bob["headers"],
        )
        assert response.status_code == 200
        assert response.json()["disappear_seconds"] == 86400

    async def test_change_is_announced_in_the_thread(self, client, pair):
        alice, _bob, conversation = pair
        await client.patch(
            f"/api/v1/conversations/{conversation['id']}",
            json={"disappear_seconds": 86400},
            headers=alice["headers"],
        )
        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=alice["headers"],
        )).json()
        system = [m for m in page["messages"] if m["type"] == "system"]
        assert system[-1]["content"] == "Alice set disappearing messages to 1 day"

        await client.patch(
            f"/api/v1/conversations/{conversation['id']}",
            json={"disappear_seconds": 0},
            headers=alice["headers"],
        )
        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=alice["headers"],
        )).json()
        assert page["messages"][-1]["content"] == "Alice turned off disappearing messages"

    async def test_new_messages_get_an_expiry(self, client, pair):
        alice, _bob, conversation = pair
        await client.patch(
            f"/api/v1/conversations/{conversation['id']}",
            json={"disappear_seconds": 3600},
            headers=alice["headers"],
        )
        sent = (await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"type": "text", "content": "self destructs", "client_msg_id": str(uuid.uuid4())},
            headers=alice["headers"],
        )).json()
        assert sent["expires_at"] is not None

    async def test_expired_messages_vanish_from_history(self, client, pair):
        alice, bob, conversation = pair
        # One second window so the test does not have to wait.
        await client.patch(
            f"/api/v1/conversations/{conversation['id']}",
            json={"disappear_seconds": 1},
            headers=alice["headers"],
        )
        await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"type": "text", "content": "gone shortly", "client_msg_id": str(uuid.uuid4())},
            headers=alice["headers"],
        )

        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=bob["headers"],
        )).json()
        assert any(m["content"] == "gone shortly" for m in page["messages"])

        await asyncio.sleep(1.2)

        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=bob["headers"],
        )).json()
        # Filtered at query time - correctness never waits on the sweeper.
        assert not any(m["content"] == "gone shortly" for m in page["messages"])

    async def test_sweeper_hard_deletes_expired_rows(self, client, pair, session_factory):
        from sqlalchemy import func, select

        from app.models import Message
        from app.services.message_service import purge_expired_messages

        alice, _bob, conversation = pair
        await client.patch(
            f"/api/v1/conversations/{conversation['id']}",
            json={"disappear_seconds": 1},
            headers=alice["headers"],
        )
        await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"type": "text", "content": "temporary", "client_msg_id": str(uuid.uuid4())},
            headers=alice["headers"],
        )
        await asyncio.sleep(1.2)

        async with session_factory() as db:
            before = await db.scalar(select(func.count()).select_from(Message))
            removed = await purge_expired_messages(db)
            after = await db.scalar(select(func.count()).select_from(Message))

        assert removed == 1
        assert after == before - 1

    async def test_existing_messages_are_not_retroactively_expired(self, client, pair):
        alice, _bob, conversation = pair
        await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"type": "text", "content": "sent before the timer", "client_msg_id": str(uuid.uuid4())},
            headers=alice["headers"],
        )
        await client.patch(
            f"/api/v1/conversations/{conversation['id']}",
            json={"disappear_seconds": 1},
            headers=alice["headers"],
        )
        await asyncio.sleep(1.2)

        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=alice["headers"],
        )).json()
        assert any(m["content"] == "sent before the timer" for m in page["messages"])
