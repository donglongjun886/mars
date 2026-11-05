from __future__ import annotations

import pytest

from mars.cli import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_STEPS,
    DEFAULT_MODEL,
    build_parser,
    main,
)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MARS_MODEL", raising=False)
    monkeypatch.delenv("MARS_BASE_URL", raising=False)
    monkeypatch.delenv("MARS_MAX_STEPS", raising=False)
    args = build_parser().parse_args([])
    assert args.model == DEFAULT_MODEL
    assert args.base_url == DEFAULT_BASE_URL
    assert args.max_steps == DEFAULT_MAX_STEPS
    assert args.resume is None


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARS_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("MARS_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("MARS_MAX_STEPS", "5")
    args = build_parser().parse_args([])
    assert args.model == "deepseek-v4-pro"
    assert args.base_url == "https://example.invalid"
    assert args.max_steps == 5


def test_cli_flags_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARS_MODEL", "deepseek-v4-pro")
    args = build_parser().parse_args(["--model", "deepseek-flash", "--max-steps", "7"])
    assert args.model == "deepseek-flash"
    assert args.max_steps == 7


def test_main_reports_unimplemented(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 1
    assert "not implemented" in capsys.readouterr().err
