"""Test doubles for the embedding and chat APIs."""

import hashlib
import json
import re
from typing import Any

import numpy as np

DIMS = 768


# Bag-of-words cosine scores run lower than real embeddings, so tests that search through
# the agent tools lower the cutoff tuned for Gemini (see the `fake_search_cutoff` fixture).
FAKE_MIN_SCORE = 0.3


class FakeEmbedder:
    """Deterministic bag-of-words embeddings: texts sharing words get similar vectors."""

    model = "fake-embedding"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [self._vector(t) for t in texts]

    @staticmethod
    def _vector(text: str) -> list[float]:
        v = np.zeros(DIMS, dtype=np.float32)
        for word in re.findall(r"[a-z]+", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMS] += 1.0
        norm = np.linalg.norm(v)
        return (v / norm if norm else v).tolist()


class ScriptedModel:
    """Returns pre-written assistant messages in order and records what it was sent."""

    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.received: list[list[dict[str, Any]]] = []

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.received.append(json.loads(json.dumps(messages)))
        return self.replies.pop(0)


def tool_call(name: str, arguments: dict[str, Any], call_id: str = "call-1") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


def answer(text: str) -> dict[str, Any]:
    return {"role": "assistant", "content": text}
