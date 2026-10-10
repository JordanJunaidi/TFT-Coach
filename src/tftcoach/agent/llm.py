"""Chat model interface for the agent loop."""

from typing import Any, Protocol

from tftcoach.openai_compat import OpenAICompatClient

Message = dict[str, Any]


class ChatModel(Protocol):
    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> Message:
        """Return the assistant message (content and/or tool_calls) for this conversation."""
        ...


class APIChatModel:
    """Chat Completions over any OpenAI-compatible endpoint."""

    def __init__(self, client: OpenAICompatClient, model: str) -> None:
        self._client = client
        self.model = model

    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> Message:
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:  # an empty tools list forces a plain-text answer
            payload |= {"tools": tools, "tool_choice": "auto"}
        data = self._client.post("chat/completions", payload)
        return data["choices"][0]["message"]
