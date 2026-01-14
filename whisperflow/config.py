"""Configuration loading and validation for Whisperflow."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from whisperflow.errors import ConfigError

ALLOWED_MODELS = {"small", "medium", "large-v3"}
ALLOWED_TASKS = {"transcribe", "translate"}
ALLOWED_OUTPUT_FORMATS = {"txt", "srt", "vtt", "json"}
ALLOWED_BACKENDS = {"auto", "sounddevice", "arecord", "pw-record"}
ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

DEFAULT_CONFIG: dict[str, Any] = {
    "output_dir": "./output",
    "model": "small",
    "language": "auto",
    "task": "transcribe",
    "output_format": "txt",
    "batch": False,
    "live_capture": {
        "enabled": True,
        "raw_transcript_filename": "live_raw.txt",
        "final_transcript_filename": "transcript.txt",
        "backend": "auto",
        "audio": {
            "device": "default",
            "sample_rate": 16000,
            "channels": 1,
            "chunk_ms": 1000,
        },
        "vad": {
            "enabled": True,
            "silence_ms": 500,
            "min_speech_ms": 250,
            "energy_threshold": 0.01,
            "max_buffer_ms": 30000,
        },
    },
    "postprocess": {
        "enabled": False,
        "provider": "llm",
        "profile": "default",
    },
    "clipboard": {
        "enabled": True,
        "tool": "auto",
    },
    "web": {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8787,
    },
    "logging": {
        "level": "INFO",
        "console": True,
        "file": "./logs/whisperflow.log",
    },
}


def load_config(path: str) -> dict[str, Any]:
    """Load and validate the config file at the provided path."""
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            raw_config = json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file is not valid JSON: {config_path}") from exc

    if not isinstance(raw_config, dict):
        raise ConfigError("Config file must contain a JSON object at the top level.")

    merged = _merge_dicts(DEFAULT_CONFIG, raw_config)
    _validate_config(merged)
    return merged


def apply_overrides(
    config: dict[str, Any], overrides: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge CLI overrides into an existing config dictionary."""
    if overrides is None:
        return copy.deepcopy(config)
    if not isinstance(overrides, dict):
        raise ConfigError("Overrides must be provided as a dictionary.")
    merged = _merge_dicts(config, overrides)
    _validate_config(merged)
    return merged


def _merge_dicts(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _validate_config(config: dict[str, Any]) -> None:
    _validate_str(config, "output_dir")
    _validate_str(config, "model", allowed=ALLOWED_MODELS)
    _validate_str(config, "language")
    _validate_str(config, "task", allowed=ALLOWED_TASKS)
    _validate_str(config, "output_format", allowed=ALLOWED_OUTPUT_FORMATS)
    _validate_bool(config, "batch")

    live_capture = _require_dict(config, "live_capture")
    _validate_bool(live_capture, "enabled")
    _validate_str(live_capture, "raw_transcript_filename")
    _validate_str(live_capture, "final_transcript_filename")
    _validate_str(live_capture, "backend", allowed=ALLOWED_BACKENDS)

    audio = _require_dict(live_capture, "audio")
    _validate_device(audio, "device")
    _validate_int(audio, "sample_rate", min_value=1)
    _validate_int(audio, "channels", min_value=1)
    _validate_int(audio, "chunk_ms", min_value=1)

    vad = _require_dict(live_capture, "vad")
    _validate_bool(vad, "enabled")
    _validate_int(vad, "silence_ms", min_value=1)
    _validate_int(vad, "min_speech_ms", min_value=1)
    _validate_float(vad, "energy_threshold", min_value=0.0)
    _validate_int(vad, "max_buffer_ms", min_value=1)

    postprocess = _require_dict(config, "postprocess")
    _validate_bool(postprocess, "enabled")
    _validate_str(postprocess, "provider")
    _validate_str(postprocess, "profile")

    clipboard = _require_dict(config, "clipboard")
    _validate_bool(clipboard, "enabled")
    _validate_str(clipboard, "tool")

    web_config = _require_dict(config, "web")
    _validate_bool(web_config, "enabled")
    _validate_str(web_config, "host")
    _validate_port(web_config, "port")

    logging_config = _require_dict(config, "logging")
    _validate_str(logging_config, "level", allowed=ALLOWED_LOG_LEVELS)
    _validate_bool(logging_config, "console")
    _validate_optional_str(logging_config, "file")


def _require_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"Config key '{key}' must be an object.")
    return value


def _validate_str(
    parent: dict[str, Any],
    key: str,
    *,
    allowed: set[str] | None = None,
) -> None:
    value = parent.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"Config key '{key}' must be a non-empty string.")
    if allowed is not None and value not in allowed:
        allowed_list = ", ".join(sorted(allowed))
        raise ConfigError(f"Config key '{key}' must be one of: {allowed_list}.")


def _validate_optional_str(parent: dict[str, Any], key: str) -> None:
    value = parent.get(key)
    if value is None:
        return
    if not isinstance(value, str):
        raise ConfigError(f"Config key '{key}' must be a string.")


def _validate_bool(parent: dict[str, Any], key: str) -> None:
    value = parent.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"Config key '{key}' must be a boolean.")


def _validate_int(
    parent: dict[str, Any], key: str, *, min_value: int | None = None
) -> None:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"Config key '{key}' must be an integer.")
    if min_value is not None and value < min_value:
        raise ConfigError(f"Config key '{key}' must be >= {min_value}.")


def _validate_port(parent: dict[str, Any], key: str) -> None:
    _validate_int(parent, key, min_value=1)
    value = parent.get(key)
    if isinstance(value, int) and value > 65535:
        raise ConfigError(f"Config key '{key}' must be <= 65535.")


def _validate_float(
    parent: dict[str, Any], key: str, *, min_value: float | None = None
) -> None:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ConfigError(f"Config key '{key}' must be a number.")
    if min_value is not None and float(value) < min_value:
        raise ConfigError(f"Config key '{key}' must be >= {min_value}.")


def _validate_device(parent: dict[str, Any], key: str) -> None:
    value = parent.get(key)
    if isinstance(value, bool):
        raise ConfigError(f"Config key '{key}' must be a string or integer.")
    if isinstance(value, (str, int)):
        return
    raise ConfigError(f"Config key '{key}' must be a string or integer.")
