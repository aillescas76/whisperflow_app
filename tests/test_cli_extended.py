"""Additional CLI coverage tests."""

from __future__ import annotations

import argparse
import types

from whisperflow import cli
from whisperflow.config import DEFAULT_CONFIG
import pytest

from whisperflow.errors import UserInputError, WhisperflowRuntimeError


def test_main_transcribe_invokes_handler(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def fake_load_config(_path: str) -> dict[str, object]:
        return DEFAULT_CONFIG

    def fake_setup_logging(_config: dict[str, object]) -> None:
        return None

    def fake_handle_transcribe(
        path: str, config: dict[str, object], overrides: dict[str, object]
    ) -> None:
        calls["path"] = path
        calls["overrides"] = overrides
        calls["model"] = config["model"]

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    monkeypatch.setattr(cli, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(cli, "_handle_transcribe", fake_handle_transcribe)

    result = cli.main(["transcribe", "audio.wav", "--model", "small"])
    assert result == 0
    assert calls["path"] == "audio.wav"
    assert calls["overrides"] == {"model": "small"}


def test_main_start_stop_status(monkeypatch) -> None:
    calls: dict[str, int] = {"start": 0, "stop": 0, "status": 0}

    monkeypatch.setattr(cli, "load_config", lambda _path: DEFAULT_CONFIG)
    monkeypatch.setattr(cli, "setup_logging", lambda _config: None)

    def fake_start(_config):
        calls["start"] += 1

    def fake_stop(_config):
        calls["stop"] += 1

    def fake_status():
        calls["status"] += 1

    monkeypatch.setattr(cli, "_handle_start", fake_start)
    monkeypatch.setattr(cli, "_handle_stop", fake_stop)
    monkeypatch.setattr(cli, "_handle_status", fake_status)

    assert cli.main(["start"]) == 0
    assert cli.main(["stop"]) == 0
    assert cli.main(["status"]) == 0
    assert calls == {"start": 1, "stop": 1, "status": 1}


def test_main_handles_errors(monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_config", lambda _path: DEFAULT_CONFIG)
    monkeypatch.setattr(cli, "setup_logging", lambda _config: None)

    def raise_error(*_args, **_kwargs):
        raise UserInputError("bad input")

    monkeypatch.setattr(cli, "_handle_batch", raise_error)
    result = cli.main(["batch", "./input"])
    assert result == 1


def test_extract_config_arg_rejects_missing_value() -> None:
    try:
        cli._extract_config_arg(["--config"])
    except UserInputError as exc:
        assert "Missing value" in str(exc)
    else:
        raise AssertionError("Expected UserInputError")


def test_extract_config_arg_rejects_empty_value() -> None:
    try:
        cli._extract_config_arg(["--config", ""])
    except UserInputError as exc:
        assert "Config path cannot be empty" in str(exc)
    else:
        raise AssertionError("Expected UserInputError")

    try:
        cli._extract_config_arg(["--config="])
    except UserInputError as exc:
        assert "Config path cannot be empty" in str(exc)
    else:
        raise AssertionError("Expected UserInputError")


def test_collect_overrides_populates_fields() -> None:
    args = argparse.Namespace(
        model="medium",
        language="en",
        task="translate",
        output_format="srt",
        output_dir="./out",
    )
    overrides = cli._collect_overrides(args)
    assert overrides == {
        "model": "medium",
        "language": "en",
        "task": "translate",
        "output_format": "srt",
        "output_dir": "./out",
    }


def test_main_handles_unexpected_exception(monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_config", lambda _path: DEFAULT_CONFIG)
    monkeypatch.setattr(cli, "setup_logging", lambda _config: None)

    def raise_error(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "_handle_transcribe", raise_error)
    result = cli.main(["transcribe", "audio.wav"])
    assert result == 1


def test_handle_helpers_raise_runtime_error(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # noqa: ANN001
        if name in {
            "whisperflow.daemon",
            "whisperflow.transcribe",
            "whisperflow.batch",
        }:
            raise ModuleNotFoundError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(WhisperflowRuntimeError, match="Live capture is not available"):
        cli._handle_start(DEFAULT_CONFIG)
    with pytest.raises(WhisperflowRuntimeError, match="Live capture is not available"):
        cli._handle_stop(DEFAULT_CONFIG)
    with pytest.raises(
        WhisperflowRuntimeError, match="Live capture status is not available"
    ):
        cli._handle_status()
    with pytest.raises(
        WhisperflowRuntimeError, match="File transcription is not available"
    ):
        cli._handle_transcribe("file.wav", DEFAULT_CONFIG, {})
    with pytest.raises(
        WhisperflowRuntimeError, match="Batch transcription is not available"
    ):
        cli._handle_batch("./input", DEFAULT_CONFIG, {})
