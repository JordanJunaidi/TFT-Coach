"""Minimal client for OpenAI-compatible APIs (Chat Completions and Embeddings).

Written on httpx rather than a vendor SDK so the request/response shapes stay visible,
and so any compatible provider (Gemini, Meta, OpenAI...) works by changing the base URL.
"""

import json
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

MAX_RETRIES = 5
# Free tiers enforce per-minute quotas, so short retries just fail again.
MIN_BACKOFF = 10.0
MAX_BACKOFF = 60.0


class LLMAPIError(Exception):
    def __init__(self, status_code: int, path: str, body: str) -> None:
        super().__init__(f"LLM API returned {status_code} for {path}: {_summarize(body)}")
        self.status_code = status_code


def _summarize(body: str) -> str:
    """The error message plus any quota violation, which is what explains a 429."""
    try:
        data = json.loads(body)
        error = (data[0] if isinstance(data, list) else data)["error"]
    except (ValueError, KeyError, IndexError, TypeError):
        return body[:300]
    message = str(error.get("message", "")).split("\n")[0][:200]
    quotas = [
        f"{v.get('quotaId')} (limit {v.get('quotaValue')})"
        for d in error.get("details", [])
        for v in d.get("violations", [])
    ]
    return message + (f" Quota: {', '.join(quotas)}" if quotas else "")


def retry_delay(response: httpx.Response, attempt: int) -> float | None:
    """Seconds to wait before retrying, or None if the server asks for longer than we'd wait.

    Uses Retry-After, then Gemini's retryDelay, then exponential backoff. A daily quota
    comes back as e.g. retryDelay "85045s"; retrying that just burns time, so give up.
    """
    if retry_after := response.headers.get("Retry-After"):
        requested = float(retry_after)
    else:
        try:
            # Gemini puts {"retryDelay": "34s"} in the error details instead of a header.
            body = json.dumps(response.json())
            match = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', body)
        except ValueError:
            match = None
        if not match:
            return min(MIN_BACKOFF * 2**attempt, MAX_BACKOFF)
        requested = float(match.group(1)) + 1
    return requested if requested <= MAX_BACKOFF else None


class OpenAICompatClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = httpx.Client(
            # A trailing slash makes relative paths ("chat/completions") append to the base.
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )
        self._sleep = sleep

    def close(self) -> None:
        self._http.close()

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST JSON, retrying timeouts and 429/503 with backoff (or the server's delay)."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._http.post(path, json=payload)
            except httpx.TimeoutException:
                # Free-tier latency is spiky; a slow request usually succeeds on retry.
                if attempt == MAX_RETRIES:
                    raise
                continue
            if response.status_code in (429, 503) and attempt < MAX_RETRIES:
                delay = retry_delay(response, attempt)
                if delay is not None:
                    self._sleep(delay)
                    continue
            if response.is_error:
                # Path only: the Authorization header must never reach an error message.
                raise LLMAPIError(response.status_code, path, response.text)
            data = response.json()
            # Gemini's compatibility layer wraps some responses in a one-element list.
            return data[0] if isinstance(data, list) else data
        raise AssertionError("unreachable")
