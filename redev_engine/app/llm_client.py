"""One function to call the LLM through an OpenAI compatible endpoint, with a file cache and a replay mode."""

import hashlib
import json
import time
from dataclasses import asdict, dataclass

import openai
from pydantic import BaseModel, ValidationError

from app.config import get_settings

MAX_ATTEMPTS = 4
SERVER_ERRORS = (openai.InternalServerError, openai.APIConnectionError, openai.APITimeoutError)
RATE_LIMIT_WAITS = (10, 30, 60)
MAX_RATE_LIMIT_WAIT_SECONDS = 90


class LLMError(RuntimeError):
    """Raised when the LLM cannot give a usable answer."""


@dataclass
class LLMResponse:
    """Text of the reply plus the trace fields for the audit trail."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cached: bool
    prompt_sha256: str
    step: str = ""
    parsed: BaseModel | None = None

    def trace(self) -> dict:
        """Trace entry as listed in llm_trace of the RedevelopResult."""
        return {k: v for k, v in asdict(self).items() if k not in {"text", "parsed"}}


def cache_key(model: str, system: str, user: str) -> str:
    """SHA 256 of model, system text and user text."""
    return hashlib.sha256("\n\x1e".join([model, system, user]).encode("utf-8")).hexdigest()


def make_client() -> openai.OpenAI:
    """OpenAI SDK client pointed at the configured endpoint."""
    settings = get_settings()
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY is not set. Set it in the root .env or use LLM_MODE=replay.")
    return openai.OpenAI(base_url=settings.llm_base_url or None, api_key=settings.llm_api_key, max_retries=0)


def error_payload(error: Exception) -> dict:
    """Inner error object of the provider body, which can be a list (Gemini) or an object."""
    body = getattr(error, "body", None)
    if isinstance(body, list):
        body = body[0] if body else {}
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        body = body["error"]
    return body if isinstance(body, dict) else {}


def provider_message(error: Exception) -> str:
    """Readable message from the provider, falling back to the SDK text."""
    return str(error_payload(error).get("message") or error)


def retry_delay(error: Exception) -> float | None:
    """Seconds the provider asks us to wait: RetryInfo 'retryDelay' in the body, else a numeric Retry-After header."""
    for detail in error_payload(error).get("details") or []:
        delay = str(detail.get("retryDelay", "")) if isinstance(detail, dict) else ""
        if delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                pass
    response = getattr(error, "response", None)
    header = response.headers.get("retry-after") if response is not None else None
    try:
        return float(header) if header else None
    except ValueError:
        return None


def call_provider(model: str, system: str, user: str, json_mode: bool) -> tuple[str, int, int]:
    """Call the provider; wait on short rate limits, stop at once on long ones, back off on server errors."""
    client = make_client()
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            reply = client.chat.completions.create(
                model=model,
                temperature=get_settings().llm_temperature,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                **kwargs,
            )
            usage = reply.usage
            return (
                reply.choices[0].message.content or "",
                usage.prompt_tokens if usage else 0,
                usage.completion_tokens if usage else 0,
            )
        except openai.RateLimitError as error:
            delay = retry_delay(error)
            if delay is not None and delay > MAX_RATE_LIMIT_WAIT_SECONDS:
                raise LLMError(f"LLM rate limit, provider asks to retry in {delay:.0f} s: {provider_message(error)}") from error
            if attempt == MAX_ATTEMPTS:
                raise LLMError(f"LLM rate limit after {MAX_ATTEMPTS} attempts: {provider_message(error)}") from error
            time.sleep(delay if delay is not None else RATE_LIMIT_WAITS[attempt - 1])
        except SERVER_ERRORS as error:
            if attempt == MAX_ATTEMPTS:
                raise LLMError(f"LLM provider failed after {MAX_ATTEMPTS} attempts: {provider_message(error)}") from error
            time.sleep(2**attempt)
    raise LLMError("unreachable")


def cached_or_live(model: str, system: str, user: str, json_mode: bool, step: str) -> LLMResponse:
    """Serve from the cache when possible, otherwise call the provider (live mode only) and store the reply."""
    settings = get_settings()
    key = cache_key(model, system, user)
    path = settings.llm_cache_dir / f"{key}.json"
    if path.exists():
        stored = json.loads(path.read_text(encoding="utf-8"))
        return LLMResponse(
            text=stored["text"], model=model, input_tokens=stored["input_tokens"],
            output_tokens=stored["output_tokens"], latency_ms=0, cached=True, prompt_sha256=key, step=step,
        )
    if settings.llm_mode == "replay":
        raise LLMError(f"LLM_MODE=replay and no cached reply for step '{step}' (key {key[:12]}).")
    started = time.perf_counter()
    text, input_tokens, output_tokens = call_provider(model, system, user, json_mode)
    latency_ms = int((time.perf_counter() - started) * 1000)
    settings.llm_cache_dir.mkdir(parents=True, exist_ok=True)
    record = {"model": model, "step": step, "text": text, "input_tokens": input_tokens, "output_tokens": output_tokens}
    path.write_text(json.dumps(record, indent=1), encoding="utf-8")
    return LLMResponse(text, model, input_tokens, output_tokens, latency_ms, False, key, step)


def parse_json(text: str, response_model: type[BaseModel]) -> BaseModel:
    """Parse a JSON reply (a surrounding code fence is tolerated) and validate it."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
    return response_model.model_validate_json(cleaned)


def complete(
    system: str,
    user: str,
    *,
    json_mode: bool = False,
    step: str = "",
    model: str | None = None,
    response_model: type[BaseModel] | None = None,
) -> LLMResponse:
    """Call the LLM once. With json_mode and a response_model, validate the reply and retry once on invalid JSON."""
    model = model or get_settings().llm_model
    if not model:
        raise LLMError("LLM_MODEL is not set.")
    response = cached_or_live(model, system, user, json_mode, step)
    if not (json_mode and response_model):
        return response
    try:
        response.parsed = parse_json(response.text, response_model)
        return response
    except (ValidationError, ValueError) as first_error:
        retry_user = f"{user}\n\nYour previous reply was not valid. Error:\n{first_error}\nReply again with valid JSON only."
        retry = cached_or_live(model, system, retry_user, json_mode, step + ":retry")
        try:
            retry.parsed = parse_json(retry.text, response_model)
        except (ValidationError, ValueError) as second_error:
            raise LLMError(f"Step '{step}': invalid JSON twice: {second_error}") from second_error
        retry.input_tokens += response.input_tokens
        retry.output_tokens += response.output_tokens
        return retry
