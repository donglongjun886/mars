"""CLI entry point: parse arguments and, eventually, subscribe to loop events."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from mars import __version__

DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MAX_STEPS = 40


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mars", description="A minimal CLI coding agent.")
    parser.add_argument(
        "--model",
        default=os.environ.get("MARS_MODEL", DEFAULT_MODEL),
        help="model id (env: MARS_MODEL)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MARS_BASE_URL", DEFAULT_BASE_URL),
        help="OpenAI-compatible base url (env: MARS_BASE_URL)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=int(os.environ.get("MARS_MAX_STEPS", DEFAULT_MAX_STEPS)),
        help="step limit per turn (env: MARS_MAX_STEPS)",
    )
    parser.add_argument(
        "--resume",
        metavar="SESSION",
        default=None,
        help="resume a session by id",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(
        f"mars: agent loop not implemented yet "
        f"(model={args.model}, base_url={args.base_url}, max_steps={args.max_steps})",
        file=sys.stderr,
    )
    return 1
