"""File-based transcription helper."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from whisperflow.config import apply_overrides
from whisperflow.errors import WhisperflowRuntimeError, UserInputError

EXECUTABLE_PATH = Path("/usr/local/bin/faster-whisper-gpu")
logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".ogg",
    ".opus",
    ".aac",
    ".wma",
    ".webm",
    ".mp4",
}


def run_transcribe(input_path: str, config: dict[str, Any], overrides: dict[str, Any]) -> list[str]:
    """Transcribe a single audio file using faster-whisper-gpu."""
    audio_path = Path(input_path)
    if not audio_path.exists():
        raise UserInputError(f"Input file not found: {audio_path}")
    if audio_path.is_dir():
        raise UserInputError(f"Input path is a directory: {audio_path}")
    if audio_path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))
        raise UserInputError(
            f"Unsupported audio format '{audio_path.suffix}'. Supported extensions: {supported}."
        )

    merged = apply_overrides(config, overrides)
    output_dir = Path(merged["output_dir"])
    if output_dir.exists() and not output_dir.is_dir():
        raise UserInputError(f"Output directory path is not a directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not EXECUTABLE_PATH.exists():
        raise WhisperflowRuntimeError(f"faster-whisper-gpu executable not found at {EXECUTABLE_PATH}.")
    if not EXECUTABLE_PATH.is_file():
        raise WhisperflowRuntimeError(f"faster-whisper-gpu path is not a file: {EXECUTABLE_PATH}.")
    if not os.access(EXECUTABLE_PATH, os.X_OK):
        raise WhisperflowRuntimeError(f"faster-whisper-gpu is not executable: {EXECUTABLE_PATH}.")

    command = [
        str(EXECUTABLE_PATH),
        "--model",
        merged["model"],
    ]
    logger.info(
        "Transcribing %s (model=%s task=%s output_format=%s output_dir=%s).",
        audio_path,
        merged["model"],
        merged["task"],
        merged["output_format"],
        output_dir,
    )
    language = merged["language"].strip().lower()
    if language != "auto":
        command.extend(["--language", merged["language"]])
    command.extend(
        [
            "--task",
            merged["task"],
            "--output_format",
            merged["output_format"],
            "--output_dir",
            str(output_dir),
            str(audio_path),
        ]
    )

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.strip() or "Unknown error."
        raise WhisperflowRuntimeError(f"Transcription failed for {audio_path}: {stderr}")

    output_file = output_dir / f"{audio_path.stem}.{merged['output_format']}"
    logger.info("Transcription complete: %s", output_file)
    return [str(output_file)]


__all__ = ["run_transcribe"]
