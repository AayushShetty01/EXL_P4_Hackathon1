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


DAILY_QUOTA_BODY = [{"error": {
    "code": 429, "status": "RESOURCE_EXHAUSTED",
    "message": "Quota exceeded for metric generate_content_free_tier_requests, limit: 20, per day limit exceeded. Please retry in 15h34m.",
    "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "56075s"}],
}}]


def rate_limit(body=None, headers=None):
    """A 429 error as the SDK raises it, with the given body and headers."""
    response = httpx.Response(429, headers=headers, request=httpx.Request("POST", "http://x"))
    return openai.RateLimitError("Error code: 429", response=response, body=body)


def server_error():
    """A 500 error as the SDK raises it."""
    response = httpx.Response(500, request=httpx.Request("POST", "http://x"))
    return openai.InternalServerError("Error code: 500", response=response, body=None)


@pytest.fixture
def scripted_sdk(monkeypatch, settings_env):
    """Fake SDK client that raises the scripted errors in order, then answers; time.sleep is recorded, not slept."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    errors, attempts, sleeps = [], [], []

    class Completions:
        """Raises the next scripted error, or answers when none is left."""

        def create(self, **kwargs):
            """One provider call."""
            attempts.append(kwargs)
            if errors:
                raise errors.pop(0)
            message = type("M", (), {"content": "ok"})
            usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 2})
            return type("R", (), {"choices": [type("C", (), {"message": message})], "usage": usage})

    client = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})})
    monkeypatch.setattr(llm_client, "make_client", lambda: client)
    monkeypatch.setattr(llm_client.time, "sleep", sleeps.append)
    return errors, attempts, sleeps


def test_daily_quota_stops_at_once_with_the_provider_message(scripted_sdk):
    """A retry delay of hours stops after one call, with no wait, and reports the provider's message."""
    errors, attempts, sleeps = scripted_sdk
    errors.append(rate_limit(DAILY_QUOTA_BODY))
    with pytest.raises(llm_client.LLMError, match="per day limit exceeded") as caught:
        llm_client.call_provider("m", "s", "u", False)
    assert "56075" in str(caught.value)
    assert (len(attempts), sleeps) == (1, [])


def test_short_retry_delay_is_waited_then_succeeds(scripted_sdk):
    """A '20s' retry delay in an object body is waited once, then the call succeeds."""
    errors, attempts, sleeps = scripted_sdk
    errors.append(rate_limit({"message": "slow down", "details": [{"retryDelay": "20s"}]}))
    assert llm_client.call_provider("m", "s", "u", False) == ("ok", 1, 2)
    assert (len(attempts), sleeps) == (2, [20.0])


def test_retry_after_header_is_used(scripted_sdk):
    """A numeric Retry-After header gives the wait when the body has none."""
    errors, _, sleeps = scripted_sdk
    errors.append(rate_limit(headers={"retry-after": "7"}))
    llm_client.call_provider("m", "s", "u", False)
    assert sleeps == [7.0]


def test_rate_limit_without_delay_waits_10_then_30(scripted_sdk):
    """Without a delay from the provider the waits are 10 then 30 seconds."""
    errors, attempts, sleeps = scripted_sdk
    errors.extend([rate_limit(), rate_limit()])
    assert llm_client.call_provider("m", "s", "u", False) == ("ok", 1, 2)
    assert (len(attempts), sleeps) == (3, [10, 30])


def test_rate_limit_on_every_attempt_reports_the_provider_message(scripted_sdk):
    """After the last attempt the error carries the provider's message, not the raw SDK text."""
    errors, attempts, sleeps = scripted_sdk
    errors.extend(rate_limit({"message": "busy, try later"}) for _ in range(llm_client.MAX_ATTEMPTS))
    with pytest.raises(llm_client.LLMError, match="busy, try later"):
        llm_client.call_provider("m", "s", "u", False)
    assert (len(attempts), sleeps) == (4, [10, 30, 60])


def test_server_errors_keep_the_short_backoff(scripted_sdk):
    """Server errors still wait 2 then 4 seconds."""
    errors, attempts, sleeps = scripted_sdk
    errors.extend([server_error(), server_error()])
    assert llm_client.call_provider("m", "s", "u", False) == ("ok", 1, 2)
    assert (len(attempts), sleeps) == (3, [2, 4])


def test_sdk_client_does_not_retry_on_its_own(monkeypatch, settings_env):
    """The SDK client is created with max_retries=0, so only call_provider retries."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    assert llm_client.make_client().max_retries == 0


def test_missing_key_is_reported(monkeypatch, settings_env):
    """Live mode without a key gives a clear error and never calls the network."""
    monkeypatch.setenv("LLM_API_KEY", "")
    with pytest.raises(llm_client.LLMError, match="LLM_API_KEY"):
        llm_client.make_client()
