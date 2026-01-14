"""Live audio capture loop with silence-gated transcription."""

from __future__ import annotations

import logging
import math
import threading
import wave
from array import array
from pathlib import Path
from typing import Any

from whisperflow.audio import AudioChunk, open_audio_capture
from whisperflow.config import apply_overrides
from whisperflow.errors import WhisperflowRuntimeError
from whisperflow.transcribe import run_transcribe

logger = logging.getLogger(__name__)


def run_live_capture(config: dict[str, Any], overrides: dict[str, Any], stop_event: threading.Event) -> None:
    """Capture audio, transcribe buffered phrases, and append to a raw transcript file."""
    merged = apply_overrides(config, overrides)
    live_config = merged["live_capture"]
    audio_config = live_config["audio"]
    vad_config = live_config["vad"]

    output_dir = Path(merged["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_transcript_path = output_dir / live_config["raw_transcript_filename"]
    segments_dir = output_dir / "live_segments"
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

            if buffer_ms > vad_config["max_buffer_ms"]:
                buffer_chunks, buffer_ms = _trim_buffer(
                    buffer_chunks,
                    buffer_ms,
                    vad_config["max_buffer_ms"],
                    chunk.sample_rate,
                    chunk.channels,
                )

            if vad_config["enabled"]:
                energy = _rms_energy(chunk.data)
                if energy < vad_config["energy_threshold"]:
                    silence_ms += chunk_duration
                else:
                    silence_ms = 0.0
                    speech_ms += chunk_duration

                if silence_ms >= vad_config["silence_ms"] and speech_ms >= vad_config["min_speech_ms"]:
                    segment_index = _flush_buffer(
                        buffer_chunks,
                        chunk.sample_rate,
                        chunk.channels,
                        segments_dir,
                        merged,
                        segment_index,
                        raw_transcript_path,
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
                )
        finally:
            capture.stop()
            logger.info("Live capture stopped.")


def _flush_buffer(
    buffer_chunks: list[bytes],
    sample_rate: int,
    channels: int,
    segments_dir: Path,
    config: dict[str, Any],
    segment_index: int,
    raw_transcript_path: Path,
) -> int:
    if not buffer_chunks:
        return segment_index

    segment_index += 1
    segment_name = f"segment_{segment_index:06d}"
    wav_path = segments_dir / f"{segment_name}.wav"
    output_overrides = {
        "output_dir": str(segments_dir),
        "output_format": config["output_format"],
        "model": config["model"],
        "language": config["language"],
        "task": config["task"],
    }

    _write_wav(wav_path, buffer_chunks, sample_rate, channels)
    try:
        output_files = run_transcribe(str(wav_path), config, output_overrides)
    except WhisperflowRuntimeError as exc:
        logger.warning("Live transcription failed for %s: %s", wav_path, exc)
        _append_line(raw_transcript_path, f"[transcription failed: {exc}]")
        return segment_index

    transcript_text = _read_transcript(output_files)
    if transcript_text:
        _append_line(raw_transcript_path, transcript_text.strip())
    return segment_index


def _write_wav(path: Path, buffer_chunks: list[bytes], sample_rate: int, channels: int) -> None:
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
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
        handle.write("\n")


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


__all__ = ["run_live_capture"]
