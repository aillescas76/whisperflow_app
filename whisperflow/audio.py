"""Audio capture helpers for live transcription."""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import select
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Optional, Protocol

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
    if resolved == "pw-record":
        target = None
        if device == "default":
            target = _resolve_pw_target_source()
        else:
            target = str(device)
        if target:
            logger.info("pw-record input target: %s", target)
        command = _build_pw_record_command(sample_rate, channels, target=target)
        return _SubprocessCapture(command, sample_rate, channels, chunk_ms)
    if resolved == "sounddevice":
        resolved_device = device
        default_source = None
        if device == "default":
            system_device = _resolve_system_default_device()
            if system_device is not None:
                resolved_device = system_device
                logger.info(
                    "Resolved system default input device to %s.", system_device
                )
            else:
                default_source = _pactl_default_source()
                if _should_use_pipewire(default_source):
                    if shutil.which("pw-record") is not None:
                        logger.info(
                            "Falling back to pw-record for bluetooth source '%s'.",
                            default_source,
                        )
                        command = _build_pw_record_command(
                            sample_rate, channels, target=default_source
                        )
                        return _SubprocessCapture(
                            command, sample_rate, channels, chunk_ms
                        )
                    logger.warning(
                        "Bluetooth source '%s' detected but pw-record is unavailable.",
                        default_source,
                    )
        return _SoundDeviceCapture(resolved_device, sample_rate, channels, chunk_ms)
    if resolved == "arecord":
        command = _build_arecord_command(device, sample_rate, channels)
        return _SubprocessCapture(command, sample_rate, channels, chunk_ms)
    if resolved == "pw-record":
        command = _build_pw_record_command(sample_rate, channels)
        return _SubprocessCapture(command, sample_rate, channels, chunk_ms)
    raise WhisperflowRuntimeError(f"Unsupported audio backend: {resolved}")


def open_output_capture(
    backend: str,
    device: str | int,
    sample_rate: int,
    channels: int,
    chunk_ms: int,
) -> AudioCapture:
    """Create an audio capture backend for system output monitoring."""
    resolved = _resolve_backend(backend)
    if resolved == "pw-record":
        target = None
        if device == "default":
            target = _resolve_pw_target_sink()
        else:
            target = str(device)
        if target:
            logger.info("pw-record output target: %s", target)
        command = _build_pw_record_command(sample_rate, channels, target=target)
        return _SubprocessCapture(command, sample_rate, channels, chunk_ms)
    if resolved == "sounddevice":
        resolved_device = device
        if device == "default":
            system_device = _resolve_system_default_output_device()
            if system_device is not None:
                resolved_device = system_device
                logger.info("Resolved system output device to %s.", system_device)
                return _SoundDeviceCapture(
                    resolved_device, sample_rate, channels, chunk_ms
                )

            sink_target = _pactl_default_sink()
            if sink_target and shutil.which("pw-record") is not None:
                logger.info(
                    "Using pw-record for output sink '%s'.",
                    sink_target,
                )
                command = _build_pw_record_command(
                    sample_rate, channels, target=sink_target
                )
                return _SubprocessCapture(command, sample_rate, channels, chunk_ms)
            if sink_target:
                logger.warning(
                    "Output sink '%s' detected but pw-record is unavailable.",
                    sink_target,
                )
            raise WhisperflowRuntimeError(
                "Unable to resolve system output device for capture. "
                "Ensure PipeWire default sink is available and pw-record is installed."
            )
        return _SoundDeviceCapture(resolved_device, sample_rate, channels, chunk_ms)
    if resolved == "arecord":
        raise WhisperflowRuntimeError(
            "arecord backend does not support output capture."
        )
    if resolved == "pw-record":
        target = None
        if device == "default":
            target = _pactl_default_sink()
            if not target:
                raise WhisperflowRuntimeError(
                    "Unable to resolve PipeWire default sink for output capture."
                )
        elif isinstance(device, str):
            target = device
        command = _build_pw_record_command(sample_rate, channels, target=target)
        return _SubprocessCapture(command, sample_rate, channels, chunk_ms)
    raise WhisperflowRuntimeError(f"Unsupported audio backend: {resolved}")


def _resolve_backend(backend: str) -> str:
    if backend != "auto":
        if backend == "sounddevice" and not _sounddevice_available():
            raise WhisperflowRuntimeError(
                "sounddevice backend requested but the package is not available."
            )
        if backend in {"arecord", "pw-record"} and shutil.which(backend) is None:
            raise WhisperflowRuntimeError(
                f"{backend} backend requested but the executable is not available."
            )
        return backend

    if shutil.which("pw-record") is not None:
        return "pw-record"
    if _sounddevice_available():
        return "sounddevice"
    if shutil.which("arecord") is not None:
        return "arecord"
    raise WhisperflowRuntimeError(
        "No supported audio capture backend is available (sounddevice, arecord, pw-record)."
    )


def _sounddevice_available() -> bool:
    try:
        import sounddevice  # noqa: F401
    except ImportError:
        return False
    return True


def _should_use_pipewire(default_source: str | None) -> bool:
    if not default_source:
        return False
    return default_source.startswith("bluez_input") or default_source.startswith(
        "bluez_output"
    )


def _resolve_system_default_device() -> str | int | None:
    default_source = _pactl_default_source()
    if not default_source:
        return None
    return _resolve_system_device_from_source(default_source, label="input")


def _resolve_system_default_output_device() -> str | int | None:
    monitor_source = _pactl_default_monitor_source()
    if not monitor_source:
        return None
    return _resolve_system_device_from_source(monitor_source, label="output")


def _resolve_system_device_from_source(
    source_name: str, *, label: str
) -> str | int | None:
    metadata = _pactl_source_metadata(source_name)
    try:
        import sounddevice as sd
    except ImportError:
        return None

    description = metadata.get("description")
    device_description = metadata.get("device_description")
    product_name = metadata.get("product_name")
    card_name = metadata.get("card_name")
    long_card_name = metadata.get("long_card_name")

    devices = list(sd.query_devices())
    best_index: int | None = None
    best_name = ""
    best_score = 0
    is_bluez = source_name.startswith("bluez_input") or source_name.startswith(
        "bluez_output"
    )

    logger.info("System default %s source: %s", label, source_name)
    for index, device in enumerate(devices):
        if not isinstance(device, dict):
            continue
        max_inputs = device.get("max_input_channels", 0)
        if not isinstance(max_inputs, int) or max_inputs <= 0:
            continue
        name = str(device.get("name", ""))
        normalized_name = _normalize_token(name)
        score = _score_device_match(
            source_name,
            description,
            device_description,
            product_name,
            card_name,
            long_card_name,
            device_name=name,
        )
        if (
            device_description
            and _normalize_token(device_description) == normalized_name
        ):
            score += 10
        if description and _normalize_token(description) == normalized_name:
            score += 6
        if is_bluez and "bluetooth" in normalized_name:
            score += 4
        if score > best_score:
            best_index = index
            best_score = score
            best_name = name

    if best_score == 0 and is_bluez:
        fallback_tokens = _collect_tokens(description, device_description, product_name)
        for index, device in enumerate(devices):
            if not isinstance(device, dict):
                continue
            max_inputs = device.get("max_input_channels", 0)
            if not isinstance(max_inputs, int) or max_inputs <= 0:
                continue
            name = str(device.get("name", ""))
            normalized_name = _normalize_token(name)
            if "bluetooth" not in normalized_name:
                continue
            if any(token in normalized_name for token in fallback_tokens):
                best_index = index
                best_name = name
                best_score = 1
                logger.info(
                    "Fallback bluetooth match for '%s' resolved to %s (%s).",
                    source_name,
                    best_index,
                    best_name,
                )
                break

    if best_score == 0:
        logger.warning(
            "Unable to map system default source '%s' to a sounddevice input.",
            source_name,
        )
        _log_sounddevice_inputs(devices)
        return None

    logger.info(
        "Mapped default source '%s' to sounddevice input %s (%s).",
        source_name,
        best_index,
        best_name,
    )
    return best_index


def _log_sounddevice_inputs(devices: list[Any]) -> None:
    inputs = []
    for index, device in enumerate(devices):
        if not isinstance(device, dict):
            continue
        max_inputs = device.get("max_input_channels", 0)
        if not isinstance(max_inputs, int) or max_inputs <= 0:
            continue
        name = str(device.get("name", ""))
        inputs.append(f"{index}: {name}")
    if inputs:
        logger.warning("Available sounddevice inputs: %s", "; ".join(inputs))


def _pactl_default_source() -> str | None:
    info = _pactl_info()
    if not info:
        return None
    return info.get("default_source")


def _pactl_default_sink() -> str | None:
    info = _pactl_info()
    if not info:
        return None
    return info.get("default_sink")


def _pw_dump_nodes() -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            ["pw-dump"], capture_output=True, text=True, check=False
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _pw_find_node_serial(
    nodes: list[dict[str, Any]], name: str, media_class: str
) -> int | None:
    for item in nodes:
        if item.get("type") != "PipeWire:Interface:Node":
            continue
        info = item.get("info")
        if not isinstance(info, dict):
            continue
        props = info.get("props")
        if not isinstance(props, dict):
            continue
        if props.get("media.class") != media_class:
            continue
        if props.get("node.name") == name:
            serial = props.get("object.serial")
            if isinstance(serial, int):
                return serial
    return None


def _resolve_pw_target_source() -> str | None:
    default_source = _pactl_default_source()
    if not default_source:
        return None
    nodes = _pw_dump_nodes()
    node_serial = _pw_find_node_serial(nodes, default_source, "Audio/Source")
    if node_serial is not None:
        return str(node_serial)
    return default_source


def _resolve_pw_target_sink() -> str | None:
    default_sink = _pactl_default_sink()
    if not default_sink:
        return None
    nodes = _pw_dump_nodes()
    node_serial = _pw_find_node_serial(nodes, default_sink, "Audio/Sink")
    if node_serial is not None:
        return str(node_serial)
    return default_sink


def _pactl_default_monitor_source() -> str | None:
    default_sink = _pactl_default_sink()
    if not default_sink:
        return None
    monitor = f"{default_sink}.monitor"
    if _pactl_has_source(monitor):
        return monitor
    return None


def _pactl_info() -> dict[str, str]:
    try:
        result = subprocess.run(
            ["pactl", "info"], capture_output=True, text=True, check=False
        )
    except OSError:
        return {}
    if result.returncode != 0:
        return {}
    info: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if line.startswith("Default Source:"):
            info["default_source"] = line.split(":", 1)[1].strip()
        if line.startswith("Default Sink:"):
            info["default_sink"] = line.split(":", 1)[1].strip()
    return info


def _pactl_has_source(source_name: str) -> bool:
    try:
        result = subprocess.run(
            ["pactl", "list", "sources", "short"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    if result.returncode != 0:
        return False
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) > 1 and parts[1] == source_name:
            return True
    return False


def _pactl_source_metadata(source_name: str) -> dict[str, str]:
    try:
        result = subprocess.run(
            ["pactl", "list", "sources"], capture_output=True, text=True, check=False
        )
    except OSError:
        return {}
    if result.returncode != 0:
        return {}

    metadata: dict[str, str] = {}
    in_block = False
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("Source #"):
            in_block = False
        if stripped.startswith("Name:"):
            in_block = stripped.split(":", 1)[1].strip() == source_name
        if not in_block:
            continue
        if stripped.startswith("Description:"):
            metadata["description"] = stripped.split(":", 1)[1].strip()
        if stripped.startswith("device.description ="):
            metadata["device_description"] = (
                stripped.split("=", 1)[1].strip().strip('"')
            )
        if stripped.startswith("device.product.name ="):
            metadata["product_name"] = stripped.split("=", 1)[1].strip().strip('"')
        if stripped.startswith("alsa.card_name ="):
            metadata["card_name"] = stripped.split("=", 1)[1].strip().strip('"')
        if stripped.startswith("alsa.long_card_name ="):
            metadata["long_card_name"] = stripped.split("=", 1)[1].strip().strip('"')
    return metadata


def _score_device_match(*candidates: str | None, device_name: str) -> int:
    normalized_name = _normalize_token(device_name)
    score = 0
    for candidate in candidates:
        if not candidate:
            continue
        normalized_candidate = _normalize_token(candidate)
        if not normalized_candidate:
            continue
        if normalized_candidate in normalized_name:
            score += 5
        for token in _tokenize(candidate):
            if token in normalized_name:
                score += 1
    return score


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _tokenize(value: str) -> list[str]:
    tokens = re.split(r"[^a-z0-9]+", value.lower())
    return [token for token in tokens if len(token) > 2]


def _collect_tokens(*values: str | None) -> list[str]:
    tokens: list[str] = []
    for value in values:
        if not value:
            continue
        tokens.extend(_tokenize(value))
    return list(dict.fromkeys(tokens))


def _default_sounddevice_samplerate(
    sounddevice_module, device: Optional[str | int]
) -> int | None:
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


def _build_arecord_command(
    device: str | int, sample_rate: int, channels: int
) -> list[str]:
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


def _build_pw_record_command(
    sample_rate: int, channels: int, target: str | None = None
) -> list[str]:
    command = [
        "pw-record",
        "--rate",
        str(sample_rate),
        "--channels",
        str(channels),
        "--format",
        "s16",
        "--raw",
    ]
    if target:
        command.extend(["--target", target])
    command.append("-")
    return command


class _SoundDeviceCapture:
    def __init__(
        self, device: str | int, sample_rate: int, channels: int, chunk_ms: int
    ) -> None:
        self._device = device
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_ms = chunk_ms
        self._stream = None
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=100)

    def start(self) -> None:
        import sounddevice as sd

        device_value: Optional[str | int] = (
            None if self._device == "default" else self._device
        )
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
                raise WhisperflowRuntimeError(
                    f"Failed to open audio input: {exc}"
                ) from exc
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
        return AudioChunk(
            data=data, sample_rate=self._sample_rate, channels=self._channels
        )

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
            raise WhisperflowRuntimeError(
                f"Audio capture executable not found: {self._command[0]}"
            ) from exc
        if self._process.stdout is not None:
            self._stdout_fd = self._process.stdout.fileno()

    def read(self, timeout: float | None = None) -> AudioChunk | None:
        if self._process is None or self._process.stdout is None:
            return None
        if self._process.poll() is not None:
            stderr = ""
            if self._process.stderr is not None:
                stderr = (
                    self._process.stderr.read()
                    .decode("utf-8", errors="replace")
                    .strip()
                )
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
                raise WhisperflowRuntimeError(
                    f"Failed to read audio capture output: {exc}"
                ) from exc
            if not data:
                return None
            self._buffer.extend(data)
            if len(self._buffer) < self._chunk_bytes:
                return None

        data = bytes(self._buffer[: self._chunk_bytes])
        del self._buffer[: self._chunk_bytes]
        return AudioChunk(
            data=data, sample_rate=self._sample_rate, channels=self._channels
        )

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


__all__ = ["AudioCapture", "AudioChunk", "open_audio_capture", "open_output_capture"]
