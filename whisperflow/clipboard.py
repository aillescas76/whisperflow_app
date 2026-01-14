"""Clipboard integration for Whisperflow."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys

TOOL_ORDER: tuple[str, ...] = ("xclip", "xsel", "wl-copy")
logger = logging.getLogger(__name__)


def copy_to_clipboard(text: str, tool: str = "auto") -> bool:
    """Copy text to the clipboard if a tool is available."""
    selected_tool = _select_tool(tool)
    if not selected_tool:
        _warn("Clipboard tool not available; skipping copy.")
        return False

    command = _build_command(selected_tool)
    try:
        result = subprocess.run(
            command,
            input=text,
            text=True,
            capture_output=True,
            check=False,
            timeout=2.0,
        )
    except subprocess.TimeoutExpired:
        _warn(f"Clipboard copy timed out using {selected_tool}.")
        return False
    if result.returncode != 0:
        details = result.stderr.strip() or "unknown error"
        _warn(f"Clipboard copy failed with {selected_tool}: {details}")
        return False
    return True


def _select_tool(preferred: str) -> str | None:
    if preferred == "auto":
        for tool in TOOL_ORDER:
            if shutil.which(tool):
                return tool
        return None
    if preferred in TOOL_ORDER and shutil.which(preferred):
        return preferred
    return None


def _build_command(tool: str) -> list[str]:
    if tool == "xclip":
        return [tool, "-selection", "clipboard"]
    if tool == "xsel":
        return [tool, "--clipboard", "--input"]
    if tool == "wl-copy":
        return [tool]
    return [tool]


def _warn(message: str) -> None:
    logger.warning(message)
    print(message, file=sys.stderr)


__all__ = ["copy_to_clipboard"]
