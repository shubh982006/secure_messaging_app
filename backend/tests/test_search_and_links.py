"""Full-text search and link previews."""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import register

pytestmark = pytest.mark.asyncio


async def seed_thread(client, alice, bob, lines: list[str]) -> dict:
    conversation = (await client.post(
        "/api/v1/conversations",
        json={"type": "direct", "user_id": bob["id"]},
        headers=alice["headers"],
    )).json()
    for line in lines:
        await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"type": "text", "content": line, "client_msg_id": str(uuid.uuid4())},
            headers=alice["headers"],
        )
    return conversation


class TestMessageSearch:
    @pytest.fixture
    async def thread(self, client):
        alice = await register(client, "+919999900701", "Alice")
        bob = await register(client, "+919999900702", "Bob")
        conversation = await seed_thread(client, alice, bob, [
            "The deployment pipeline is green again",
            "Let's grab coffee tomorrow morning",
            "Pipeline broke because of a migration",
            "See you at the coffee place",
        ])
        return alice, bob, conversation

    async def test_finds_matches_across_a_conversation(self, client, thread):
        alice, _bob, _conversation = thread
        results = (await client.get(
            "/api/v1/search/messages?q=pipeline", headers=alice["headers"]
        )).json()["results"]
        contents = {hit["message"]["content"] for hit in results}
        assert contents == {
            "The deployment pipeline is green again",
            "Pipeline broke because of a migration",
        }

    async def test_is_case_insensitive(self, client, thread):
        alice, _bob, _conversation = thread
        results = (await client.get(
            "/api/v1/search/messages?q=PIPELINE", headers=alice["headers"]
        )).json()["results"]
        assert len(results) == 2

    async def test_matches_a_prefix_so_search_feels_live(self, client, thread):
        alice, _bob, _conversation = thread
        results = (await client.get(
            "/api/v1/search/messages?q=coff", headers=alice["headers"]
        )).json()["results"]
        assert len(results) == 2

    async def test_results_carry_conversation_context(self, client, thread):
        alice, _bob, conversation = thread
        hit = (await client.get(
            "/api/v1/search/messages?q=migration", headers=alice["headers"]
        )).json()["results"][0]
        assert hit["conversation_id"] == conversation["id"]
        assert hit["conversation_name"] == "Bob"
        assert hit["conversation_type"] == "direct"
        assert "migration" in hit["snippet"]

    async def test_can_be_scoped_to_one_conversation(self, client, thread):
        alice, bob, conversation = thread
        other = await seed_thread(
            client, alice,
            await register(client, "+919999900703", "Carol"),
            ["Another pipeline entirely"],
        )
        everywhere = (await client.get(
            "/api/v1/search/messages?q=pipeline", headers=alice["headers"]
        )).json()["results"]
        assert len(everywhere) == 3

        scoped = (await client.get(
            f"/api/v1/search/messages?q=pipeline&conversation_id={other['id']}",
            headers=alice["headers"],
        )).json()["results"]
        assert len(scoped) == 1
        assert scoped[0]["message"]["content"] == "Another pipeline entirely"

    async def test_never_leaks_another_conversation(self, client, thread):
        _alice, _bob, _conversation = thread
        mallory = await register(client, "+919999900704", "Mallory")
        results = (await client.get(
            "/api/v1/search/messages?q=pipeline", headers=mallory["headers"]
        )).json()["results"]
        assert results == []

    async def test_deleted_messages_are_excluded(self, client, thread):
        alice, _bob, conversation = thread
        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=alice["headers"],
        )).json()
        target = next(m for m in page["messages"] if "migration" in (m["content"] or ""))
        await client.delete(f"/api/v1/messages/{target['id']}", headers=alice["headers"])

        results = (await client.get(
            "/api/v1/search/messages?q=migration", headers=alice["headers"]
        )).json()["results"]
        assert results == []

    async def test_system_messages_are_excluded(self, client):
        alice = await register(client, "+919999900705", "Alice")
        bob = await register(client, "+919999900706", "Bob")
        await client.post(
            "/api/v1/conversations",
            json={"type": "group", "name": "Squad", "member_ids": [bob["id"]]},
            headers=alice["headers"],
        )
        results = (await client.get(
            "/api/v1/search/messages?q=created", headers=alice["headers"]
        )).json()["results"]
        assert results == []

    async def test_short_queries_are_ignored(self, client, thread):
        alice, _bob, _conversation = thread
        results = (await client.get(
            "/api/v1/search/messages?q=a", headers=alice["headers"]
        )).json()["results"]
        assert results == []

    async def test_fts_operators_do_not_blow_up(self, client, thread):
        alice, _bob, _conversation = thread
        # These characters are FTS5 syntax; a user typing them must not 500.
        for query in ['"', "c++", "foo*", "a AND", "(", "^x", "-y", "'"]:
            response = await client.get(
                f"/api/v1/search/messages?q={query}", headers=alice["headers"]
            )
            assert response.status_code == 200, (query, response.text)

    async def test_edits_are_reindexed(self, client, thread):
        alice, _bob, conversation = thread
        # Soft delete rewrites content to NULL, which must update the index.
        page = (await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=alice["headers"],
        )).json()
        target = next(m for m in page["messages"] if "coffee tomorrow" in (m["content"] or ""))
        await client.delete(f"/api/v1/messages/{target['id']}", headers=alice["headers"])

        results = (await client.get(
            "/api/v1/search/messages?q=coffee", headers=alice["headers"]
        )).json()["results"]
        assert len(results) == 1
        assert results[0]["message"]["content"] == "See you at the coffee place"

    async def test_requires_auth(self, client):
        assert (await client.get("/api/v1/search/messages?q=hello")).status_code == 401


class TestLinkPreviewSecurity:
    """The endpoint fetches a user-supplied URL, so SSRF is the whole risk."""

    @pytest.fixture
    async def alice(self, client):
        return await register(client, "+919999900801", "Alice")

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/admin",
        "http://localhost:8000/",
        "http://169.254.169.254/latest/meta-data/",   # cloud metadata
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://[::1]/",
        "http://0.0.0.0/",
    ])
    async def test_private_and_loopback_targets_are_refused(self, client, alice, url):
        response = await client.get(
            f"/api/v1/links/preview?url={url}", headers=alice["headers"]
        )
        assert response.status_code in (400, 422), (url, response.text)
        assert response.json()["error"]["code"] in {
            "LINK_NOT_ALLOWED", "UNSUPPORTED_SCHEME", "VALIDATION_ERROR",
        }

    @pytest.mark.parametrize("url", [
        "file:///etc/passwd",
        "gopher://127.0.0.1:11211/",
        "data:text/html,<h1>hi</h1>",
        "ftp://example.com/",
    ])
    async def test_non_http_schemes_are_refused(self, client, alice, url):
        response = await client.get(
            f"/api/v1/links/preview?url={url}", headers=alice["headers"]
        )
        assert response.status_code in (400, 422)
        assert response.json()["error"]["code"] == "UNSUPPORTED_SCHEME"

    async def test_requires_auth(self, client):
        response = await client.get("/api/v1/links/preview?url=https://example.com")
        assert response.status_code == 401
