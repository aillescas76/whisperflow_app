"""Tests for error formatting."""

from __future__ import annotations

from whisperflow.errors import (
    ConfigError,
    UserInputError,
    WhisperflowRuntimeError,
    format_error,
)


def test_format_error_prefixes() -> None:
    assert format_error(ConfigError("bad")) == "Config error: bad"
    assert format_error(UserInputError("missing")) == "Input error: missing"
    assert format_error(WhisperflowRuntimeError("boom")) == "Runtime error: boom"
    assert format_error(ValueError("nope")) == "Unexpected error: nope"
