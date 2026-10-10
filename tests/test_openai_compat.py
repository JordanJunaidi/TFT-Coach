import httpx
import pytest

from tftcoach.openai_compat import LLMAPIError, OpenAICompatClient, retry_delay
from tftcoach.rag.embed import APIEmbedder
from tftcoach.ratelimit import RateLimiter


def client(handler, sleeps: list[float]) -> OpenAICompatClient:
    return OpenAICompatClient(
        "https://llm.example/v1beta/openai/", "secret-key",
        transport=httpx.MockTransport(handler), sleep=sleeps.append,
    )  # fmt: skip


def test_retry_delay_prefers_header_then_gemini_body() -> None:
    assert retry_delay(httpx.Response(429, headers={"Retry-After": "5"}), 0) == 5
    body = {"error": {"details": [{"retryDelay": "34s"}]}}
    assert retry_delay(httpx.Response(429, json=body), 0) == 35
    assert retry_delay(httpx.Response(429), 0) == 10
    assert retry_delay(httpx.Response(429), 5) == 60  # capped


def test_daily_quota_fails_fast_with_readable_error() -> None:
    body = {
        "error": {
            "message": "You exceeded your current quota.\n* details",
            "details": [
                {"violations": [{"quotaId": "RequestsPerDay-FreeTier", "quotaValue": "20"}]},
                {"retryDelay": "85045s"},
            ],
        }
    }
    sleeps: list[float] = []
    c = client(lambda r: httpx.Response(429, json=[body]), sleeps)

    with pytest.raises(LLMAPIError) as exc_info:
        c.post("chat/completions", {})

    assert sleeps == []  # no pointless retries
    assert "RequestsPerDay-FreeTier (limit 20)" in str(exc_info.value)


def test_post_retries_rate_limits_and_unwraps_list_responses() -> None:
    responses = iter([httpx.Response(429), httpx.Response(200, json=[{"ok": True}])])
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1beta/openai/chat/completions"
        assert request.headers["Authorization"] == "Bearer secret-key"
        return next(responses)

    assert client(handler, sleeps).post("chat/completions", {}) == {"ok": True}
    assert sleeps == [10]


def test_errors_do_not_leak_the_key() -> None:
    c = client(lambda r: httpx.Response(401, text="bad key"), [])
    with pytest.raises(LLMAPIError) as exc_info:
        c.post("chat/completions", {})
    assert "secret-key" not in str(exc_info.value)


def test_embedder_batches_and_handles_missing_index() -> None:
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        inputs = json.loads(request.content)["input"]
        sizes.append(len(inputs))
        # Gemini-style: no "index" field, results in input order.
        return httpx.Response(200, json={"data": [{"embedding": [float(len(t))]} for t in inputs]})

    embedder = APIEmbedder(client(handler, []), "m", 1, rate_limiter=RateLimiter(((1000, 1.0),)))
    vectors = embedder.embed(["a" * n for n in range(1, 121)])

    assert sizes == [50, 50, 20]
    assert vectors[:3] == [[1.0], [2.0], [3.0]] and vectors[-1] == [120.0]
