"""One way to call the LLM, with a reply cache and a replay mode (section 12 of the project context).

live: answer from factory_core/llm_cache/ when the prompt was seen before, otherwise call the provider
and store the reply. replay: answer from the cache only, so the pipeline runs with no key and no network.
"""

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import openai
from pydantic import BaseModel, ValidationError

from app.config import Settings

MAX_PROVIDER_ATTEMPTS = 4
PROVIDER_TIMEOUT_SECONDS = 180.0
JSON_ONLY_INSTRUCTION = "Reply with one JSON object only. No text before or after it, no code fences."
RETRYABLE_ERRORS = (openai.RateLimitError, openai.InternalServerError, openai.APIConnectionError)


class LLMError(Exception):
    """Any LLM failure; the message is ready to show as a stage error."""


class LLMConfigurationError(LLMError):
    """Live mode needs a key and a model id that are not set."""


class LLMReplayMissError(LLMError):
    """Replay mode found no recorded reply for this prompt."""


class LLMCallError(LLMError):
    """The provider failed, also after retries."""


class LLMInvalidReplyError(LLMError):
    """The reply was not valid JSON for the required shape, also after one corrective retry."""


@dataclass(frozen=True)
class ProviderReply:
    """What the provider returned for one call."""

    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True)
class LLMResponse:
    """One answered call, from the cache or the provider, with the fields the audit trail records."""

    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    cached: bool
    prompt_sha256: str
    step: str
    parsed: Any = field(default=None, compare=False)

    def trace(self) -> dict[str, Any]:
        """The detail of the llm_call audit event for this call."""
        return {
            "step": self.step,
            "model": self.model,
            "prompt_sha256": self.prompt_sha256,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "cached": self.cached,
        }


Provider = Callable[[str, str, str, float], ProviderReply]


def sha256_text(text: str) -> str:
    """SHA 256 of a text, as hex."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_hash(system: str, user: str) -> str:
    """Hash of the prompt alone, recorded in the audit trail."""
    return sha256_text(json.dumps([system, user], ensure_ascii=False))


def cache_key(model: str, system: str, user: str) -> str:
    """Cache key: SHA 256 of the model id, the system text and the user text."""
    return sha256_text(json.dumps([model, system, user], ensure_ascii=False))


def extract_json_object(text: str) -> Any:
    """Parse the JSON object in a reply, tolerating code fences or text around it."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("the reply contains no JSON object")
    return json.loads(cleaned[start : end + 1])


def openai_provider(settings: Settings) -> Provider:
    """Provider that calls any OpenAI compatible chat completions endpoint."""
    client = openai.OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url or None,
        max_retries=0,
        timeout=PROVIDER_TIMEOUT_SECONDS,
    )

    def call(model: str, system: str, user: str, temperature: float) -> ProviderReply:
        """Send one chat completion request."""
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
        )
        usage = completion.usage
        return ProviderReply(
            text=completion.choices[0].message.content or "",
            model=completion.model or model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )

    return call


class LLMClient:
    """The LLM client of factory_core. on_call receives every answered call, cached or not."""

    def __init__(
        self,
        settings: Settings,
        provider: Provider | None = None,
        on_call: Callable[[LLMResponse], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Keep the settings; the provider is created on the first live call unless a test passes one."""
        self.settings = settings
        self.provider = provider
        self.on_call = on_call
        self.sleep = sleep

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        step: str = "",
        model: str | None = None,
        schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        """Answer one prompt. With json_mode the reply is parsed (and validated against schema when given)."""
        if json_mode:
            system = f"{system}\n\n{JSON_ONLY_INSTRUCTION}"
        response = self._answer(system, user, step, model)
        if not json_mode:
            return response
        try:
            return self._with_parsed(response, schema)
        except (ValueError, ValidationError) as first_error:
            retry_user = (
                f"{user}\n\nYour previous reply could not be used: {first_error}\n"
                "Reply again with the corrected JSON object only."
            )
            retried = self._answer(system, retry_user, f"{step}:retry", model)
            try:
                return self._with_parsed(retried, schema)
            except (ValueError, ValidationError) as second_error:
                raise LLMInvalidReplyError(f"LLM step {step}: reply is not valid JSON twice: {second_error}") from None

    def _with_parsed(self, response: LLMResponse, schema: type[BaseModel] | None) -> LLMResponse:
        """Attach the parsed JSON (validated against the schema when given) to a response."""
        data = extract_json_object(response.text)
        parsed = schema.model_validate(data) if schema else data
        return LLMResponse(**{**response.__dict__, "parsed": parsed})

    def _answer(self, system: str, user: str, step: str, model: str | None) -> LLMResponse:
        """Answer from the cache or the provider, store new replies, and report the call."""
        model_id = model or self.settings.llm_model
        prompt_sha256 = prompt_hash(system, user)
        recorded = self._read_cache(cache_key(model_id, system, user), prompt_sha256)
        if recorded is not None:
            response = LLMResponse(
                text=recorded["text"],
                model=recorded["model"],
                input_tokens=recorded.get("input_tokens"),
                output_tokens=recorded.get("output_tokens"),
                latency_ms=0,
                cached=True,
                prompt_sha256=prompt_sha256,
                step=step,
            )
        else:
            response = self._call_provider(model_id, system, user, step, prompt_sha256)
        if self.on_call:
            self.on_call(response)
        return response

    def _read_cache(self, key: str, prompt_sha256: str) -> dict[str, Any] | None:
        """Exact cache hit; in replay mode also any recorded reply to the same prompt."""
        path = self.settings.llm_cache_dir / f"{key}.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if self.settings.llm_mode != "replay" or not self.settings.llm_cache_dir.is_dir():
            return None
        for candidate in sorted(self.settings.llm_cache_dir.glob("*.json")):
            recorded = json.loads(candidate.read_text(encoding="utf-8"))
            if recorded.get("prompt_sha256") == prompt_sha256:
                return recorded
        return None

    def _call_provider(self, model_id: str, system: str, user: str, step: str, prompt_sha256: str) -> LLMResponse:
        """Call the provider with retries and store the reply in the cache."""
        if self.settings.llm_mode == "replay":
            raise LLMReplayMissError(
                f"LLM step {step}: no recorded reply in factory_core/llm_cache/ (prompt {prompt_sha256[:12]}). "
                "Run once with LLM_MODE=live and a key to record it."
            )
        if not self.settings.llm_api_key or not model_id:
            raise LLMConfigurationError(
                "LLM_API_KEY and LLM_MODEL must be set in .env for live mode, or use LLM_MODE=replay."
            )
        provider = self.provider or openai_provider(self.settings)
        started = time.perf_counter()
        for attempt in range(1, MAX_PROVIDER_ATTEMPTS + 1):
            try:
                reply = provider(model_id, system, user, self.settings.llm_temperature)
                break
            except RETRYABLE_ERRORS as error:
                if attempt == MAX_PROVIDER_ATTEMPTS:
                    raise LLMCallError(f"LLM step {step}: provider failed {attempt} times: {error}") from error
                self.sleep(2 ** (attempt - 1))
            except openai.APIStatusError as error:
                raise LLMCallError(
                    f"LLM step {step}: provider returned {error.status_code}: {error.message}"
                ) from error
        response = LLMResponse(
            text=reply.text,
            model=reply.model,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            cached=False,
            prompt_sha256=prompt_sha256,
            step=step,
        )
        self._write_cache(cache_key(model_id, system, user), response)
        return response

    def _write_cache(self, key: str, response: LLMResponse) -> None:
        """Store a live reply as one JSON file, written atomically."""
        self.settings.llm_cache_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "cache_key": key,
            "prompt_sha256": response.prompt_sha256,
            "step": response.step,
            "model": response.model,
            "text": response.text,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_ms": response.latency_ms,
            "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        target = self.settings.llm_cache_dir / f"{key}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(target)
