import json

import httpx
import pytest

from app import rag
from app.config import Settings
from app.rag import (
    ClaudeAnswerer,
    OpenAICompatibleAnswerer,
    RetrievedChunk,
    SourcesOnlyAnswerer,
)

CHUNKS = [RetrievedChunk("Register online at My.SSS.", "SSS", "https://sss.gov.ph", "SSS")]


def answerer_with(handler, sleeps=None) -> OpenAICompatibleAnswerer:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    sleep = sleeps.append if sleeps is not None else lambda s: None
    return OpenAICompatibleAnswerer(
        "https://api.example.com/v1/", "test-key", "some-model", http, sleep
    )


def test_openai_compatible_sends_chat_request_and_reads_answer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Go to My.SSS [1]."}}]}
        )

    answer = answerer_with(handler).answer("How do I join SSS?", CHUNKS, "tl")

    assert answer == "Go to My.SSS [1]."
    assert seen["url"] == "https://api.example.com/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "some-model"
    assert seen["body"]["messages"][0]["role"] == "system"
    user_msg = seen["body"]["messages"][1]["content"]
    assert user_msg.endswith("Answer in Tagalog.")
    assert "**Pangkalahatang gabay" in user_msg


def test_openai_compatible_explains_rate_limit_after_retries():
    sleeps = []
    answer = answerer_with(lambda r: httpx.Response(429), sleeps).answer("q", CHUNKS, "en")
    assert "quota" in answer
    assert len(sleeps) == OpenAICompatibleAnswerer.MAX_RETRIES


def test_openai_compatible_waits_out_short_rate_limit():
    responses = iter(
        [
            httpx.Response(429, headers={"retry-after": "3"}),
            httpx.Response(200, json={"choices": [{"message": {"content": "Done [1]."}}]}),
        ]
    )
    sleeps = []
    answer = answerer_with(lambda r: next(responses), sleeps).answer("q", CHUNKS, "en")
    assert answer == "Done [1]."
    assert sleeps == [3.0]


def test_openai_compatible_gives_up_on_long_rate_limit():
    sleeps = []
    long_wait = httpx.Response(429, headers={"retry-after": "120"})
    answer = answerer_with(lambda r: long_wait, sleeps).answer("q", CHUNKS, "en")
    assert "quota" in answer
    assert sleeps == []


def test_openai_compatible_raises_on_other_errors():
    with pytest.raises(httpx.HTTPStatusError):
        answerer_with(lambda r: httpx.Response(401)).answer("q", CHUNKS, "en")


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, SourcesOnlyAnswerer),
        ({"anthropic_api_key": "k"}, ClaudeAnswerer),
        ({"llm_provider": "groq"}, SourcesOnlyAnswerer),
        ({"llm_provider": "groq", "llm_api_key": "k"}, OpenAICompatibleAnswerer),
        ({"llm_provider": "gemini", "llm_api_key": "k"}, OpenAICompatibleAnswerer),
    ],
)
def test_get_answerer_picks_provider(monkeypatch, env, expected):
    monkeypatch.setattr(rag, "get_settings", lambda: Settings(_env_file=None, **env))
    rag.get_answerer.cache_clear()
    try:
        assert isinstance(rag.get_answerer(), expected)
    finally:
        rag.get_answerer.cache_clear()


def test_groq_uses_default_endpoint_and_model(monkeypatch):
    settings = Settings(_env_file=None, llm_provider="groq", llm_api_key="k")
    monkeypatch.setattr(rag, "get_settings", lambda: settings)
    rag.get_answerer.cache_clear()
    try:
        answerer = rag.get_answerer()
    finally:
        rag.get_answerer.cache_clear()
    assert answerer._url == "https://api.groq.com/openai/v1/chat/completions"
    assert answerer._model == "openai/gpt-oss-120b"
