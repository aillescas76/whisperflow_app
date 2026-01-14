"""Audio capture helpers for live transcription."""

from __future__ import annotations

import logging
import os
import queue
import select
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional, Protocol

from whisperflow.errors import WhisperflowRuntimeError

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class AudioChunk:
    """A single chunk of PCM audio data."""

    data: bytes
    sample_rate: int
    channels: int


class AudioCapture(Protocol):
    """Protocol for audio capture implementations."""

    def start(self) -> None:
        """Start capturing audio."""

    def read(self, timeout: float | None = None) -> AudioChunk | None:
        """Read the next chunk of audio data."""

    def stop(self) -> None:
        """Stop capturing audio."""


def open_audio_capture(
    backend: str,
    device: str | int,
    sample_rate: int,
    channels: int,
    chunk_ms: int,
) -> AudioCapture:
    """Create an audio capture backend based on configuration."""
    resolved = _resolve_backend(backend)
    if resolved == "sounddevice":
        return _SoundDeviceCapture(device, sample_rate, channels, chunk_ms)
    if resolved == "arecord":
        command = _build_arecord_command(device, sample_rate, channels)
        return _SubprocessCapture(command, sample_rate, channels, chunk_ms)
    if resolved == "pw-record":
        command = _build_pw_record_command(sample_rate, channels)
        return _SubprocessCapture(command, sample_rate, channels, chunk_ms)
    raise WhisperflowRuntimeError(f"Unsupported audio backend: {resolved}")


def _resolve_backend(backend: str) -> str:
    if backend != "auto":
        if backend == "sounddevice" and not _sounddevice_available():
            raise WhisperflowRuntimeError("sounddevice backend requested but the package is not available.")
        if backend in {"arecord", "pw-record"} and shutil.which(backend) is None:
            raise WhisperflowRuntimeError(f"{backend} backend requested but the executable is not available.")
        return backend

    if _sounddevice_available():
        return "sounddevice"
    if shutil.which("arecord") is not None:
        return "arecord"
    if shutil.which("pw-record") is not None:
        return "pw-record"
    raise WhisperflowRuntimeError("No supported audio capture backend is available (sounddevice, arecord, pw-record).")


def _sounddevice_available() -> bool:
    try:
        import sounddevice  # noqa: F401
    except ImportError:
        return False
    return True


def _default_sounddevice_samplerate(sounddevice_module, device: Optional[str | int]) -> int | None:
    try:
        info = sounddevice_module.query_devices(device, "input")
    except sounddevice_module.PortAudioError:
        return None
    if not info:
        return None
    default_rate = info.get("default_samplerate")
    if not default_rate:
        return None
    return int(default_rate)


def _build_arecord_command(device: str | int, sample_rate: int, channels: int) -> list[str]:
    command = [
        "arecord",
        "-q",
        "-f",
        "S16_LE",
        "-r",
        str(sample_rate),
        "-c",
        str(channels),
        "-t",
        "raw",
    ]
    if device != "default":
        device_value = f"plughw:{device}" if isinstance(device, int) else str(device)
        command.extend(["-D", device_value])
    return command


def _build_pw_record_command(sample_rate: int, channels: int) -> list[str]:
    return [
        "pw-record",
        "--rate",
        str(sample_rate),
        "--channels",
        str(channels),
        "--format",
        "s16",
        "--raw",
        "-",
    ]


class _SoundDeviceCapture:
    def __init__(self, device: str | int, sample_rate: int, channels: int, chunk_ms: int) -> None:
        self._device = device
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_ms = chunk_ms
        self._stream = None
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=100)

    def start(self) -> None:
        import sounddevice as sd

        device_value: Optional[str | int] = None if self._device == "default" else self._device
        frames_per_chunk = max(1, int(self._sample_rate * self._chunk_ms / 1000))

        def callback(indata, _frames, _time, _status) -> None:
            data = indata.tobytes()
            try:
                self._queue.put_nowait(data)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    return
                try:
                    self._queue.put_nowait(data)
                except queue.Full:
                    return

        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype="int16",
                blocksize=frames_per_chunk,
                device=device_value,
                callback=callback,
            )
            self._stream.start()
        except sd.PortAudioError as exc:
            fallback_rate = _default_sounddevice_samplerate(sd, device_value)
            if fallback_rate is None or fallback_rate == self._sample_rate:
                raise WhisperflowRuntimeError(f"Failed to open audio input: {exc}") from exc
            logger.warning(
                "Sounddevice sample rate %s unsupported; falling back to %s.",
                self._sample_rate,
                fallback_rate,
            )
            self._sample_rate = fallback_rate
            frames_per_chunk = max(1, int(self._sample_rate * self._chunk_ms / 1000))
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype="int16",
                blocksize=frames_per_chunk,
                device=device_value,
                callback=callback,
            )
            self._stream.start()

    def read(self, timeout: float | None = None) -> AudioChunk | None:
        try:
            data = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        return AudioChunk(data=data, sample_rate=self._sample_rate, channels=self._channels)

    def stop(self) -> None:
        if self._stream is None:
            return
        self._stream.stop()
        self._stream.close()
        self._stream = None


class _SubprocessCapture:
    def __init__(
        self,
        command: list[str],
        sample_rate: int,
        channels: int,
        chunk_ms: int,
    ) -> None:
        self._command = command
        self._sample_rate = sample_rate
        self._channels = channels
        frames_per_chunk = max(1, int(sample_rate * chunk_ms / 1000))
        self._chunk_bytes = frames_per_chunk * channels * 2
        self._process: subprocess.Popen[bytes] | None = None
        self._stdout_fd: int | None = None
        self._buffer = bytearray()

    def start(self) -> None:
        try:
            self._process = subprocess.Popen(
                self._command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise WhisperflowRuntimeError(f"Audio capture executable not found: {self._command[0]}") from exc
        if self._process.stdout is not None:
            self._stdout_fd = self._process.stdout.fileno()

    def read(self, timeout: float | None = None) -> AudioChunk | None:
        if self._process is None or self._process.stdout is None:
            return None
        if self._process.poll() is not None:
            stderr = ""
            if self._process.stderr is not None:
                stderr = self._process.stderr.read().decode("utf-8", errors="replace").strip()
            message = stderr or "Audio capture process exited unexpectedly."
            raise WhisperflowRuntimeError(message)
        if self._stdout_fd is None:
            return None
        if len(self._buffer) < self._chunk_bytes:
            ready, _, _ = select.select([self._stdout_fd], [], [], timeout)
            if not ready:
                return None
            try:
                data = os.read(self._stdout_fd, self._chunk_bytes - len(self._buffer))
            except OSError as exc:
                raise WhisperflowRuntimeError(f"Failed to read audio capture output: {exc}") from exc
            if not data:
                return None
            self._buffer.extend(data)
            if len(self._buffer) < self._chunk_bytes:
                return None

        data = bytes(self._buffer[: self._chunk_bytes])
        del self._buffer[: self._chunk_bytes]
        return AudioChunk(data=data, sample_rate=self._sample_rate, channels=self._channels)

    def stop(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.kill()
        self._stdout_fd = None
        self._buffer.clear()
        self._process = None


__all__ = ["AudioCapture", "AudioChunk", "open_audio_capture"]
