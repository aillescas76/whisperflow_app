"""Logging setup for Whisperflow."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


def setup_logging(config: dict[str, Any]) -> None:
    """Configure root logging based on the provided config."""
    settings = config.get("logging", {})
    level_name = str(settings.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    handlers: list[logging.Handler] = []
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    if settings.get("console", True):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    file_path = str(settings.get("file", "")).strip()
    if file_path:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    for handler in handlers:
        root.addHandler(handler)

    if not handlers:
        root.addHandler(logging.NullHandler())


__all__ = ["setup_logging"]
