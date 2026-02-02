"""Live audio capture loop with silence-gated transcription."""

from __future__ import annotations

import logging
import math
import threading
import time
import wave
from array import array
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from whisperflow.audio import AudioChunk, open_audio_capture, open_output_capture
from whisperflow.config import apply_overrides
from whisperflow.errors import WhisperflowRuntimeError
from whisperflow.model_utils import select_best_model
from whisperflow.transcribe import run_transcribe
from whisperflow.web_dashboard import LiveDashboard

logger = logging.getLogger(__name__)


def run_live_capture(
    config: dict[str, Any],
    overrides: dict[str, Any],
    stop_event: threading.Event,
    dashboard: LiveDashboard | None = None,
) -> None:
    """Capture audio, transcribe buffered phrases, and append to a raw transcript file."""
    merged = apply_overrides(config, overrides)
    live_config = merged["live_capture"]
    audio_config = live_config["audio"]
    vad_config = live_config["vad"]

    output_dir = Path(merged["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_transcript_path = output_dir / live_config["raw_transcript_filename"]
    final_transcript_path = output_dir / live_config["final_transcript_filename"]
    segments_dir = output_dir / "live_segments"

    _backup_existing_file(raw_transcript_path)
    _backup_existing_file(final_transcript_path)
    _backup_existing_dir(segments_dir)

    segments_dir.mkdir(parents=True, exist_ok=True)

    capture = open_audio_capture(
        live_config["backend"],
        audio_config["device"],
        audio_config["sample_rate"],
        audio_config["channels"],
        audio_config["chunk_ms"],
    )

    buffer_chunks: list[bytes] = []
    buffer_ms = 0.0
    silence_ms = 0.0
    speech_ms = 0.0
    segment_index = 0
    active_sample_rate = audio_config["sample_rate"]
    active_channels = audio_config["channels"]

    logger.info(
        "Live capture started: backend=%s device=%s sample_rate=%s channels=%s chunk_ms=%s",
        live_config["backend"],
        audio_config["device"],
        audio_config["sample_rate"],
        audio_config["channels"],
        audio_config["chunk_ms"],
    )

    capture.start()
    if dashboard:
        dashboard.set_status("listening")
    try:
        while not stop_event.is_set():
            chunk = capture.read(timeout=0.25)
            if chunk is None:
                continue
            active_sample_rate = chunk.sample_rate
            active_channels = chunk.channels
            chunk_duration = _chunk_duration_ms(chunk)
            buffer_chunks.append(chunk.data)
            buffer_ms += chunk_duration

            if vad_config["enabled"]:
                energy = _rms_energy(chunk.data)
                if energy < vad_config["energy_threshold"]:
                    silence_ms += chunk_duration
                else:
                    silence_ms = 0.0
                    speech_ms += chunk_duration

                if buffer_ms >= vad_config["max_buffer_ms"]:
                    if speech_ms >= vad_config["min_speech_ms"]:
                        segment_index = _flush_buffer(
                            buffer_chunks,
                            chunk.sample_rate,
                            chunk.channels,
                            segments_dir,
                            merged,
                            segment_index,
                            raw_transcript_path,
                            dashboard,
                        )
                        logger.info("Flushed live segment %s (max buffer)", segment_index)
                        buffer_chunks = []
                        buffer_ms = 0.0
                        silence_ms = 0.0
                        speech_ms = 0.0
                        continue
                    buffer_chunks, buffer_ms = _trim_buffer(
                        buffer_chunks,
                        buffer_ms,
                        vad_config["max_buffer_ms"],
                        chunk.sample_rate,
                        chunk.channels,
                    )

                if (
                    silence_ms >= vad_config["silence_ms"]
                    and speech_ms >= vad_config["min_speech_ms"]
                ):
                    segment_index = _flush_buffer(
                        buffer_chunks,
                        chunk.sample_rate,
                        chunk.channels,
                        segments_dir,
                        merged,
                        segment_index,
                        raw_transcript_path,
                        dashboard,
                    )

                    logger.info("Flushed live segment %s", segment_index)
                    buffer_chunks = []
                    buffer_ms = 0.0
                    silence_ms = 0.0
                    speech_ms = 0.0
            else:
                if buffer_ms >= vad_config["max_buffer_ms"]:
                    segment_index = _flush_buffer(
                        buffer_chunks,
                        chunk.sample_rate,
                        chunk.channels,
                        segments_dir,
                        merged,
                        segment_index,
                        raw_transcript_path,
                        dashboard,
                    )
                    logger.info("Flushed live segment %s", segment_index)
                    buffer_chunks = []
                    buffer_ms = 0.0
                    silence_ms = 0.0
                    speech_ms = 0.0
    finally:
        try:
            should_flush = buffer_chunks and (
                not vad_config["enabled"] or speech_ms >= vad_config["min_speech_ms"]
            )
            if should_flush:
                _flush_buffer(
                    buffer_chunks,
                    active_sample_rate,
                    active_channels,
                    segments_dir,
                    merged,
                    segment_index,
                    raw_transcript_path,
                    dashboard,
                )

        finally:
            capture.stop()
            if dashboard:
                dashboard.set_status("stopped")
            logger.info("Live capture stopped.")


def run_output_capture(
    config: dict[str, Any],
    overrides: dict[str, Any],
    stop_event: threading.Event,
    dashboard: LiveDashboard | None = None,
) -> None:
    """Capture system output audio and write to a separate transcript."""
    merged = apply_overrides(config, overrides)
    live_config = merged["live_capture"]
    audio_config = live_config["audio"]
    vad_config = live_config["output_vad"]

    output_dir = Path(merged["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_transcript_path = output_dir / live_config["output_raw_transcript_filename"]
    final_transcript_path = output_dir / live_config["output_final_transcript_filename"]
    segments_dir = output_dir / "live_output_segments"

    _backup_existing_file(raw_transcript_path)
    _backup_existing_file(final_transcript_path)
    _backup_existing_dir(segments_dir)

    segments_dir.mkdir(parents=True, exist_ok=True)

    capture = open_output_capture(
        live_config["backend"],
        audio_config["device"],
        audio_config["sample_rate"],
        audio_config["channels"],
        audio_config["chunk_ms"],
    )

    buffer_chunks: list[bytes] = []
    buffer_ms = 0.0
    silence_ms = 0.0
    speech_ms = 0.0
    segment_index = 0
    active_sample_rate = audio_config["sample_rate"]
    active_channels = audio_config["channels"]

    logger.info(
        "Output capture started: backend=%s device=%s sample_rate=%s channels=%s chunk_ms=%s",
        live_config["backend"],
        audio_config["device"],
        audio_config["sample_rate"],
        audio_config["channels"],
        audio_config["chunk_ms"],
    )

    capture.start()
    try:
        while not stop_event.is_set():
            chunk = capture.read(timeout=0.25)
            if chunk is None:
                continue
            active_sample_rate = chunk.sample_rate
            active_channels = chunk.channels
            chunk_duration = _chunk_duration_ms(chunk)
            buffer_chunks.append(chunk.data)
            buffer_ms += chunk_duration

            if vad_config["enabled"]:
                energy = _rms_energy(chunk.data)
                if energy < vad_config["energy_threshold"]:
                    silence_ms += chunk_duration
                else:
                    silence_ms = 0.0
                    speech_ms += chunk_duration

                if buffer_ms >= vad_config["max_buffer_ms"]:
                    if speech_ms >= vad_config["min_speech_ms"]:
                        segment_index = _flush_buffer(
                            buffer_chunks,
                            chunk.sample_rate,
                            chunk.channels,
                            segments_dir,
                            merged,
                            segment_index,
                            raw_transcript_path,
                            dashboard,
                            output_mode=True,
                        )
                        logger.info(
                            "Flushed output segment %s (max buffer)", segment_index
                        )
                        buffer_chunks = []
                        buffer_ms = 0.0
                        silence_ms = 0.0
                        speech_ms = 0.0
                        continue
                    buffer_chunks, buffer_ms = _trim_buffer(
                        buffer_chunks,
                        buffer_ms,
                        vad_config["max_buffer_ms"],
                        chunk.sample_rate,
                        chunk.channels,
                    )

                if (
                    silence_ms >= vad_config["silence_ms"]
                    and speech_ms >= vad_config["min_speech_ms"]
                ):
                    segment_index = _flush_buffer(
                        buffer_chunks,
                        chunk.sample_rate,
                        chunk.channels,
                        segments_dir,
                        merged,
                        segment_index,
                        raw_transcript_path,
                        dashboard,
                        output_mode=True,
                    )

                    logger.info("Flushed output segment %s", segment_index)
                    buffer_chunks = []
                    buffer_ms = 0.0
                    silence_ms = 0.0
                    speech_ms = 0.0
            else:
                if buffer_ms >= vad_config["max_buffer_ms"]:
                    segment_index = _flush_buffer(
                        buffer_chunks,
                        chunk.sample_rate,
                        chunk.channels,
                        segments_dir,
                        merged,
                        segment_index,
                        raw_transcript_path,
                        dashboard,
                        output_mode=True,
                    )
                    logger.info("Flushed output segment %s", segment_index)
                    buffer_chunks = []
                    buffer_ms = 0.0
                    silence_ms = 0.0
                    speech_ms = 0.0
    finally:
        try:
            should_flush = buffer_chunks and (
                not vad_config["enabled"] or speech_ms >= vad_config["min_speech_ms"]
            )
            if should_flush:
                _flush_buffer(
                    buffer_chunks,
                    active_sample_rate,
                    active_channels,
                    segments_dir,
                    merged,
                    segment_index,
                    raw_transcript_path,
                    dashboard,
                    output_mode=True,
                )

        finally:
            capture.stop()
            logger.info("Output capture stopped.")


def _flush_buffer(
    buffer_chunks: list[bytes],
    sample_rate: int,
    channels: int,
    segments_dir: Path,
    config: dict[str, Any],
    segment_index: int,
    raw_transcript_path: Path,
    dashboard: LiveDashboard | None,
    *,
    output_mode: bool = False,
) -> int:
    if not buffer_chunks:
        return segment_index

    segment_index += 1
    segment_name = f"segment_{segment_index:06d}"
    wav_path = segments_dir / f"{segment_name}.wav"
    output_overrides = {
        "output_dir": str(segments_dir),
        "output_format": config["output_format"],
        "model": select_best_model(config["model"]),
        "language": config["language"],
        "task": config["task"],
    }

    segment_audio_ms = _buffer_duration_ms(buffer_chunks, sample_rate, channels)
    if dashboard:
        if output_mode:
            dashboard.output_segment_started(segment_index, segment_audio_ms)
        else:
            dashboard.segment_started(segment_index, segment_audio_ms)

    _write_wav(wav_path, buffer_chunks, sample_rate, channels)
    start_time = time.perf_counter()
    try:
        output_files = run_transcribe(str(wav_path), config, output_overrides)
    except WhisperflowRuntimeError as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        logger.warning("Live transcription failed for %s: %s", wav_path, exc)
        _append_line(raw_transcript_path, f"[transcription failed: {exc}]")
        if dashboard:
            if output_mode:
                dashboard.output_mark_error(str(exc))
                dashboard.output_segment_finished(
                    segment_index, segment_audio_ms, elapsed_ms, False, ""
                )
            else:
                dashboard.mark_error(str(exc))
                dashboard.segment_finished(
                    segment_index, segment_audio_ms, elapsed_ms, False, ""
                )
        return segment_index

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    transcript_text = _read_transcript(output_files)
    preview = _preview_transcript(transcript_text)
    if transcript_text:
        _append_line(raw_transcript_path, transcript_text.strip())
        if dashboard:
            dashboard.append_transcript(transcript_text, output_mode=output_mode)
    if dashboard:
        if output_mode:
            dashboard.output_segment_finished(
                segment_index, segment_audio_ms, elapsed_ms, True, preview
            )
        else:
            dashboard.segment_finished(
                segment_index, segment_audio_ms, elapsed_ms, True, preview
            )
    return segment_index


def _write_wav(
    path: Path, buffer_chunks: list[bytes], sample_rate: int, channels: int
) -> None:
    data = b"".join(buffer_chunks)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(data)


def _read_transcript(output_files: list[str]) -> str:
    if not output_files:
        return ""
    path = Path(output_files[0])
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _append_line(path: Path, text: str) -> None:
    timestamp = _now_iso()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {text}\n")


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _rms_energy(data: bytes) -> float:
    samples = array("h")
    samples.frombytes(data)
    if not samples:
        return 0.0
    total = sum(sample * sample for sample in samples)
    mean_square = total / len(samples)
    return math.sqrt(mean_square) / 32768.0


def _chunk_duration_ms(chunk: AudioChunk) -> float:
    bytes_per_sample = 2
    frame_count = len(chunk.data) / (bytes_per_sample * chunk.channels)
    return (frame_count / chunk.sample_rate) * 1000.0


def _buffer_duration_ms(
    buffer_chunks: list[bytes], sample_rate: int, channels: int
) -> float:
    bytes_per_sample = 2
    total_bytes = sum(len(chunk) for chunk in buffer_chunks)
    frame_count = total_bytes / (bytes_per_sample * channels)
    return (frame_count / sample_rate) * 1000.0


def _preview_transcript(text: str, limit: int = 120) -> str:
    if not text:
        return ""
    cleaned = " ".join(text.strip().split())
    return cleaned[:limit]


def _backup_existing_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.{timestamp}.bak")
    counter = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.{timestamp}.{counter}.bak")
        counter += 1
    path.rename(backup_path)
    logger.info("Backed up %s to %s", path, backup_path)


def _backup_existing_dir(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.{timestamp}.bak")
    counter = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.{timestamp}.{counter}.bak")
        counter += 1
    path.rename(backup_path)
    logger.info("Backed up %s to %s", path, backup_path)


def _trim_buffer(
    buffer_chunks: list[bytes],
    buffer_ms: float,
    max_buffer_ms: int,
    sample_rate: int,
    channels: int,
) -> tuple[list[bytes], float]:
    bytes_per_sample = 2
    bytes_per_ms = (sample_rate * channels * bytes_per_sample) / 1000.0
    while buffer_chunks and buffer_ms > max_buffer_ms:
        removed = buffer_chunks.pop(0)
        buffer_ms -= len(removed) / bytes_per_ms
    return buffer_chunks, buffer_ms


__all__ = ["run_live_capture", "run_output_capture"]
