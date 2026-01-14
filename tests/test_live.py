"""Tests for live capture helpers and dashboard stats."""

from __future__ import annotations

from datetime import datetime, timezone

from whisperflow.live import (
    _backup_existing_file,
    _preview_transcript,
    _read_transcript,
    _rms_energy,
    _trim_buffer,
)
from whisperflow.web_dashboard import LiveDashboard


def test_backup_existing_file_creates_timestamped_copy(tmp_path, monkeypatch) -> None:
    source = tmp_path / "live_raw.txt"
    source.write_text("hello", encoding="utf-8")

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    monkeypatch.setattr("whisperflow.live.datetime", FixedDateTime)

    _backup_existing_file(source)

    backup = tmp_path / "live_raw.txt.20240102T030405Z.bak"
    assert backup.exists()
    assert not source.exists()
    assert backup.read_text(encoding="utf-8") == "hello"


def test_dashboard_tracks_segment_success() -> None:
    dashboard = LiveDashboard(
        {
            "model": "small",
            "language": "en",
            "task": "transcribe",
            "output_format": "txt",
        }
    )

    dashboard.segment_started(1, 500.0)
    dashboard.segment_finished(1, 500.0, 250.0, True, "hello world")

    snapshot = dashboard.snapshot()
    assert snapshot["status"] == "listening"
    assert snapshot["segments_total"] == 1
    assert snapshot["segments_failed"] == 0
    assert snapshot["current_segment"] is None
    assert snapshot["total_audio_seconds"] == 0.5
    assert snapshot["total_transcribe_seconds"] == 0.25
    assert snapshot["realtime_factor"] == 0.5

    recent = snapshot["recent_segments"][0]
    assert recent["index"] == 1
    assert recent["success"] is True
    assert recent["transcript_chars"] == len("hello world")


def test_dashboard_tracks_segment_failure() -> None:
    dashboard = LiveDashboard(
        {
            "model": "small",
            "language": "en",
            "task": "transcribe",
            "output_format": "txt",
        }
    )

    dashboard.segment_started(2, 400.0)
    dashboard.segment_finished(2, 400.0, 100.0, False, "")

    snapshot = dashboard.snapshot()
    assert snapshot["segments_total"] == 1
    assert snapshot["segments_failed"] == 1
    assert snapshot["recent_segments"][0]["success"] is False


def test_rms_energy_and_trim_buffer() -> None:
    assert _rms_energy(b"") == 0.0
    loud = b"\x10\x27" * 4
    assert _rms_energy(loud) > 0.0

    buffer = [b"0" * 4, b"1" * 4]
    trimmed, buffer_ms = _trim_buffer(buffer, 4.0, 2, 1000, 1)
    assert len(trimmed) == 1
    assert buffer_ms <= 2.0


def test_preview_and_read_transcript(tmp_path) -> None:
    assert _preview_transcript("hello world", limit=5) == "hello"
    assert _preview_transcript("") == ""

    missing = _read_transcript([str(tmp_path / "missing.txt")])
    assert missing == ""
