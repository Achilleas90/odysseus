import asyncio
import sys
import types

import pytest

from src.task_scheduler import TaskScheduler


def _task(name="Daily Brief"):
    return types.SimpleNamespace(id="task-1", name=name)


def test_discord_output_target_detection_and_webhook_resolution(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_DISCORD_WEBHOOK_URL", " https://discord.com/api/webhooks/1/token ")
    monkeypatch.setenv("ODYSSEUS_DISCORD_WEBHOOK_ALERTS_TEAM", "https://discord.com/api/webhooks/2/token")

    assert TaskScheduler._is_discord_output_target("discord")
    assert TaskScheduler._is_discord_output_target("Discord:alerts-team")
    assert not TaskScheduler._is_discord_output_target("session")

    assert TaskScheduler._resolve_discord_webhook("discord") == "https://discord.com/api/webhooks/1/token"
    assert TaskScheduler._resolve_discord_webhook("Discord:alerts team") == "https://discord.com/api/webhooks/2/token"


def test_discord_webhook_validation_rejects_non_discord_urls():
    TaskScheduler._validate_discord_webhook_url("https://discord.com/api/webhooks/1/token")
    TaskScheduler._validate_discord_webhook_url("https://discordapp.com/api/webhooks/1/token")

    with pytest.raises(RuntimeError):
        TaskScheduler._validate_discord_webhook_url("http://discord.com/api/webhooks/1/token")
    with pytest.raises(RuntimeError):
        TaskScheduler._validate_discord_webhook_url("https://example.com/api/webhooks/1/token")
    with pytest.raises(RuntimeError):
        TaskScheduler._validate_discord_webhook_url("https://discord.com/channels/1")


def test_discord_chunks_split_long_output_on_newlines_when_possible():
    first = "a" * 410
    second = "b" * 60
    chunks = TaskScheduler._discord_chunks(f"{first}\n{second}", limit=450)

    assert chunks == [first, second]


def test_deliver_via_discord_posts_payloads_without_network(monkeypatch):
    posts = []

    class FakeResponse:
        status_code = 204

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            posts.append((url, json))
            return FakeResponse()

    fake_httpx = types.SimpleNamespace(AsyncClient=FakeAsyncClient)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    monkeypatch.setenv("ODYSSEUS_DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/token")

    scheduler = TaskScheduler.__new__(TaskScheduler)

    asyncio.run(scheduler._deliver_via_discord("discord", _task(), "hello"))

    assert posts == [
        (
            "https://discord.com/api/webhooks/1/token",
            {"username": "Odysseus", "content": "**Odysseus: Daily Brief**\nhello"},
        )
    ]


def test_deliver_via_discord_surfaces_http_failures(monkeypatch):
    class FakeResponse:
        status_code = 500

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            return FakeResponse()

    fake_httpx = types.SimpleNamespace(AsyncClient=FakeAsyncClient)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    monkeypatch.setenv("ODYSSEUS_DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/token")

    scheduler = TaskScheduler.__new__(TaskScheduler)

    with pytest.raises(RuntimeError, match="HTTP 500"):
        asyncio.run(scheduler._deliver_via_discord("discord", _task(), "hello"))
