"""Custom exceptions for Whisperflow."""

from __future__ import annotations

import builtins
from typing import Tuple


class ConfigError(Exception):
    """Raised when configuration loading or validation fails."""


class UserInputError(Exception):
    """Raised when user input is missing or invalid."""


class WhisperflowRuntimeError(builtins.RuntimeError):
    """Raised when a runtime operation fails."""


_ERROR_PREFIXES: Tuple[Tuple[type[BaseException], str], ...] = (
    (ConfigError, "Config error"),
    (UserInputError, "Input error"),
    (WhisperflowRuntimeError, "Runtime error"),
)


def format_error(exc: BaseException) -> str:
    """Return a user-facing error message with a consistent prefix."""
    message = str(exc).strip() or exc.__class__.__name__
    for exc_type, prefix in _ERROR_PREFIXES:
        if isinstance(exc, exc_type):
            return f"{prefix}: {message}"
    return f"Unexpected error: {message}"


__all__ = [
    "ConfigError",
    "UserInputError",
    "WhisperflowRuntimeError",
    "format_error",
]
