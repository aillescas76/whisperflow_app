"""Model selection helpers for Whisperflow."""

from __future__ import annotations

from pathlib import Path

MODEL_PREFERENCE = ("large-v3", "medium", "small")
MODEL_CACHE_DIR = Path("/opt/faster-whisper/models")


def select_best_model(config_model: str) -> str:
    """Select the best available cached model, falling back to the config model."""
    for model_name in MODEL_PREFERENCE:
        if (MODEL_CACHE_DIR / model_name).exists():
            return model_name
    return config_model


__all__ = ["select_best_model"]
