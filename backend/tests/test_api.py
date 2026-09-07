"""API-level tests driven through the real ASGI app."""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import register

pytestmark = pytest.mark.asyncio


class TestAuth:
    async def test_otp_flow_creates_a_user(self, client):
        response = await client.post(
            "/api/v1/auth/request-otp", json={"phone_number": "+919999911111"}
        )
        assert response.status_code == 200
        assert response.json()["mocked_code"] == "123456"

        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": "+919999911111", "code": "123456"},
        )
        body = response.json()
        assert body["is_new_user"] is True
        assert body["user"]["phone_number"] == "+919999911111"

        # Second login is not a new user.
        await client.post("/api/v1/auth/request-otp", json={"phone_number": "+919999911111"})
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": "+919999911111", "code": "123456"},
        )
        assert response.json()["is_new_user"] is False

    async def test_phone_numbers_are_normalised(self, client):
        await client.post("/api/v1/auth/request-otp", json={"phone_number": "91 99999 22222"})
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": "+919999922222", "code": "123456"},
        )
        assert response.status_code == 200

    async def test_protected_route_requires_a_token(self, client):
        response = await client.get("/api/v1/conversations")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    async def test_error_envelope_shape(self, client):
        response = await client.get("/api/v1/conversations")
        assert set(response.json()["error"]) == {"code", "message", "detail"}


class TestConversations:
    async def test_direct_conversation_is_get_or_create(self, client):
        alice = await register(client, "+919999900101", "Alice")
        bob = await register(client, "+919999900102", "Bob")

        first = await client.post(
            "/api/v1/conversations",
            json={"type": "direct", "user_id": bob["id"]},
            headers=alice["headers"],
        )
        second = await client.post(
            "/api/v1/conversations",
            json={"type": "direct", "user_id": alice["id"]},
            headers=bob["headers"],
        )
        assert first.status_code == 201
        assert first.json()["id"] == second.json()["id"]

    async def test_cannot_dm_yourself(self, client):
        alice = await register(client, "+919999900103", "Alice")
        response = await client.post(
            "/api/v1/conversations",
            json={"type": "direct", "user_id": alice["id"]},
            headers=alice["headers"],
        )
        assert response.status_code == 400

    async def test_list_is_sorted_by_recent_activity(self, client):
        alice = await register(client, "+919999900104", "Alice")
        bob = await register(client, "+919999900105", "Bob")
        carol = await register(client, "+919999900106", "Carol")

        with_bob = (await client.post(
            "/api/v1/conversations",
            json={"type": "direct", "user_id": bob["id"]},
            headers=alice["headers"],
        )).json()
        with_carol = (await client.post(
            "/api/v1/conversations",
            json={"type": "direct", "user_id": carol["id"]},
            headers=alice["headers"],
        )).json()

        await client.post(
            f"/api/v1/conversations/{with_bob['id']}/messages",
            json={"type": "text", "content": "hi bob", "client_msg_id": str(uuid.uuid4())},
            headers=alice["headers"],
        )
        listing = (await client.get("/api/v1/conversations", headers=alice["headers"])).json()
        assert listing["conversations"][0]["id"] == with_bob["id"]
        assert listing["conversations"][0]["last_message"]["preview"] == "hi bob"
        assert with_carol["id"] in {c["id"] for c in listing["conversations"]}

    async def test_membership_is_enforced(self, client):
        alice = await register(client, "+919999900107", "Alice")
        bob = await register(client, "+919999900108", "Bob")
        mallory = await register(client, "+919999900109", "Mallory")

        conversation = (await client.post(
            "/api/v1/conversations",
            json={"type": "direct", "user_id": bob["id"]},
            headers=alice["headers"],
        )).json()

        assert (await client.get(
            f"/api/v1/conversations/{conversation['id']}", headers=mallory["headers"]
        )).status_code == 404
        assert (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=mallory["headers"],
        )).status_code == 404
        assert (await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"type": "text", "content": "intruding"},
            headers=mallory["headers"],
        )).status_code == 404


class TestMessages:
    @pytest.fixture
    async def pair(self, client):
        alice = await register(client, "+919999900201", "Alice")
        bob = await register(client, "+919999900202", "Bob")
        conversation = (await client.post(
            "/api/v1/conversations",
            json={"type": "direct", "user_id": bob["id"]},
            headers=alice["headers"],
        )).json()
        return alice, bob, conversation

    async def test_sequence_numbers_are_gap_free(self, client, pair):
        alice, _bob, conversation = pair
        for index in range(5):
            await client.post(
                f"/api/v1/conversations/{conversation['id']}/messages",
                json={"type": "text", "content": f"m{index}", "client_msg_id": str(uuid.uuid4())},
                headers=alice["headers"],
            )
        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=alice["headers"],
        )).json()
        assert [m["seq"] for m in page["messages"]] == [1, 2, 3, 4, 5]

    async def test_send_is_idempotent_on_client_msg_id(self, client, pair):
        alice, _bob, conversation = pair
        client_msg_id = str(uuid.uuid4())
        payload = {"type": "text", "content": "only once", "client_msg_id": client_msg_id}

        first = await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json=payload, headers=alice["headers"],
        )
        second = await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json=payload, headers=alice["headers"],
        )
        assert first.json()["id"] == second.json()["id"]

        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=alice["headers"],
        )).json()
        assert len(page["messages"]) == 1

    async def test_empty_and_oversized_content_rejected(self, client, pair):
        alice, _bob, conversation = pair
        for content in ("   ", "x" * 9000):
            response = await client.post(
                f"/api/v1/conversations/{conversation['id']}/messages",
                json={"type": "text", "content": content},
                headers=alice["headers"],
            )
            assert response.status_code == 400, content[:10]

    async def test_read_marker_clears_unread(self, client, pair):
        alice, bob, conversation = pair
        for index in range(3):
            await client.post(
                f"/api/v1/conversations/{conversation['id']}/messages",
                json={"type": "text", "content": f"m{index}", "client_msg_id": str(uuid.uuid4())},
                headers=alice["headers"],
            )

        listing = (await client.get("/api/v1/conversations", headers=bob["headers"])).json()
        assert listing["conversations"][0]["unread_count"] == 3

        response = await client.post(
            f"/api/v1/conversations/{conversation['id']}/read",
            json={}, headers=bob["headers"],
        )
        assert response.json() == {"unread_count": 0, "last_read_seq": 3}

        listing = (await client.get("/api/v1/conversations", headers=bob["headers"])).json()
        assert listing["conversations"][0]["unread_count"] == 0

    async def test_status_ladder_end_to_end(self, client, pair):
        alice, bob, conversation = pair
        sent = (await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"type": "text", "content": "tick", "client_msg_id": str(uuid.uuid4())},
            headers=alice["headers"],
        )).json()
        assert sent["status"] == "sent"

        await client.post(
            f"/api/v1/conversations/{conversation['id']}/read",
            json={"last_read_message_id": sent["id"]}, headers=bob["headers"],
        )
        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=alice["headers"],
        )).json()
        assert page["messages"][0]["status"] == "read"
        assert page["messages"][0]["read_by"] == 1

    async def test_soft_delete_leaves_a_tombstone(self, client, pair):
        alice, bob, conversation = pair
        message = (await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"type": "text", "content": "oops", "client_msg_id": str(uuid.uuid4())},
            headers=alice["headers"],
        )).json()

        assert (await client.delete(
            f"/api/v1/messages/{message['id']}", headers=bob["headers"]
        )).status_code == 403
        assert (await client.delete(
            f"/api/v1/messages/{message['id']}", headers=alice["headers"]
        )).status_code == 204

        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=alice["headers"],
        )).json()
        assert page["messages"][0]["deleted_at"] is not None
        assert page["messages"][0]["content"] is None

    async def test_history_pagination_walks_backwards(self, client, pair):
        alice, _bob, conversation = pair
        for index in range(12):
            await client.post(
                f"/api/v1/conversations/{conversation['id']}/messages",
                json={"type": "text", "content": f"m{index}", "client_msg_id": str(uuid.uuid4())},
                headers=alice["headers"],
            )
        first = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages?limit=5",
            headers=alice["headers"],
        )).json()
        assert [m["seq"] for m in first["messages"]] == [8, 9, 10, 11, 12]
        assert first["next_cursor"] == "seq:8"

        second = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages?limit=5&before=8",
            headers=alice["headers"],
        )).json()
        assert [m["seq"] for m in second["messages"]] == [3, 4, 5, 6, 7]

    async def test_after_cursor_backfills_a_reconnect(self, client, pair):
        alice, bob, conversation = pair
        for index in range(6):
            await client.post(
                f"/api/v1/conversations/{conversation['id']}/messages",
                json={"type": "text", "content": f"m{index}", "client_msg_id": str(uuid.uuid4())},
                headers=alice["headers"],
            )
        missed = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages?after=3",
            headers=bob["headers"],
        )).json()
        assert [m["seq"] for m in missed["messages"]] == [4, 5, 6]


class TestGroups:
    @pytest.fixture
    async def trio(self, client):
        alice = await register(client, "+919999900301", "Alice")
        bob = await register(client, "+919999900302", "Bob")
        carol = await register(client, "+919999900303", "Carol")
        group = (await client.post(
            "/api/v1/conversations",
            json={"type": "group", "name": "Trip", "member_ids": [bob["id"], carol["id"]]},
            headers=alice["headers"],
        )).json()
        return alice, bob, carol, group

    async def test_creator_is_admin_and_members_are_added(self, client, trio):
        alice, _bob, _carol, group = trio
        assert group["type"] == "group"
        assert group["members_count"] == 3
        assert group["my_role"] == "admin"
        roles = {m["user_id"]: m["role"] for m in group["members"]}
        assert roles[alice["id"]] == "admin"

    async def test_creation_emits_a_system_message(self, client, trio):
        alice, _bob, _carol, group = trio
        page = (await client.get(
            f"/api/v1/conversations/{group['id']}/messages", headers=alice["headers"]
        )).json()
        assert page["messages"][0]["type"] == "system"
        assert page["messages"][0]["content"] == "Alice created the group"

    async def test_only_admins_can_add_members(self, client, trio):
        alice, bob, _carol, group = trio
        dave = await register(client, "+919999900304", "Dave")

        denied = await client.post(
            f"/api/v1/conversations/{group['id']}/members",
            json={"user_ids": [dave["id"]]}, headers=bob["headers"],
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "FORBIDDEN"

        allowed = await client.post(
            f"/api/v1/conversations/{group['id']}/members",
            json={"user_ids": [dave["id"]]}, headers=alice["headers"],
        )
        assert allowed.status_code == 200
        assert allowed.json()["members_count"] == 4

    async def test_added_member_does_not_inherit_the_backlog_as_unread(self, client, trio):
        alice, _bob, _carol, group = trio
        for index in range(4):
            await client.post(
                f"/api/v1/conversations/{group['id']}/messages",
                json={"type": "text", "content": f"m{index}", "client_msg_id": str(uuid.uuid4())},
                headers=alice["headers"],
            )
        dave = await register(client, "+919999900305", "Dave")
        await client.post(
            f"/api/v1/conversations/{group['id']}/members",
            json={"user_ids": [dave["id"]]}, headers=alice["headers"],
        )
        listing = (await client.get("/api/v1/conversations", headers=dave["headers"])).json()
        # Only the "Alice added Dave" system message is unread, not the history.
        assert listing["conversations"][0]["unread_count"] == 1

    async def test_removing_a_member_revokes_access(self, client, trio):
        alice, bob, _carol, group = trio
        response = await client.delete(
            f"/api/v1/conversations/{group['id']}/members/{bob['id']}",
            headers=alice["headers"],
        )
        assert response.status_code == 204
        assert (await client.get(
            f"/api/v1/conversations/{group['id']}", headers=bob["headers"]
        )).status_code == 404

    async def test_self_leave_is_allowed_without_admin(self, client, trio):
        _alice, bob, _carol, group = trio
        assert (await client.delete(
            f"/api/v1/conversations/{group['id']}/members/{bob['id']}",
            headers=bob["headers"],
        )).status_code == 204

    async def test_admin_is_reassigned_when_the_last_admin_leaves(self, client, trio):
        alice, bob, _carol, group = trio
        await client.delete(
            f"/api/v1/conversations/{group['id']}/members/{alice['id']}",
            headers=alice["headers"],
        )
        detail = (await client.get(
            f"/api/v1/conversations/{group['id']}", headers=bob["headers"]
        )).json()
        assert any(m["role"] == "admin" for m in detail["members"])

    async def test_only_admins_can_rename(self, client, trio):
        alice, bob, _carol, group = trio
        assert (await client.patch(
            f"/api/v1/conversations/{group['id']}",
            json={"name": "Hijacked"}, headers=bob["headers"],
        )).status_code == 403

        renamed = await client.patch(
            f"/api/v1/conversations/{group['id']}",
            json={"name": "Weekend Trip"}, headers=alice["headers"],
        )
        assert renamed.json()["name"] == "Weekend Trip"

    async def test_mute_is_per_member_not_admin_gated(self, client, trio):
        _alice, bob, _carol, group = trio
        response = await client.patch(
            f"/api/v1/conversations/{group['id']}",
            json={"muted": True}, headers=bob["headers"],
        )
        assert response.status_code == 200
        assert response.json()["muted"] is True


class TestUsersAndContacts:
    async def test_search_excludes_self_and_matches_name_or_phone(self, client):
        alice = await register(client, "+919999900401", "Alice Cooper")
        await register(client, "+919999900402", "Bob Dylan")

        results = (await client.get(
            "/api/v1/users/search?q=dylan", headers=alice["headers"]
        )).json()["results"]
        assert [u["display_name"] for u in results] == ["Bob Dylan"]

        results = (await client.get(
            "/api/v1/users/search?q=9999900402", headers=alice["headers"]
        )).json()["results"]
        assert len(results) == 1

        results = (await client.get(
            "/api/v1/users/search?q=Cooper", headers=alice["headers"]
        )).json()["results"]
        assert results == []

    async def test_contacts_crud_and_duplicate_guard(self, client):
        alice = await register(client, "+919999900403", "Alice")
        await register(client, "+919999900404", "Bob")

        created = await client.post(
            "/api/v1/contacts",
            json={"phone_number": "+919999900404", "nickname": "Bobby"},
            headers=alice["headers"],
        )
        assert created.status_code == 201
        assert created.json()["nickname"] == "Bobby"

        duplicate = await client.post(
            "/api/v1/contacts",
            json={"phone_number": "+919999900404"},
            headers=alice["headers"],
        )
        assert duplicate.status_code == 409

        listing = (await client.get("/api/v1/contacts", headers=alice["headers"])).json()
        assert len(listing["contacts"]) == 1

        assert (await client.delete(
            f"/api/v1/contacts/{created.json()['id']}", headers=alice["headers"]
        )).status_code == 204

    async def test_profile_update_and_username_uniqueness(self, client):
        alice = await register(client, "+919999900405", "Alice")
        bob = await register(client, "+919999900406", "Bob")

        response = await client.patch(
            "/api/v1/users/me",
            json={"username": "alice", "about": "on Signal"},
            headers=alice["headers"],
        )
        assert response.json()["username"] == "alice"

        clash = await client.patch(
            "/api/v1/users/me", json={"username": "Alice"}, headers=bob["headers"]
        )
        assert clash.status_code == 409
        assert clash.json()["error"]["code"] == "USERNAME_TAKEN"
