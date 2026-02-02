"""Simple HTTP server for browsing transcript archives."""

from __future__ import annotations

import argparse
import threading
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from whisperflow.config import load_config
from whisperflow.errors import WhisperflowRuntimeError, format_error

DEFAULT_CONFIG_PATH = Path("config") / "config.json"


class ArchiveRequestHandler(SimpleHTTPRequestHandler):
    """Serve files from the archive root with directory listings."""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def start_archive_server(
    archive_root: Path,
    stop_event: threading.Event,
    host: str,
    port: int,
) -> ThreadingHTTPServer:
    """Start the archive browser server in a background thread."""
    archive_root.mkdir(parents=True, exist_ok=True)

    def handler_factory(*args: Any, **kwargs: Any) -> ArchiveRequestHandler:
        return ArchiveRequestHandler(*args, directory=str(archive_root), **kwargs)

    server = ThreadingHTTPServer((host, port), handler_factory)

    thread = threading.Thread(
        target=server.serve_forever, name="whisperflow-archive", daemon=True
    )
    thread.start()

    def shutdown_server() -> None:
        stop_event.wait()
        server.shutdown()

    stopper = threading.Thread(
        target=shutdown_server, name="whisperflow-archive-stop", daemon=True
    )
    stopper.start()

    return server


def _archive_root(config: dict[str, Any]) -> Path:
    archive_config = config.get("archive", {})
    dir_name = "archives"
    if isinstance(archive_config, dict):
        dir_name = archive_config.get("dir_name", "archives")
    return Path(config["output_dir"]) / dir_name


def main(argv: list[str] | None = None) -> int:
    """Run the archive browser server."""
    parser = argparse.ArgumentParser(
        description="Whisperflow transcript archive browser."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config file (default: config/config.json).",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        archive_config = config.get("archive", {})
        if not isinstance(archive_config, dict) or not archive_config.get(
            "enabled", False
        ):
            raise WhisperflowRuntimeError("Archive browsing is disabled in the config.")

        archive_web = archive_config.get("web", {})
        if not isinstance(archive_web, dict) or not archive_web.get(
            "enabled", False
        ):
            raise WhisperflowRuntimeError("Archive web server is disabled in the config.")

        host = archive_web.get("host", "127.0.0.1")
        port = int(archive_web.get("port", 8788))
        archive_root = _archive_root(config)

        stop_event = threading.Event()
        server = start_archive_server(archive_root, stop_event, host, port)
        print(f"Archive browser running at http://{host}:{port} (root: {archive_root})")
        try:
            stop_event.wait()
        except KeyboardInterrupt:
            stop_event.set()
        server.shutdown()
        server.server_close()
        return 0
    except Exception as exc:  # noqa: BLE001
        print(format_error(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["start_archive_server", "main"]
