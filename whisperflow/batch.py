"""Batch transcription helpers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from whisperflow.errors import WhisperflowRuntimeError, UserInputError
from whisperflow.transcribe import SUPPORTED_AUDIO_EXTENSIONS, run_transcribe

logger = logging.getLogger(__name__)

def run_batch(input_dir: str, config: dict[str, Any], overrides: dict[str, Any]) -> dict[str, list[str]]:
    """Transcribe all supported audio files in a folder."""
    folder_path = Path(input_dir)
    if not folder_path.exists():
        raise UserInputError(f"Input folder not found: {folder_path}")
    if not folder_path.is_dir():
        raise UserInputError(f"Input path is not a directory: {folder_path}")

    entries = [path for path in sorted(folder_path.iterdir()) if path.is_file()]
    audio_files = [
        path for path in entries if path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    ]
    unsupported_files = [
        path for path in entries if path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS
    ]

    successes: list[str] = []
    failures: list[str] = []
    skipped: list[str] = [str(path) for path in unsupported_files]

    for path in unsupported_files:
        logger.warning("Skipping unsupported file: %s", path)

    for audio_path in audio_files:
        try:
            output_files = run_transcribe(str(audio_path), config, overrides)
            successes.extend(output_files)
            logger.info("Transcribed: %s", audio_path)
        except (UserInputError, WhisperflowRuntimeError) as exc:
            failures.append(f"{audio_path} ({exc})")
            logger.warning("Failed: %s (%s)", audio_path, exc)

    summary = {
        "successes": successes,
        "failures": failures,
        "skipped": skipped,
    }
    logger.info(
        "Batch summary: %s succeeded, %s failed, %s skipped.",
        len(successes),
        len(failures),
        len(skipped),
    )
    return summary


__all__ = ["run_batch"]
