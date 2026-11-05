"""Module entry point for `python -m mars` and the `mars` console script."""

from __future__ import annotations

import sys

from mars.cli import main as cli_main


def main() -> int:
    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
