"""Thin OpenAI-compatible streaming client.

Turns one streaming Chat Completions call into a typed chunk sequence.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from openai import OpenAI, omit
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
from openai.types.completion_usage import CompletionUsage


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    cache_hit_tokens: int
    cache_miss_tokens: int
    reasoning_tokens: int


@dataclass(frozen=True)
class ReasoningDelta:
    text: str


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class Completion:
    content: str
    reasoning_content: str
    tool_calls: tuple[ToolCall, ...]
    finish_reason: str | None
    usage: Usage


Chunk = ReasoningDelta | TextDelta | Completion


class ChatClient(Protocol):
    def stream(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, object]],
        tools: Sequence[dict[str, object]] = (),
    ) -> Iterator[Chunk]: ...


@dataclass
class _ToolCallBuilder:
    id: str = ""
    name: str = ""
    arguments: str = ""


def _int_field(obj: object, name: str) -> int:
    value = getattr(obj, name, None)
    return value if isinstance(value, int) else 0


def _to_usage(raw: CompletionUsage) -> Usage:
    details = getattr(raw, "completion_tokens_details", None)
    return Usage(
        prompt_tokens=raw.prompt_tokens,
        completion_tokens=raw.completion_tokens,
        cache_hit_tokens=_int_field(raw, "prompt_cache_hit_tokens"),
        cache_miss_tokens=_int_field(raw, "prompt_cache_miss_tokens"),
        reasoning_tokens=_int_field(details, "reasoning_tokens"),
    )


class OpenAICompatibleClient:
    def __init__(self, *, model: str, base_url: str, api_key: str) -> None:
        if not base_url:
            raise ValueError("base_url must be a non-empty string")
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def stream(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, object]],
        tools: Sequence[dict[str, object]] = (),
    ) -> Iterator[Chunk]:
        payload: list[dict[str, object]] = [{"role": "system", "content": system}, *messages]
        typed_messages = cast(list[ChatCompletionMessageParam], payload)
        tools_payload = cast(list[ChatCompletionToolParam], list(tools)) if tools else omit
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=typed_messages,
            tools=tools_payload,
            stream=True,
            stream_options={"include_usage": True},
        )

        content: list[str] = []
        reasoning: list[str] = []
        builders: dict[int, _ToolCallBuilder] = {}
        finish_reason: str | None = None
        usage = Usage(0, 0, 0, 0, 0)

        with completion as stream:
            for chunk in stream:
                if chunk.usage is not None:
                    usage = _to_usage(chunk.usage)
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                reasoning_piece = getattr(delta, "reasoning_content", None)
                if reasoning_piece:
                    reasoning.append(reasoning_piece)
                    yield ReasoningDelta(reasoning_piece)

                if delta.content:
                    content.append(delta.content)
                    yield TextDelta(delta.content)

                for fragment in delta.tool_calls or ():
                    builder = builders.setdefault(fragment.index, _ToolCallBuilder())
                    if fragment.id and not builder.id:
                        builder.id = fragment.id
                    function = fragment.function
                    if function is not None:
                        if function.name and not builder.name:
                            builder.name = function.name
                        if function.arguments:
                            builder.arguments += function.arguments

                if choice.finish_reason is not None:
                    finish_reason = choice.finish_reason

        yield Completion(
            content="".join(content),
            reasoning_content="".join(reasoning),
            tool_calls=tuple(
                ToolCall(id=builder.id, name=builder.name, arguments=builder.arguments)
                for _, builder in sorted(builders.items())
            ),
            finish_reason=finish_reason,
            usage=usage,
        )
