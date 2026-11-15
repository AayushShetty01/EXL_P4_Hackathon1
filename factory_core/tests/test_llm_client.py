"""The LLM client: cache, replay mode, retries, JSON validation and the call report."""

import dataclasses
import json

import httpx
import openai
import pytest
from pydantic import BaseModel

from app.config import Settings
from app.llm_client import (
    LLMCallError,
    LLMClient,
    LLMConfigurationError,
    LLMInvalidReplyError,
    LLMReplayMissError,
    LLMResponse,
    ProviderReply,
    extract_json_object,
)
from app.provider_errors import retry_delay


class Answer(BaseModel):
    """A small reply shape for JSON mode tests."""

    purpose: str


class FakeProvider:
    """Answers with prepared replies (or raises prepared errors) and counts the calls."""

    def __init__(self, *replies: object) -> None:
        """Keep the replies in the order they are given."""
        self.replies = list(replies)
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, model: str, system: str, user: str, temperature: float) -> ProviderReply:
        """Return or raise the next prepared reply."""
        self.calls.append((model, system, user))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return ProviderReply(text=str(reply), model=model, input_tokens=120, output_tokens=30)


def live(settings: Settings) -> Settings:
    """Settings in live mode with a model and a dummy key."""
    return dataclasses.replace(settings, llm_mode="live", llm_model="test-model", llm_api_key="dummy-key")


def rate_limited() -> openai.RateLimitError:
    """A 429 error as the SDK raises it."""
    response = httpx.Response(429, request=httpx.Request("POST", "http://provider.test/chat/completions"))
    return openai.RateLimitError("rate limited", response=response, body=None)


def test_live_call_is_cached_and_answered_from_the_cache_afterwards(settings: Settings) -> None:
    """The first call reaches the provider and is stored; the same prompt is then served from the cache."""
    provider = FakeProvider("The model estimates default risk.")
    client = LLMClient(live(settings), provider=provider)
    first = client.complete("system text", "user text", step="discover")
    second = client.complete("system text", "user text", step="discover")
    assert (first.cached, second.cached) == (False, True)
    assert second.text == first.text
    assert len(provider.calls) == 1
    assert len(list(settings.llm_cache_dir.glob("*.json"))) == 1


def test_replay_mode_serves_recorded_replies_without_a_key(settings: Settings) -> None:
    """A reply recorded in live mode is served in replay mode with no key and any model setting."""
    LLMClient(live(settings), provider=FakeProvider("recorded")).complete("s", "u", step="discover")
    replay = LLMClient(dataclasses.replace(settings, llm_mode="replay", llm_model=""))
    response = replay.complete("s", "u", step="discover")
    assert (response.text, response.cached, response.model) == ("recorded", True, "test-model")


def test_replay_mode_raises_a_clear_error_on_a_missing_reply(settings: Settings) -> None:
    """Replay mode never calls a provider; a missing reply names the step and how to record it."""
    client = LLMClient(settings)
    with pytest.raises(LLMReplayMissError, match="section:overview.*LLM_MODE=live"):
        client.complete("s", "never recorded", step="section:overview")


def test_live_mode_without_a_key_explains_what_to_set(settings: Settings) -> None:
    """Live mode with no key stops with a message naming LLM_API_KEY."""
    client = LLMClient(dataclasses.replace(settings, llm_mode="live"))
    with pytest.raises(LLMConfigurationError, match="LLM_API_KEY"):
        client.complete("s", "u")


def server_error() -> openai.InternalServerError:
    """A 500 error as the SDK raises it."""
    response = httpx.Response(500, request=httpx.Request("POST", "http://provider.test/chat/completions"))
    return openai.InternalServerError("server error", response=response, body=None)


def gemini_quota_error(delay: str) -> openai.RateLimitError:
    """A 429 shaped like Gemini's: the body is a list holding the message and a RetryInfo delay."""
    message = (
        "You exceeded your current quota. \n* Quota exceeded for metric: free_tier_requests, limit: 20, "
        "description: Generate content requests per day limit exceeded on Free Tier.\nPlease retry in 15h34m."
    )
    retry_info = {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}
    body = [{"error": {"code": 429, "message": message, "status": "RESOURCE_EXHAUSTED", "details": [retry_info]}}]
    response = httpx.Response(429, request=httpx.Request("POST", "http://provider.test/chat/completions"))
    return openai.RateLimitError("Error code: 429", response=response, body=body)


def test_rate_limits_without_a_delay_are_retried_after_10_then_30_seconds(settings: Settings) -> None:
    """A per minute limit needs longer waits than a server error; the provider gave no delay here."""
    waits: list[float] = []
    provider = FakeProvider(rate_limited(), rate_limited(), "finally")
    response = LLMClient(live(settings), provider=provider, sleep=waits.append).complete("s", "u")
    assert response.text == "finally"
    assert waits == [10.0, 30.0]


def test_server_errors_are_retried_after_1_then_2_seconds(settings: Settings) -> None:
    """A passing server failure is retried quickly."""
    waits: list[float] = []
    provider = FakeProvider(server_error(), server_error(), "finally")
    response = LLMClient(live(settings), provider=provider, sleep=waits.append).complete("s", "u")
    assert (response.text, waits) == ("finally", [1, 2])


def test_provider_gives_up_after_four_attempts(settings: Settings) -> None:
    """Four rate limit errors in a row become an LLMCallError with the reason, and nothing is cached."""
    provider = FakeProvider(*(rate_limited() for _ in range(4)))
    client = LLMClient(live(settings), provider=provider, sleep=lambda seconds: None)
    with pytest.raises(LLMCallError, match="after 4 attempts.*rate limited"):
        client.complete("s", "u")
    assert not settings.llm_cache_dir.exists()


def test_daily_quota_stops_at_once_with_the_provider_reason(settings: Settings) -> None:
    """A delay of hours means the daily quota is used up: no waiting, and the error says why."""
    waits: list[float] = []
    provider = FakeProvider(gemini_quota_error("56075s"))
    client = LLMClient(live(settings), provider=provider, sleep=waits.append)
    with pytest.raises(LLMCallError, match="quota used up.*limit: 20.*per day limit exceeded.*15h34m"):
        client.complete("s", "u", step="section:overview")
    assert (len(provider.calls), waits) == (1, [])


def test_a_short_provider_delay_is_waited_out(settings: Settings) -> None:
    """A per minute limit with a suggested delay waits that long, then succeeds."""
    waits: list[float] = []
    provider = FakeProvider(gemini_quota_error("20s"), "after the wait")
    response = LLMClient(live(settings), provider=provider, sleep=waits.append).complete("s", "u")
    assert (response.text, waits) == ("after the wait", [20.0])


def test_a_retry_after_header_is_used_when_the_body_has_no_delay() -> None:
    """The standard Retry-After header gives the delay; a date or nothing gives none."""
    request = httpx.Request("POST", "http://provider.test/chat/completions")
    with_header = httpx.Response(429, request=request, headers={"retry-after": "7"})
    assert retry_delay(openai.RateLimitError("x", response=with_header, body=None)) == 7.0
    assert retry_delay(rate_limited()) is None


def test_json_mode_validates_against_the_schema(settings: Settings) -> None:
    """A JSON reply, even in a code fence, is parsed and validated."""
    provider = FakeProvider('```json\n{"purpose": "Approve or decline card applications"}\n```')
    response = LLMClient(live(settings), provider=provider).complete("s", "u", json_mode=True, schema=Answer)
    assert response.parsed == Answer(purpose="Approve or decline card applications")


def test_invalid_json_is_retried_once_with_the_error(settings: Settings) -> None:
    """An invalid first reply leads to one retry that carries the validation error."""
    provider = FakeProvider('{"wrong_field": 1}', '{"purpose": "Fraud screening"}')
    response = LLMClient(live(settings), provider=provider).complete("s", "u", json_mode=True, schema=Answer, step="x")
    assert response.parsed.purpose == "Fraud screening"
    assert "could not be used" in provider.calls[1][2]
    assert response.step == "x:retry"


def test_invalid_json_twice_is_an_error(settings: Settings) -> None:
    """Two invalid replies stop with LLMInvalidReplyError instead of guessing."""
    provider = FakeProvider("no json here", "still none")
    client = LLMClient(live(settings), provider=provider)
    with pytest.raises(LLMInvalidReplyError):
        client.complete("s", "u", json_mode=True, schema=Answer)


def test_every_answered_call_is_reported(settings: Settings) -> None:
    """on_call receives each call, including the corrective retry, with the audit trace fields."""
    reported: list[LLMResponse] = []
    provider = FakeProvider("not json", '{"purpose": "Pricing"}')
    LLMClient(live(settings), provider=provider, on_call=reported.append).complete(
        "s", "u", json_mode=True, schema=Answer, step="discover"
    )
    assert [response.step for response in reported] == ["discover", "discover:retry"]
    assert set(reported[0].trace()) == {
        "step",
        "model",
        "prompt_sha256",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "cached",
    }


def test_cache_file_holds_no_secret(settings: Settings) -> None:
    """The stored reply never contains the API key."""
    LLMClient(live(settings), provider=FakeProvider("text")).complete("s", "u")
    [cache_file] = settings.llm_cache_dir.glob("*.json")
    assert "dummy-key" not in cache_file.read_text()
    assert json.loads(cache_file.read_text())["model"] == "test-model"


def test_extract_json_object_rejects_text_without_json() -> None:
    """Text with no object is a ValueError, never an empty result."""
    with pytest.raises(ValueError):
        extract_json_object("I cannot answer that.")
