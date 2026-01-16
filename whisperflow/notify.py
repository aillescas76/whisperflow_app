"""Desktop notification helper."""

from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


def send_notification(title: str, message: str, *, icon: str | None = None) -> None:
    """Send a desktop notification using notify-send if available."""
    notifier = shutil.which("notify-send")
    if notifier is None:
        logger.warning("notify-send is not available; skipping notification.")
        return
    command = [notifier, title, message]
    if icon:
        command.extend(["--icon", icon])
    subprocess.run(command, check=False)


__all__ = ["send_notification"]
