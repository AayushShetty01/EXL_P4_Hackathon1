"""Tests for the LLM client with a mocked provider: cache, replay, JSON retry and backoff."""

import httpx
import openai
import pytest
from pydantic import BaseModel

from app import llm_client


class Answer(BaseModel):
    """A tiny JSON reply shape."""

    value: int


@pytest.fixture
def provider(monkeypatch, settings_env):
    """Mock the provider call in live mode and record each call."""
    monkeypatch.setenv("LLM_MODE", "live")
    replies, calls = [], []

    def fake_call(model, system, user, json_mode):
        """Return the next scripted reply."""
        calls.append(user)
        return replies.pop(0), 100, 20

    monkeypatch.setattr(llm_client, "call_provider", fake_call)
    return replies, calls


def test_live_call_is_cached_and_reused(provider, settings_env):
    """The first call reaches the provider and is stored; the same call again comes from the cache."""
    replies, calls = provider
    replies.append("hello")
    first = llm_client.complete("sys", "user", step="s")
    second = llm_client.complete("sys", "user", step="s")
    assert (first.text, first.cached, second.text, second.cached) == ("hello", False, "hello", True)
    assert len(calls) == 1
    assert (settings_env / "llm_cache" / f"{first.prompt_sha256}.json").exists()
    assert set(first.trace()) == {"step", "model", "prompt_sha256", "input_tokens", "output_tokens", "latency_ms", "cached"}


def test_replay_serves_cache_and_fails_clearly_without_it(provider, monkeypatch):
    """Replay mode serves stored replies and raises a clear error for a missing one."""
    provider[0].append("stored")
    llm_client.complete("sys", "user", step="s")
    monkeypatch.setenv("LLM_MODE", "replay")
    assert llm_client.complete("sys", "user", step="s").text == "stored"
    with pytest.raises(llm_client.LLMError, match="replay"):
        llm_client.complete("sys", "other", step="s")


def test_invalid_json_is_retried_once_with_the_error(provider):
    """Invalid JSON triggers one retry that includes the validation error."""
    replies, calls = provider
    replies += ["not json", '{"value": 3}']
    response = llm_client.complete("sys", "user", json_mode=True, step="s", response_model=Answer)
    assert response.parsed.value == 3
    assert "not valid" in calls[1]


def test_invalid_json_twice_raises(provider):
    """Two invalid replies raise LLMError."""
    provider[0].extend(["nope", "still nope"])
    with pytest.raises(llm_client.LLMError):
        llm_client.complete("sys", "user", json_mode=True, step="s", response_model=Answer)


def test_rate_limit_is_retried_with_backoff(monkeypatch, settings_env):
    """A rate limit error is retried and the call then succeeds."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    error = openai.RateLimitError("slow down", response=httpx.Response(429, request=httpx.Request("POST", "http://x")), body=None)
    attempts = []

    class Completions:
        """Fails once, then answers."""

        def create(self, **kwargs):
            """Raise on the first attempt."""
            attempts.append(kwargs)
            if len(attempts) == 1:
                raise error
            message = type("M", (), {"content": "ok"})
            usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 2})
            return type("R", (), {"choices": [type("C", (), {"message": message})], "usage": usage})

    client = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})})
    monkeypatch.setattr(llm_client, "make_client", lambda: client)
    monkeypatch.setattr(llm_client.time, "sleep", lambda seconds: None)
    assert llm_client.call_provider("m", "s", "u", False) == ("ok", 1, 2)
    assert len(attempts) == 2


def test_missing_key_is_reported(monkeypatch, settings_env):
    """Live mode without a key gives a clear error and never calls the network."""
    monkeypatch.setenv("LLM_API_KEY", "")
    with pytest.raises(llm_client.LLMError, match="LLM_API_KEY"):
        llm_client.make_client()
