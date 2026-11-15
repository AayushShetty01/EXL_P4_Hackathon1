"""What an OpenAI compatible provider says about a failed call: its own message and its retry delay.

Some providers (Gemini among them) send the error body as a list, so the SDK only shows "Error code: 429".
These helpers find the provider's message and suggested wait, so a stage error can say, for example, that
the daily free tier quota is used up and when it resets.
"""

from typing import Any

import openai

MESSAGE_LIMIT = 400


def error_body(error: openai.APIStatusError) -> dict[str, Any]:
    """The inner error object of a provider error body, whether it came as an object or a list."""
    body: Any = error.body
    if isinstance(body, list):
        body = body[0] if body else {}
    if not isinstance(body, dict):
        return {}
    inner = body.get("error", body)
    return inner if isinstance(inner, dict) else {}


def provider_message(error: openai.APIStatusError) -> str:
    """The provider's own explanation, shortened to its most specific part."""
    message = str(error_body(error).get("message") or error.message)
    specific = message.split("* ", 1)[-1]
    return " ".join(specific.split())[:MESSAGE_LIMIT]


def seconds(text: str) -> float | None:
    """Seconds from a delay such as "56075s" or "20"; None when it is not a number."""
    try:
        return float(text.strip().removesuffix("s"))
    except ValueError:
        return None


def retry_delay(error: openai.APIStatusError) -> float | None:
    """How long the provider asks the caller to wait before retrying, in seconds, when it says so."""
    details = error_body(error).get("details")
    for detail in details if isinstance(details, list) else []:
        if isinstance(detail, dict) and "retryDelay" in detail:
            return seconds(str(detail["retryDelay"]))
    header = error.response.headers.get("retry-after")
    return seconds(header) if header else None
