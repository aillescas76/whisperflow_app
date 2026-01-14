"""Tests for CLI argument parsing."""

import pytest

from whisperflow import cli


def test_help_includes_commands() -> None:
    parser = cli._build_parser()
    help_text = parser.format_help()
    for command in ("start", "stop", "status", "transcribe", "batch"):
        assert command in help_text
    assert "--output_format" in help_text


def test_parser_requires_command() -> None:
    parser = cli._build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args([])
    assert excinfo.value.code == 2
