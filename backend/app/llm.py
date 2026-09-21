"""
The model, behind one seam.

Everything that knows the Anthropic API lives here, so the Review loop is only
about what to ask and what to do with the answer, and a test scripts the
answers instead of reaching the network. The loop never sees a content block:
it is handed a `Reply` and hands back tool results.

The key and the model come from the environment and are read when a Review
actually runs, not when the app starts: an installation without a key still
serves every screen it has, and only the agent Review fails, loudly and in the
one place that was going to call the model.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic

DEFAULT_MODEL = "claude-sonnet-5"

# Enough for a handful of Insights in Spanish and nothing like enough to write
# an essay with: the answer is meant to be short.
MAX_TOKENS = 4096


class LLMUnavailable(Exception):
    """The model could not be reached, or there was no key to reach it with."""


@dataclass(frozen=True)
class ToolCall:
    """One use of a tool the model asked for, and the id its result answers."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Reply:
    """
    One turn of the model: what it said, what it wants to run, what it cost.

    A turn with no tool calls is the model having nothing left to do, which is
    how the loop knows it is over.
    """

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0

    def as_turn(self) -> dict:
        """The assistant turn to append to the conversation, as JSON."""
        content: list[dict] = []
        if self.text:
            content.append({"type": "text", "text": self.text})
        content.extend(
            {
                "type": "tool_use",
                "id": call.id,
                "name": call.name,
                "input": call.arguments,
            }
            for call in self.tool_calls
        )
        return {"role": "assistant", "content": content}


class LLMClient(Protocol):
    """One turn of a tool-use conversation with a model."""

    async def reply(
        self, system: str, messages: list[dict], tools: list[dict]
    ) -> Reply: ...


class AnthropicClient:
    """
    The Claude Messages API, one turn at a time.

    It keeps no conversation of its own: the loop owns the messages, which is
    what lets the whole exchange be stored on the Review as it happened.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._model = model or os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)

    async def reply(
        self, system: str, messages: list[dict], tools: list[dict]
    ) -> Reply:
        if not self._api_key:
            raise LLMUnavailable(
                "ANTHROPIC_API_KEY is not set, so no Review can call the model"
            )
        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        try:
            answer = await client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,
                tools=tools,
            )
        except anthropic.AnthropicError as error:
            raise LLMUnavailable(f"the model did not answer: {error}") from error
        finally:
            await client.close()
        return _read(answer)


def _read(answer: Any) -> Reply:
    """The API's content blocks as the loop wants them."""
    return Reply(
        text="".join(
            block.text for block in answer.content if block.type == "text"
        ),
        tool_calls=tuple(
            ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
            for block in answer.content
            if block.type == "tool_use"
        ),
        input_tokens=answer.usage.input_tokens,
        output_tokens=answer.usage.output_tokens,
    )


def get_llm_client() -> LLMClient:
    return AnthropicClient()
