"""Tests for logging setup."""

from __future__ import annotations

import logging

from whisperflow.logging_utils import setup_logging


def test_setup_logging_configures_handlers(tmp_path) -> None:
    log_path = tmp_path / "whisperflow.log"
    config = {"logging": {"level": "DEBUG", "console": False, "file": str(log_path)}}

    setup_logging(config)

    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert any(isinstance(handler, logging.FileHandler) for handler in root.handlers)

    logging.getLogger("whisperflow.test").info("hello")
    for handler in root.handlers:
        handler.flush()

    assert log_path.exists()
    assert "hello" in log_path.read_text(encoding="utf-8")


def test_setup_logging_console_handler() -> None:
    config = {"logging": {"level": "INFO", "console": True, "file": ""}}
    setup_logging(config)

    root = logging.getLogger()
    assert any(isinstance(handler, logging.StreamHandler) for handler in root.handlers)


def test_setup_logging_null_handler() -> None:
    config = {"logging": {"level": "INFO", "console": False, "file": ""}}
    setup_logging(config)

    root = logging.getLogger()
    assert any(isinstance(handler, logging.NullHandler) for handler in root.handlers)
