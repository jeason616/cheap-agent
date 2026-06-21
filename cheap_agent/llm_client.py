import time

import openai
from openai import OpenAI

from cheap_agent.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, MAX_OUTPUT_CHARS
from cheap_agent.logging_setup import get_logger

logger = get_logger("cheap_agent.llm_client")

_client: OpenAI | None = None

# Retry only on transient network errors (timeout / connection). Auth and
# HTTP status errors are not retried — they won't succeed on a second try.
_MAX_RETRIES = 2
_RETRY_DELAYS = [1.0, 3.0]


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=60.0)
    return _client


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [truncated at {limit} chars]"


def ask_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> str:
    """Call an OpenAI-compatible LLM and return the response text."""
    if not system_prompt and not user_prompt:
        return "[LLM Error] system_prompt and user_prompt are both empty"

    client = _get_client()
    last_transient_err: str | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content or ""
            return _truncate(text, MAX_OUTPUT_CHARS)
        except openai.AuthenticationError as e:
            logger.warning("Authentication failed: %s", e)
            return "[LLM Error] Authentication failed - check LLM_API_KEY"
        except openai.APIStatusError as e:
            logger.warning("API error %s: %s", e.status_code, e.message)
            return f"[LLM Error] API returned {e.status_code}: {e.message}"
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            last_transient_err = (
                "Request timed out" if isinstance(e, openai.APITimeoutError)
                else f"Cannot connect to {LLM_BASE_URL} - is the server running?"
            )
            logger.warning(
                "transient error (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, e,
            )
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAYS[attempt])
                continue
            return f"[LLM Error] {last_transient_err}"
        except Exception as e:
            logger.exception("Unexpected error")
            return f"[LLM Error] {e}"

    return f"[LLM Error] {last_transient_err}"
