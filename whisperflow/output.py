"""Output helpers for Whisperflow transcripts."""

from __future__ import annotations

from pathlib import Path


def write_transcript(text: str, path: str) -> None:
    """Write transcript text to the provided path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(text)


__all__ = ["write_transcript"]
