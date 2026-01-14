"""Tests for config loading and validation."""

import copy
from pathlib import Path

import pytest

from whisperflow.config import DEFAULT_CONFIG, apply_overrides, load_config
from whisperflow.errors import ConfigError


def _override(base: dict[str, object], overrides: dict[str, object]) -> dict[str, object]:
    return apply_overrides(copy.deepcopy(base), overrides)


def test_bool_values_are_rejected_for_int_fields() -> None:
    with pytest.raises(ConfigError, match="sample_rate"):
        _override(DEFAULT_CONFIG, {"live_capture": {"audio": {"sample_rate": True}}})

    with pytest.raises(ConfigError, match="chunk_ms"):
        _override(DEFAULT_CONFIG, {"live_capture": {"audio": {"chunk_ms": False}}})


def test_bool_values_are_rejected_for_float_fields() -> None:
    with pytest.raises(ConfigError, match="energy_threshold"):
        _override(DEFAULT_CONFIG, {"live_capture": {"vad": {"energy_threshold": True}}})


def test_nested_override_validation_rejects_bad_types() -> None:
    with pytest.raises(ConfigError, match="live_capture"):
        _override(DEFAULT_CONFIG, {"live_capture": "not-a-dict"})

    with pytest.raises(ConfigError, match="audio"):
        _override(DEFAULT_CONFIG, {"live_capture": {"audio": []}})


def test_load_config_applies_audio_and_vad_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    loaded = load_config(str(config_path))
    audio = loaded["live_capture"]["audio"]
    vad = loaded["live_capture"]["vad"]

    assert audio["sample_rate"] == DEFAULT_CONFIG["live_capture"]["audio"]["sample_rate"]
    assert audio["channels"] == DEFAULT_CONFIG["live_capture"]["audio"]["channels"]
    assert audio["chunk_ms"] == DEFAULT_CONFIG["live_capture"]["audio"]["chunk_ms"]
    assert vad["silence_ms"] == DEFAULT_CONFIG["live_capture"]["vad"]["silence_ms"]
    assert vad["min_speech_ms"] == DEFAULT_CONFIG["live_capture"]["vad"]["min_speech_ms"]
    assert vad["energy_threshold"] == DEFAULT_CONFIG["live_capture"]["vad"]["energy_threshold"]
    assert vad["max_buffer_ms"] == DEFAULT_CONFIG["live_capture"]["vad"]["max_buffer_ms"]
