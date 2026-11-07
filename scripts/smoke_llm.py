"""Manual smoke test against a live OpenAI-compatible API.

Not collected by pytest and not run in CI: it needs a live API key, spends
tokens, and depends on the network. Run it after changing the llm client or the
provider wiring:

    uv run python scripts/smoke_llm.py

Configuration, highest priority first: CLI flags, shell environment, then
``~/.mars/.env`` (``MARS_API_KEY``, falling back to ``DEEPSEEK_API_KEY``).

Checks: streaming works, usage is reported, a tool call assembles with parseable
JSON arguments, and a follow-up round that echoes ``reasoning_content`` is
accepted instead of rejected with HTTP 400.

Exit codes: 0 all checks passed, 1 a check failed, 2 configuration missing.

Known gap: the client does not expose a timeout yet, so the SDK default (600s)
applies and a hung request would block this script.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import openai

from mars.llm import Completion, OpenAICompatibleClient, ReasoningDelta

DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
SYSTEM = "You are a test harness for a coding agent API."

# The model's command is never executed, so this script has no side effects.
# The echo check only needs a well-formed tool result message.
TOOL_RESULT = "391\n"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command in the current directory.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "Command to run."}},
                "required": ["command"],
            },
        },
    }
]


def dump_request(
    label: str, system: str, messages: list[dict[str, object]], tools: list[dict[str, object]]
) -> None:
    print(f"\n=== {label} request ===")
    payload = {"system": system, "messages": messages, "tools": tools}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def dump_stream(label: str, chunks: list[object]) -> None:
    print(f"\n=== {label} stream ({len(chunks)} chunks) ===")
    for index, chunk in enumerate(chunks, 1):
        print(f"[{index:02d}] {type(chunk).__name__}: {chunk}")


def read_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines with the standard library only, like the future cli."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip().strip("'\"")
    return values


def resolve_api_key() -> str:
    key = os.environ.get("MARS_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    values = read_env_file(Path.home() / ".mars" / ".env")
    key = values.get("MARS_API_KEY") or values.get("DEEPSEEK_API_KEY")
    if key:
        return key
    print(
        "error: no MARS_API_KEY or DEEPSEEK_API_KEY in the environment or ~/.mars/.env",
        file=sys.stderr,
    )
    raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test mars.llm against a live API.")
    parser.add_argument("--model", default=os.environ.get("MARS_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=os.environ.get("MARS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument(
        "--verbose", action="store_true", help="dump each request and every streamed chunk"
    )
    args = parser.parse_args()

    client = OpenAICompatibleClient(
        model=args.model, base_url=args.base_url, api_key=resolve_api_key()
    )
    print(f"model={args.model} base_url={args.base_url} openai={openai.__version__}")

    messages: list[dict[str, object]] = [
        {
            "role": "user",
            "content": (
                "Think step by step: compute 17 * 23. Then use the bash tool to run "
                "`echo $((17*23))` to verify, and reply with the result."
            ),
        }
    ]

    if args.verbose:
        dump_request("round 1", SYSTEM, messages, TOOLS)
    first = list(client.stream(system=SYSTEM, messages=messages, tools=TOOLS))
    if args.verbose:
        dump_stream("round 1", first)
    completion = first[-1]
    if not isinstance(completion, Completion):
        raise AssertionError("the stream did not end with a Completion")
    reasoning_deltas = sum(isinstance(chunk, ReasoningDelta) for chunk in first)
    print(
        f"round 1: reasoning_deltas={reasoning_deltas} "
        f"content_chars={len(completion.content)} "
        f"tool_calls={len(completion.tool_calls)} usage={completion.usage}"
    )
    if not completion.tool_calls:
        raise AssertionError("expected the model to call a tool")
    for call in completion.tool_calls:
        json.loads(call.arguments)
    if not completion.reasoning_content:
        raise AssertionError("no reasoning_content; the echo check below would be vacuous")
    if completion.usage.prompt_tokens <= 0:
        raise AssertionError("usage was not reported")

    assistant: dict[str, object] = {
        "role": "assistant",
        "content": completion.content,
        "reasoning_content": completion.reasoning_content,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in completion.tool_calls
        ],
    }
    messages.append(assistant)
    for call in completion.tool_calls:
        messages.append({"role": "tool", "tool_call_id": call.id, "content": TOOL_RESULT})

    if args.verbose:
        dump_request("round 2", SYSTEM, messages, TOOLS)
    second = list(client.stream(system=SYSTEM, messages=messages, tools=TOOLS))
    if args.verbose:
        dump_stream("round 2", second)
    final = second[-1]
    if not isinstance(final, Completion):
        raise AssertionError("the stream did not end with a Completion")
    print(
        f"round 2: content={final.content!r} reasoning_chars={len(final.reasoning_content)} "
        f"finish_reason={final.finish_reason} usage={final.usage}"
    )
    print("PASS: echoed assistant message accepted, no HTTP 400")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
