"""Tests for file-based transcription wrapper."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from whisperflow.config import DEFAULT_CONFIG
from whisperflow.errors import WhisperflowRuntimeError, UserInputError
from whisperflow.transcribe import run_transcribe
import whisperflow.transcribe as transcribe


def _config_for(tmp_path: Path) -> dict[str, object]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["output_dir"] = str(tmp_path / "output")
    return config


def _make_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\n")
    os.chmod(path, 0o755)


def test_missing_input_file_raises_error(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    with pytest.raises(UserInputError, match="Input file not found"):
        run_transcribe(str(tmp_path / "missing.wav"), config, {})


def test_directory_input_raises_error(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    input_dir = tmp_path / "input_dir"
    input_dir.mkdir()
    with pytest.raises(UserInputError, match="Input path is a directory"):
        run_transcribe(str(input_dir), config, {})


def test_unsupported_extension_raises_error(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    input_path = tmp_path / "note.txt"
    input_path.write_text("not audio")
    with pytest.raises(UserInputError, match="Unsupported audio format"):
        run_transcribe(str(input_path), config, {})


def test_missing_executable_raises_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config_for(tmp_path)
    input_path = tmp_path / "audio.wav"
    input_path.write_bytes(b"fake")
    monkeypatch.setattr(transcribe, "EXECUTABLE_PATH", tmp_path / "missing-exec")
    with pytest.raises(WhisperflowRuntimeError, match="executable not found"):
        run_transcribe(str(input_path), config, {})


def test_command_omits_language_for_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config_for(tmp_path)
    input_path = tmp_path / "audio.wav"
    input_path.write_bytes(b"fake")
    exec_path = tmp_path / "faster-whisper-gpu"
    _make_executable(exec_path)
    monkeypatch.setattr(transcribe, "EXECUTABLE_PATH", exec_path)

    captured: dict[str, list[str]] = {}

    def fake_run(
        command: list[str], capture_output: bool, text: bool, check: bool
    ) -> SimpleNamespace:
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(transcribe.subprocess, "run", fake_run)

    outputs = run_transcribe(str(input_path), config, {})

    assert "--language" not in captured["command"]
    assert captured["command"][0] == str(exec_path)
    assert outputs == [str(Path(str(config["output_dir"])) / "audio.txt")]


def test_command_includes_language_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config_for(tmp_path)
    input_path = tmp_path / "audio.wav"
    input_path.write_bytes(b"fake")
    exec_path = tmp_path / "faster-whisper-gpu"
    _make_executable(exec_path)
    monkeypatch.setattr(transcribe, "EXECUTABLE_PATH", exec_path)

    captured: dict[str, list[str]] = {}

    def fake_run(
        command: list[str], capture_output: bool, text: bool, check: bool
    ) -> SimpleNamespace:
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(transcribe.subprocess, "run", fake_run)

    run_transcribe(str(input_path), config, {"language": "en"})

    assert "--language" in captured["command"]
    language_index = captured["command"].index("--language") + 1
    assert captured["command"][language_index] == "en"


def test_output_dir_must_be_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config_for(tmp_path)
    output_path = tmp_path / "output"
    output_path.write_text("not a dir", encoding="utf-8")
    config["output_dir"] = str(output_path)

    input_path = tmp_path / "audio.wav"
    input_path.write_bytes(b"fake")

    with pytest.raises(
        UserInputError, match="Output directory path is not a directory"
    ):
        run_transcribe(str(input_path), config, {})


def test_executable_must_be_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config_for(tmp_path)
    input_path = tmp_path / "audio.wav"
    input_path.write_bytes(b"fake")

    exec_path = tmp_path / "exec-dir"
    exec_path.mkdir()
    monkeypatch.setattr(transcribe, "EXECUTABLE_PATH", exec_path)

    with pytest.raises(WhisperflowRuntimeError, match="path is not a file"):
        run_transcribe(str(input_path), config, {})


def test_executable_must_be_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config_for(tmp_path)
    input_path = tmp_path / "audio.wav"
    input_path.write_bytes(b"fake")

    exec_path = tmp_path / "faster-whisper-gpu"
    exec_path.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(transcribe, "EXECUTABLE_PATH", exec_path)

    with pytest.raises(WhisperflowRuntimeError, match="not executable"):
        run_transcribe(str(input_path), config, {})


def test_transcribe_reports_subprocess_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config_for(tmp_path)
    input_path = tmp_path / "audio.wav"
    input_path.write_bytes(b"fake")

    exec_path = tmp_path / "faster-whisper-gpu"
    _make_executable(exec_path)
    monkeypatch.setattr(transcribe, "EXECUTABLE_PATH", exec_path)

    def fake_run(
        command: list[str], capture_output: bool, text: bool, check: bool
    ) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(transcribe.subprocess, "run", fake_run)

    with pytest.raises(WhisperflowRuntimeError, match="Unknown error"):
        run_transcribe(str(input_path), config, {})
