"""System tray indicator for live capture."""

from __future__ import annotations

import os
import logging
import threading
import tempfile
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


def start_tray_indicator(
    stop_event: threading.Event, *, tooltip: str, icon_name: str
) -> threading.Thread | None:
    """Start a best-effort system tray indicator for the recording state."""
    icon_value, icon_is_path = resolve_tray_icon(icon_name)
    runner = _load_tray_runner()
    if runner is None:
        logger.warning(
            "Tray indicator requested but no supported tray backend is available."
        )
        return None
    thread = threading.Thread(
        target=runner,
        args=(stop_event, tooltip, icon_value, icon_is_path),
        name="whisperflow-tray",
        daemon=True,
    )
    thread.start()
    return thread


def resolve_tray_icon(icon_name: str) -> tuple[str, bool]:
    """Resolve a tray icon name or custom file path."""
    if icon_name == "custom":
        return _ensure_custom_icon(), True
    if os.path.isabs(icon_name) and Path(icon_name).exists():
        return icon_name, True
    return icon_name, False


def _ensure_custom_icon() -> str:
    icon_path = Path(tempfile.gettempdir()) / "whisperflow-recording.svg"
    if icon_path.exists():
        return str(icon_path)
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'>"
        "<circle cx='32' cy='32' r='20' fill='#dc2626'/>"
        "</svg>"
    )
    icon_path.write_text(svg, encoding="utf-8")
    return str(icon_path)


def _load_tray_runner() -> Callable[[threading.Event, str, str, bool], None] | None:
    runner = _load_appindicator_runner()
    if runner is not None:
        return runner
    runner = _load_gtk_runner()
    if runner is not None:
        return runner
    return _load_pystray_runner()


def _load_appindicator_runner() -> Callable[[threading.Event, str, str, bool], None] | None:
    try:
        import gi  # type: ignore

        try:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as AppIndicator3  # type: ignore
        except (ValueError, ImportError):
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import AppIndicator3  # type: ignore

        gi.require_version("Gtk", "3.0")
        from gi.repository import GLib, Gtk  # type: ignore
    except (ImportError, ValueError) as exc:
        logger.debug("AppIndicator tray backend unavailable: %s", exc)
        return None

    def run(
        stop_event: threading.Event, tooltip: str, icon_value: str, icon_is_path: bool
    ) -> None:
        try:
            indicator = AppIndicator3.Indicator.new(
                "whisperflow",
                icon_value,
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            if hasattr(indicator, "set_title"):
                indicator.set_title(tooltip)
            if hasattr(indicator, "set_icon_full"):
                indicator.set_icon_full(icon_value, tooltip)
            else:
                indicator.set_icon(icon_value)

            menu = Gtk.Menu()
            item = Gtk.MenuItem(label="Recording...")
            item.set_sensitive(False)
            menu.append(item)
            menu.show_all()
            indicator.set_menu(menu)

            loop = GLib.MainLoop()

            def check_stop() -> bool:
                if stop_event.is_set():
                    loop.quit()
                    return False
                return True

            GLib.timeout_add(500, check_stop)
            loop.run()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tray indicator failed to start: %s", exc)

    return run


def _load_gtk_runner() -> Callable[[threading.Event, str, str, bool], None] | None:
    try:
        import gi  # type: ignore

        gi.require_version("Gtk", "3.0")
        from gi.repository import GLib, Gtk  # type: ignore
    except (ImportError, ValueError) as exc:
        logger.debug("Gtk tray backend unavailable: %s", exc)
        return None

    def run(
        stop_event: threading.Event, tooltip: str, icon_value: str, icon_is_path: bool
    ) -> None:
        try:
            if icon_is_path:
                icon = Gtk.StatusIcon.new_from_file(icon_value)
            else:
                icon = Gtk.StatusIcon.new_from_icon_name(icon_value)
            icon.set_tooltip_text(tooltip)
            icon.set_visible(True)

            loop = GLib.MainLoop()

            def check_stop() -> bool:
                if stop_event.is_set():
                    icon.set_visible(False)
                    loop.quit()
                    return False
                return True

            GLib.timeout_add(500, check_stop)
            loop.run()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tray indicator failed to start: %s", exc)

    return run


def _load_pystray_runner() -> Callable[[threading.Event, str, str, bool], None] | None:
    try:
        import pystray  # type: ignore
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError as exc:
        logger.debug("pystray backend unavailable: %s", exc)
        return None

    def _build_icon() -> Image.Image:
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((12, 12, size - 12, size - 12), fill=(220, 38, 38, 255))
        return image

    def run(
        stop_event: threading.Event, tooltip: str, icon_value: str, icon_is_path: bool
    ) -> None:
        icon = pystray.Icon("whisperflow", _build_icon(), tooltip)

        def wait_for_stop() -> None:
            stop_event.wait()
            icon.stop()

        threading.Thread(target=wait_for_stop, daemon=True).start()
        icon.run()

    return run


__all__ = ["start_tray_indicator"]
