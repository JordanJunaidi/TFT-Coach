"""Text embeddings through an OpenAI-compatible /embeddings endpoint."""

from typing import Protocol

from tftcoach.openai_compat import OpenAICompatClient
from tftcoach.ratelimit import RateLimiter

BATCH_SIZE = 50
# Free-tier embedding quotas count each input text, not each request: indexing failed
# after ~106 texts in one minute. Pace inputs below that.
FREE_TIER_INPUT_LIMITS: tuple[tuple[int, float], ...] = ((80, 60.0),)


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class APIEmbedder:
    def __init__(
        self,
        client: OpenAICompatClient,
        model: str,
        dimensions: int,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._client = client
        self.model = model
        self.dimensions = dimensions
        self._rate_limiter = rate_limiter or RateLimiter(FREE_TIER_INPUT_LIMITS)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        # Batching keeps a full re-index to a handful of requests under free-tier limits.
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            for _ in batch:
                self._rate_limiter.acquire()
            data = self._client.post(
                "embeddings",
                {"model": self.model, "input": batch, "dimensions": self.dimensions},
            )
            items = data["data"]
            if len(items) != len(batch):
                raise ValueError(f"Asked for {len(batch)} embeddings, got {len(items)}")
            # OpenAI includes each item's input position; Gemini omits it and keeps order.
            ordered = sorted(enumerate(items), key=lambda pair: pair[1].get("index", pair[0]))
            vectors.extend(item["embedding"] for _, item in ordered)
        return vectors
