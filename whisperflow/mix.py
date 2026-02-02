"""Helpers for re-transcribing and mixing live capture transcripts."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from whisperflow.errors import WhisperflowRuntimeError
from whisperflow.output import write_transcript
from whisperflow.transcribe import run_transcribe
from whisperflow.tray import start_tray_indicator


def retranscribe_segments(
    segments_dir: Path,
    config: dict[str, Any],
    model_name: str,
    progress_callback: Callable[[Path], None] | None = None,
) -> list[str]:
    """Re-transcribe live input segments and return timestamped transcript lines."""
    if not segments_dir.exists() or not segments_dir.is_dir():
        return []

    retranscribe_dir = segments_dir / "retranscribed"
    retranscribe_dir.mkdir(parents=True, exist_ok=True)

    segment_paths = sorted(segments_dir.glob("segment_*.wav"))
    lines: list[str] = []
    for segment_path in segment_paths:
        try:
            output_files = run_transcribe(
                str(segment_path),
                config,
                {
                    "model": model_name,
                    "output_format": "json",
                    "output_dir": str(retranscribe_dir),
                },
            )
        except WhisperflowRuntimeError:
            output_files = []

        segments = _read_json_segments(output_files)
        if segments:
            base_time = _base_time_from_segments(segment_path, segments)
            for segment in segments:
                timestamp = _timestamp_from_seconds(base_time + segment["start"])
                text = segment["text"].strip()
                if text:
                    lines.append(f"{timestamp} {text}")
        try:
            if progress_callback:
                progress_callback(segment_path)
        except Exception:  # noqa: BLE001
            pass
    return lines


logger = logging.getLogger(__name__)


def mix_with_ollama(
    input_lines: list[str], output_lines: list[str], model_name: str
) -> str:
    """Mix input/output transcripts using local Ollama."""
    if not shutil.which("ollama"):
        raise WhisperflowRuntimeError("Ollama CLI not found in PATH.")

    prompt = _build_mix_prompt(input_lines, output_lines)
    result = subprocess.run(
        ["ollama", "run", model_name],
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        error_text = result.stderr.strip() or "Unknown Ollama error."
        raise WhisperflowRuntimeError(f"Ollama mix failed: {error_text}")

    return _sanitize_mixed_output(result.stdout)


def unload_ollama_models() -> list[str]:
    """Unload any running Ollama models to free GPU memory."""
    if not shutil.which("ollama"):
        return []

    result = subprocess.run(
        ["ollama", "ps"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        error_text = result.stderr.strip() or "Unknown Ollama error."
        logger.warning("Failed to list Ollama models: %s", error_text)
        return []

    models: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip() or line.lstrip().startswith("NAME"):
            continue
        parts = line.split()
        if parts:
            models.append(parts[0])

    unloaded: list[str] = []
    for model_name in models:
        stop_result = subprocess.run(
            ["ollama", "stop", model_name],
            text=True,
            capture_output=True,
            check=False,
        )
        if stop_result.returncode == 0:
            unloaded.append(model_name)
            continue
        error_text = stop_result.stderr.strip() or "Unknown Ollama error."
        logger.warning("Failed to stop Ollama model %s: %s", model_name, error_text)

    return unloaded


def run_mixing_process(config: dict[str, Any]) -> None:
    """Run mixing using existing raw transcripts."""
    output_dir = Path(config["output_dir"])
    live_config = config.get("live_capture", {})
    if not isinstance(live_config, dict):
        raise WhisperflowRuntimeError("Live capture config is missing or invalid.")

    raw_path = output_dir / live_config.get("raw_transcript_filename", "live_raw.txt")
    output_raw_path = output_dir / live_config.get(
        "output_raw_transcript_filename", "live_output_raw.txt"
    )

    input_lines = _read_raw_lines(raw_path)
    if not input_lines:
        raise WhisperflowRuntimeError(
            "No input transcript lines found. Run a capture first."
        )

    output_lines: list[str] = []
    if output_raw_path.exists():
        output_lines = _read_raw_lines(output_raw_path)

    mixing_config = config.get("mixing", {})
    mixing_enabled = True
    model_name = "glm-4.7-flash:latest"
    if isinstance(mixing_config, dict):
        mixing_enabled = mixing_config.get("enabled", True)
        model_name = mixing_config.get("ollama_model", model_name)

    if not mixing_enabled:
        mixed_text = merge_lines_fallback(input_lines, output_lines)
    else:
        mix_stop = threading.Event()
        start_tray_indicator(mix_stop, tooltip="Ollama mixing", icon_name="mix")
        try:
            mixed_text = mix_with_ollama(input_lines, output_lines, model_name)
            if not mixed_text:
                mixed_text = merge_lines_fallback(input_lines, output_lines)
        finally:
            mix_stop.set()

    final_name = live_config.get("final_transcript_filename", "transcript.txt")
    write_transcript(mixed_text, str(output_dir / final_name))


def _read_raw_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _read_json_segments(output_files: list[str]) -> list[dict[str, float | str]]:
    if not output_files:
        return []
    path = Path(output_files[0])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    segments = payload.get("segments")
    if not isinstance(segments, list):
        return []

    parsed: list[dict[str, float | str]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        start = segment.get("start")
        end = segment.get("end")
        text = segment.get("text")
        if not isinstance(start, (int, float)) or not isinstance(text, str):
            continue
        entry: dict[str, float | str] = {"start": float(start), "text": text}
        if isinstance(end, (int, float)):
            entry["end"] = float(end)
        parsed.append(entry)
    return parsed


def _base_time_from_segments(path: Path, segments: list[dict[str, float | str]]) -> float:
    if not segments:
        return path.stat().st_mtime
    last = segments[-1]
    last_end = last.get("end")
    last_start = last.get("start", 0.0)
    if isinstance(last_end, (int, float)):
        offset = float(last_end)
    elif isinstance(last_start, (int, float)):
        offset = float(last_start)
    else:
        offset = 0.0
    return max(path.stat().st_mtime - offset, 0.0)


def _timestamp_from_seconds(seconds: float) -> str:
    timestamp = datetime.fromtimestamp(seconds, tz=timezone.utc)
    return timestamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def _build_mix_prompt(input_lines: list[str], output_lines: list[str]) -> str:
    input_block = "\n".join(input_lines) if input_lines else "(none)"
    output_block = "\n".join(output_lines) if output_lines else "(none)"
    return (
        "You are a transcript mixer. Combine input mic and system output transcripts "
        "into a single chronological transcript.\n"
        "Output format (one line per entry):\n"
        "YYYY-MM-DDTHH:MM:SSZ speaker-1: text\n"
        "Use speaker-1 for mic input and speaker-2 for system output.\n"
        "Do not add commentary. Do not invent content. Use the provided timestamps.\n"
        "If timestamps collide, keep original order.\n"
        "Output only transcript lines. No analysis, no headings, no extra text.\n\n"
        "Mic input transcript lines:\n"
        f"{input_block}\n\n"
        "System output transcript lines:\n"
        f"{output_block}\n"
    )


def _sanitize_mixed_output(text: str) -> str:
    line_pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z speaker-\d+: .+$"
    )
    lines = [line.strip() for line in text.splitlines()]
    filtered = [line for line in lines if line_pattern.match(line)]
    return "\n".join(filtered)


def merge_lines_fallback(input_lines: list[str], output_lines: list[str]) -> str:
    """Fallback mixer that merges lines with speaker tags based on timestamps."""
    merged: list[tuple[str, int, str]] = []
    for index, line in enumerate(input_lines):
        parsed = _parse_timestamped_line(line)
        if not parsed:
            continue
        timestamp, text = parsed
        merged.append((timestamp, index, f"{timestamp} speaker-1: {text}"))
    offset = len(input_lines)
    for index, line in enumerate(output_lines):
        parsed = _parse_timestamped_line(line)
        if not parsed:
            continue
        timestamp, text = parsed
        merged.append((timestamp, offset + index, f"{timestamp} speaker-2: {text}"))
    merged.sort(key=lambda item: (item[0], item[1]))
    return "\n".join(entry[2] for entry in merged)


def _parse_timestamped_line(line: str) -> tuple[str, str] | None:
    match = re.match(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+(.+)$", line
    )
    if not match:
        return None
    timestamp = match.group(1)
    text = match.group(2).strip()
    if not text:
        return None
    return timestamp, text


__all__ = [
    "retranscribe_segments",
    "mix_with_ollama",
    "unload_ollama_models",
    "run_mixing_process",
    "merge_lines_fallback",
]
