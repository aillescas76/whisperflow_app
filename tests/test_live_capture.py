"""Tests for running a minimal live capture loop."""

from __future__ import annotations

import copy
import threading
import types
from pathlib import Path

from whisperflow.config import DEFAULT_CONFIG
from whisperflow.live import run_live_capture
from whisperflow.web_dashboard import LiveDashboard


def test_run_live_capture_writes_transcript(tmp_path, monkeypatch) -> None:
    stop_event = threading.Event()

    config = copy.deepcopy(DEFAULT_CONFIG)
    config["output_dir"] = str(tmp_path)
    config["live_capture"] = dict(config["live_capture"])
    config["live_capture"]["vad"] = {
        "enabled": False,
        "silence_ms": 500,
        "min_speech_ms": 250,
        "energy_threshold": 0.01,
        "max_buffer_ms": 1000,
    }
    config["live_capture"]["audio"] = {
        "device": "default",
        "sample_rate": 1000,
        "channels": 1,
        "chunk_ms": 1000,
    }

    class FakeCapture:
        def __init__(self) -> None:
            self.started = False
            self.calls = 0

        def start(self) -> None:
            self.started = True

        def read(self, timeout=None):  # noqa: ANN001
            self.calls += 1
            if self.calls == 1:
                data = b"1" * 2000
                return types.SimpleNamespace(data=data, sample_rate=1000, channels=1)
            stop_event.set()
            return None

        def stop(self) -> None:
            self.started = False

    monkeypatch.setattr("whisperflow.live.open_audio_capture", lambda *_: FakeCapture())

    def fake_run_transcribe(
        input_path: str, _config: dict, overrides: dict
    ) -> list[str]:
        output_dir = Path(overrides["output_dir"])
        output_file = (
            output_dir / f"{Path(input_path).stem}.{overrides['output_format']}"
        )
        output_file.write_text("hello", encoding="utf-8")
        return [str(output_file)]

    monkeypatch.setattr("whisperflow.live.run_transcribe", fake_run_transcribe)

    dashboard = LiveDashboard(config)
    run_live_capture(config, {}, stop_event, dashboard)

    raw_path = (
        Path(config["output_dir"]) / config["live_capture"]["raw_transcript_filename"]
    )
    assert raw_path.exists()
    assert "hello" in raw_path.read_text(encoding="utf-8")


def test_run_live_capture_with_vad(tmp_path, monkeypatch) -> None:
    stop_event = threading.Event()

    config = copy.deepcopy(DEFAULT_CONFIG)
    config["output_dir"] = str(tmp_path)
    config["live_capture"] = dict(config["live_capture"])
    config["live_capture"]["vad"] = {
        "enabled": True,
        "silence_ms": 500,
        "min_speech_ms": 250,
        "energy_threshold": 0.01,
        "max_buffer_ms": 5000,
    }
    config["live_capture"]["audio"] = {
        "device": "default",
        "sample_rate": 1000,
        "channels": 1,
        "chunk_ms": 500,
    }

    class FakeCapture:
        def __init__(self) -> None:
            self.calls = 0

        def start(self) -> None:
            return None

        def read(self, timeout=None):  # noqa: ANN001
            self.calls += 1
            if self.calls == 1:
                data = b"\x10\x27" * 500
                return types.SimpleNamespace(data=data, sample_rate=1000, channels=1)
            if self.calls == 2:
                data = b"\x00\x00" * 500
                return types.SimpleNamespace(data=data, sample_rate=1000, channels=1)
            stop_event.set()
            return None

        def stop(self) -> None:
            return None

    monkeypatch.setattr("whisperflow.live.open_audio_capture", lambda *_: FakeCapture())

    def fake_run_transcribe(
        input_path: str, _config: dict, overrides: dict
    ) -> list[str]:
        output_dir = Path(overrides["output_dir"])
        output_file = (
            output_dir / f"{Path(input_path).stem}.{overrides['output_format']}"
        )
        output_file.write_text("speech", encoding="utf-8")
        return [str(output_file)]

    monkeypatch.setattr("whisperflow.live.run_transcribe", fake_run_transcribe)

    dashboard = LiveDashboard(config)
    run_live_capture(config, {}, stop_event, dashboard)

    raw_path = (
        Path(config["output_dir"]) / config["live_capture"]["raw_transcript_filename"]
    )
    assert "speech" in raw_path.read_text(encoding="utf-8")
