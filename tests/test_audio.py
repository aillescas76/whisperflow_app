"""Tests for audio capture helpers."""

from __future__ import annotations

import types

import pytest

from whisperflow import audio
from whisperflow.errors import WhisperflowRuntimeError


class FakeStream:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


def test_resolve_backend_prefers_sounddevice(monkeypatch) -> None:
    monkeypatch.setattr(audio, "_sounddevice_available", lambda: True)
    assert audio._resolve_backend("auto") == "sounddevice"


def test_resolve_backend_missing_backends(monkeypatch) -> None:
    monkeypatch.setattr(audio, "_sounddevice_available", lambda: False)
    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    with pytest.raises(
        WhisperflowRuntimeError, match="No supported audio capture backend"
    ):
        audio._resolve_backend("auto")


def test_build_arecord_command_handles_device() -> None:
    assert "-D" not in audio._build_arecord_command("default", 16000, 1)
    command = audio._build_arecord_command("hw:2", 16000, 2)
    assert command[-2:] == ["-D", "hw:2"]


def test_build_pw_record_command() -> None:
    command = audio._build_pw_record_command(8000, 1)
    assert command[:2] == ["pw-record", "--rate"]
    assert "--channels" in command


def test_build_pw_record_command_with_target() -> None:
    command = audio._build_pw_record_command(8000, 1, target="bluez_input.test")
    assert "--target" in command
    assert "bluez_input.test" in command


def test_sounddevice_capture_falls_back_on_sample_rate(monkeypatch) -> None:
    call_state = {"count": 0}

    class FakePortAudioError(Exception):
        pass

    def fake_input_stream(*_args, **_kwargs):
        if call_state["count"] == 0:
            call_state["count"] += 1
            raise FakePortAudioError("bad rate")
        return FakeStream()

    fake_module = types.SimpleNamespace(
        InputStream=fake_input_stream,
        PortAudioError=FakePortAudioError,
        query_devices=lambda *_: None,
    )

    monkeypatch.setitem(__import__("sys").modules, "sounddevice", fake_module)
    monkeypatch.setattr(audio, "_default_sounddevice_samplerate", lambda *_: 8000)

    capture = audio._SoundDeviceCapture("default", 16000, 1, 100)
    capture.start()

    assert capture._sample_rate == 8000
    capture.stop()


def test_subprocess_capture_reads_audio(monkeypatch) -> None:
    class FakeStdout:
        def fileno(self) -> int:
            return 3

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = FakeStdout()
            self.stderr = None

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout=None):  # noqa: ANN001
            return 0

    capture = audio._SubprocessCapture(["cmd"], 1000, 1, 100)
    capture._process = FakeProcess()  # type: ignore[assignment]
    capture._stdout_fd = 3

    monkeypatch.setattr(audio.select, "select", lambda *_: ([3], [], []))
    monkeypatch.setattr(audio.os, "read", lambda *_: b"0" * capture._chunk_bytes)

    chunk = capture.read(timeout=0.1)
    assert chunk is not None
    assert len(chunk.data) == capture._chunk_bytes
    capture.stop()


def test_subprocess_capture_reports_exit(monkeypatch) -> None:
    class FakeStdout:
        def fileno(self) -> int:
            return 3

    class FakeStderr:
        def read(self) -> bytes:
            return b"boom"

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = FakeStdout()
            self.stderr = FakeStderr()

        def poll(self) -> int:
            return 1

    capture = audio._SubprocessCapture(["cmd"], 1000, 1, 100)
    capture._process = FakeProcess()  # type: ignore[assignment]
    capture._stdout_fd = 3

    with pytest.raises(WhisperflowRuntimeError, match="boom"):
        capture.read(timeout=0.1)


def test_subprocess_start_missing_executable(monkeypatch) -> None:
    def raise_error(*_args, **_kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(audio.subprocess, "Popen", raise_error)
    capture = audio._SubprocessCapture(["missing"], 1000, 1, 100)

    with pytest.raises(WhisperflowRuntimeError, match="missing"):
        capture.start()


def test_open_audio_capture_arecord(monkeypatch) -> None:
    capture_instance = object()
    monkeypatch.setattr(audio, "_resolve_backend", lambda *_: "arecord")
    monkeypatch.setattr(audio, "_build_arecord_command", lambda *_: ["arecord"])
    monkeypatch.setattr(
        audio, "_SubprocessCapture", lambda *_args, **_kwargs: capture_instance
    )

    result = audio.open_audio_capture("arecord", "default", 16000, 1, 100)
    assert result is capture_instance


def test_open_audio_capture_pw_record(monkeypatch) -> None:
    capture_instance = object()
    monkeypatch.setattr(audio, "_resolve_backend", lambda *_: "pw-record")
    monkeypatch.setattr(audio, "_build_pw_record_command", lambda *_: ["pw-record"])
    monkeypatch.setattr(
        audio, "_SubprocessCapture", lambda *_args, **_kwargs: capture_instance
    )

    result = audio.open_audio_capture("pw-record", "default", 16000, 1, 100)
    assert result is capture_instance


def test_open_audio_capture_invalid_backend(monkeypatch) -> None:
    monkeypatch.setattr(audio, "_resolve_backend", lambda *_: "invalid")
    with pytest.raises(WhisperflowRuntimeError, match="Unsupported audio backend"):
        audio.open_audio_capture("invalid", "default", 16000, 1, 100)


def test_open_output_capture_invalid_backend(monkeypatch) -> None:
    monkeypatch.setattr(audio, "_resolve_backend", lambda *_: "invalid")
    with pytest.raises(WhisperflowRuntimeError, match="Unsupported audio backend"):
        audio.open_output_capture("invalid", "default", 16000, 1, 100)


def test_open_output_capture_missing_output_device(monkeypatch) -> None:
    monkeypatch.setattr(audio, "_resolve_backend", lambda *_: "sounddevice")
    monkeypatch.setattr(audio, "_resolve_system_default_output_device", lambda: None)
    monkeypatch.setattr(audio, "_pactl_default_sink", lambda: "default_sink")
    monkeypatch.setattr(audio.shutil, "which", lambda _name: None)

    with pytest.raises(
        WhisperflowRuntimeError, match="Unable to resolve system output device"
    ):
        audio.open_output_capture("sounddevice", "default", 16000, 1, 100)


def test_open_output_capture_arecord_unsupported(monkeypatch) -> None:
    monkeypatch.setattr(audio, "_resolve_backend", lambda *_: "arecord")
    with pytest.raises(
        WhisperflowRuntimeError, match="arecord backend does not support output capture"
    ):
        audio.open_output_capture("arecord", "default", 16000, 1, 100)


def test_open_output_capture_pw_record_without_sink(monkeypatch) -> None:
    monkeypatch.setattr(audio, "_resolve_backend", lambda *_: "pw-record")
    monkeypatch.setattr(audio, "_pactl_default_sink", lambda: None)
    with pytest.raises(
        WhisperflowRuntimeError,
        match="Unable to resolve PipeWire default sink",
    ):
        audio.open_output_capture("pw-record", "default", 16000, 1, 100)


def test_resolve_backend_requested_backend_missing(monkeypatch) -> None:
    monkeypatch.setattr(audio, "_sounddevice_available", lambda: False)
    monkeypatch.setattr(audio.shutil, "which", lambda _name: None)
    with pytest.raises(WhisperflowRuntimeError, match="arecord backend requested"):
        audio._resolve_backend("arecord")


def test_sounddevice_available_true(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", object())
    assert audio._sounddevice_available() is True


def test_default_sounddevice_samplerate(monkeypatch) -> None:
    class FakePortAudioError(Exception):
        pass

    class FakeModule:
        PortAudioError = FakePortAudioError

        @staticmethod
        def query_devices(_device, _kind):
            return {"default_samplerate": 44100}

    assert audio._default_sounddevice_samplerate(FakeModule, None) == 44100

    class ErrorModule:
        PortAudioError = FakePortAudioError

        @staticmethod
        def query_devices(_device, _kind):
            raise FakePortAudioError("bad")

    assert audio._default_sounddevice_samplerate(ErrorModule, None) is None


def test_sounddevice_capture_read_queue(monkeypatch) -> None:
    capture = audio._SoundDeviceCapture("default", 16000, 1, 100)
    assert capture.read(timeout=0.0) is None
    capture._queue.put(b"1234")
    chunk = capture.read(timeout=0.0)
    assert chunk is not None
    assert chunk.data == b"1234"


def test_subprocess_capture_read_without_process() -> None:
    capture = audio._SubprocessCapture(["cmd"], 1000, 1, 100)
    assert capture.read(timeout=0.0) is None


def test_subprocess_capture_returns_none_on_eof(monkeypatch) -> None:
    class FakeStdout:
        def fileno(self) -> int:
            return 3

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = FakeStdout()
            self.stderr = None

        def poll(self) -> None:
            return None

    capture = audio._SubprocessCapture(["cmd"], 1000, 1, 100)
    capture._process = FakeProcess()  # type: ignore[assignment]
    capture._stdout_fd = 3

    monkeypatch.setattr(audio.select, "select", lambda *_: ([3], [], []))
    monkeypatch.setattr(audio.os, "read", lambda *_: b"")

    assert capture.read(timeout=0.1) is None


def test_subprocess_capture_stop_without_process() -> None:
    capture = audio._SubprocessCapture(["cmd"], 1000, 1, 100)
    capture.stop()


def test_resolve_system_default_device_matches(monkeypatch) -> None:
    def fake_run(args, capture_output, text, check):  # noqa: ANN001
        if args[:2] == ["pactl", "info"]:
            return types.SimpleNamespace(
                returncode=0, stdout="Default Source: bluez_input.test\n"
            )
        return types.SimpleNamespace(
            returncode=0,
            stdout=(
                "Source #1\n"
                "\tName: bluez_input.test\n"
                "\tDescription: HD 450SE\n"
                "\tProperties:\n"
                '\t\talsa.card_name = "HD 450SE"\n'
            ),
        )

    fake_sd = types.SimpleNamespace(
        query_devices=lambda: [
            {"name": "HD 450SE Analog", "max_input_channels": 1},
            {"name": "Other", "max_input_channels": 1},
        ]
    )

    monkeypatch.setitem(__import__("sys").modules, "sounddevice", fake_sd)
    monkeypatch.setattr(audio.subprocess, "run", fake_run)

    assert audio._resolve_system_default_device() == 0


def test_resolve_system_default_device_without_pactl(monkeypatch) -> None:
    def raise_error(*_args, **_kwargs):
        raise OSError("missing pactl")

    monkeypatch.setattr(audio.subprocess, "run", raise_error)
    assert audio._resolve_system_default_device() is None


def test_resolve_system_default_output_device(monkeypatch) -> None:
    def fake_run(args, capture_output, text, check):  # noqa: ANN001
        if args[:2] == ["pactl", "info"]:
            return types.SimpleNamespace(
                returncode=0,
                stdout="Default Sink: bluez_output.test\n",
            )
        return types.SimpleNamespace(
            returncode=0,
            stdout=(
                "Source #1\n"
                "\tName: bluez_output.test.monitor\n"
                "\tDescription: HD 450SE Monitor\n"
                "\tProperties:\n"
                '\t\tdevice.description = "HD 450SE"\n'
            ),
        )

    fake_sd = types.SimpleNamespace(
        query_devices=lambda: [
            {"name": "HD 450SE Monitor", "max_input_channels": 1},
            {"name": "Other", "max_input_channels": 1},
        ]
    )

    monkeypatch.setitem(__import__("sys").modules, "sounddevice", fake_sd)
    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    monkeypatch.setattr(
        audio, "_pactl_default_monitor_source", lambda: "bluez_output.test.monitor"
    )

    assert audio._resolve_system_default_output_device() == 0


def test_open_audio_capture_bluetooth_fallback(monkeypatch) -> None:
    sentinel = object()

    monkeypatch.setattr(audio, "_resolve_backend", lambda *_: "sounddevice")
    monkeypatch.setattr(audio, "_resolve_system_default_device", lambda: None)
    monkeypatch.setattr(audio, "_pactl_default_source", lambda: "bluez_input.test")
    monkeypatch.setattr(
        audio, "_build_pw_record_command", lambda *_args, **_kwargs: ["pw-record"]
    )
    monkeypatch.setattr(audio.shutil, "which", lambda _name: "/usr/bin/pw-record")
    monkeypatch.setattr(audio, "_SubprocessCapture", lambda *_args, **_kwargs: sentinel)

    result = audio.open_audio_capture("sounddevice", "default", 16000, 1, 100)
    assert result is sentinel


def test_open_output_capture_bluetooth_fallback(monkeypatch) -> None:
    sentinel = object()

    monkeypatch.setattr(audio, "_resolve_backend", lambda *_: "sounddevice")
    monkeypatch.setattr(audio, "_resolve_system_default_output_device", lambda: None)
    monkeypatch.setattr(audio, "_pactl_default_sink", lambda: "bluez_output.test")
    monkeypatch.setattr(
        audio, "_build_pw_record_command", lambda *_args, **_kwargs: ["pw-record"]
    )
    monkeypatch.setattr(audio.shutil, "which", lambda _name: "/usr/bin/pw-record")
    monkeypatch.setattr(audio, "_SubprocessCapture", lambda *_args, **_kwargs: sentinel)

    result = audio.open_output_capture("sounddevice", "default", 16000, 1, 100)
    assert result is sentinel
