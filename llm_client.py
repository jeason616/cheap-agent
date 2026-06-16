import sys

import openai
from openai import OpenAI

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, MAX_OUTPUT_CHARS

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    return _client


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [truncated at {limit} chars]"


def ask_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """Call an OpenAI-compatible LLM and return the response text."""
    if not system_prompt and not user_prompt:
        return "[LLM Error] system_prompt and user_prompt are both empty"

    try:
        client = _get_client()
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
        print(f"[llm_client] Authentication failed: {e}", file=sys.stderr)
        return f"[LLM Error] Authentication failed — check LLM_API_KEY"
    except openai.APIConnectionError as e:
        print(f"[llm_client] Connection failed: {e}", file=sys.stderr)
        return f"[LLM Error] Cannot connect to {LLM_BASE_URL} — is the server running?"
    except openai.APITimeoutError as e:
        print(f"[llm_client] Request timed out: {e}", file=sys.stderr)
        return f"[LLM Error] Request timed out"
    except openai.APIStatusError as e:
        print(f"[llm_client] API error {e.status_code}: {e}", file=sys.stderr)
        return f"[LLM Error] API returned {e.status_code}: {e.message}"
    except Exception as e:
        print(f"[llm_client] Unexpected error: {e}", file=sys.stderr)
        return f"[LLM Error] {e}"
