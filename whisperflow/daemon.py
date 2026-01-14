"""Local daemon and IPC for Whisperflow live capture."""

from __future__ import annotations

import argparse
import logging
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence

from whisperflow.clipboard import copy_to_clipboard
from whisperflow.config import load_config
from whisperflow.errors import WhisperflowRuntimeError
from whisperflow.ipc import send_command, serve
from whisperflow.live import run_live_capture
from whisperflow.logging_utils import setup_logging
from whisperflow.output import write_transcript
from whisperflow.web_dashboard import LiveDashboard, start_dashboard_server

RUN_DIR = Path("run")
SOCKET_PATH = RUN_DIR / "whisperflow.sock"
PID_PATH = RUN_DIR / "whisperflow.pid"
STATE_PATH = RUN_DIR / "whisperflow.state.json"
CONFIG_PATH = RUN_DIR / "whisperflow.config.json"
LOG_PATH = RUN_DIR / "whisperflow.log"
logger = logging.getLogger(__name__)


def start_daemon(config: dict[str, Any]) -> None:
    """Start the Whisperflow daemon if it is not already running."""
    live_config = config.get("live_capture", {})
    if not isinstance(live_config, dict) or not live_config.get("enabled", False):
        raise WhisperflowRuntimeError("Live capture is disabled in the config.")

    _ensure_run_dir()
    if _daemon_running():
        pid = _read_pid()
        message = (
            f"Daemon already running (pid {pid})." if pid else "Daemon already running."
        )
        print(message)
        return

    _cleanup_stale_files()
    _write_json(CONFIG_PATH, config)

    with LOG_PATH.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [sys.executable, "-m", "whisperflow.daemon", "--config", str(CONFIG_PATH)],
            stdout=log_handle,
            stderr=log_handle,
            start_new_session=True,
        )

    if not _wait_for_daemon_ready(process.pid):
        raise WhisperflowRuntimeError(f"Daemon failed to start. Check log: {LOG_PATH}")
    print(f"Daemon started (pid {process.pid}).")


def stop_daemon(_config: dict[str, Any]) -> None:
    """Stop the Whisperflow daemon via IPC."""
    if not _daemon_running():
        print("Daemon is not running.")
        return

    response = send_command(SOCKET_PATH, "stop")
    if not response.get("ok", False):
        raise WhisperflowRuntimeError(response.get("error", "Failed to stop daemon."))

    if not _wait_for_daemon_exit(timeout=10.0):
        raise WhisperflowRuntimeError("Daemon did not exit after stop request.")
    print("Daemon stopped.")


def show_status() -> None:
    """Display current daemon status and last known state."""
    state = _read_state()
    running = _daemon_running()

    if not state:
        print("Daemon is not running.")
        return

    status = state.get("status", "unknown")
    pid = state.get("pid", "unknown")
    header = f"Status: {status}"
    if running:
        header += f" (pid {pid})"
    print(header)

    _print_state_line(state, "output_dir", "Output dir")
    _print_state_line(state, "raw_transcript_path", "Raw transcript")
    _print_state_line(state, "final_transcript_path", "Final transcript")
    _print_state_line(state, "backend", "Capture backend")
    _print_state_line(state, "device", "Capture device")
    _print_state_line(state, "sample_rate", "Sample rate")
    _print_state_line(state, "channels", "Channels")
    _print_state_line(state, "model", "Model")
    _print_state_line(state, "language", "Language")
    _print_state_line(state, "task", "Task")
    _print_state_line(state, "output_format", "Output format")
    _print_state_line(state, "web_url", "Web dashboard")
    _print_state_line(state, "web_error", "Web error")
    _print_state_line(state, "started_at", "Started")
    _print_state_line(state, "stopped_at", "Stopped")
    _print_state_line(state, "last_error", "Last error")

    if not running:
        print("Daemon is not running.")


def _run_daemon(config_path: Path) -> None:
    config = load_config(str(config_path))
    setup_logging(config)
    logger.info("Daemon starting.")
    _ensure_run_dir()
    _cleanup_socket()

    stop_event = threading.Event()
    state_lock = threading.Lock()
    state = _build_state(config)

    _write_pid()
    _write_state(state)

    def update_state(**updates: Any) -> None:
        with state_lock:
            state.update(updates)
            _write_state(state)

    dashboard: LiveDashboard | None = None
    web_server: ThreadingHTTPServer | None = None
    web_config = config.get("web", {})
    if isinstance(web_config, dict) and web_config.get("enabled", False):
        dashboard = LiveDashboard(config)
        host = web_config.get("host", "127.0.0.1")
        port = int(web_config.get("port", 8787))
        try:
            web_server = start_dashboard_server(dashboard, stop_event, host, port)
            update_state(web_url=f"http://{host}:{port}")
        except OSError as exc:
            logger.warning("Failed to start dashboard on %s:%s: %s", host, port, exc)
            update_state(web_error=str(exc))
            dashboard = None

    def capture_worker() -> None:
        try:
            update_state(status="running")
            run_live_capture(config, {}, stop_event, dashboard)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Capture worker crashed: %s", exc)
            update_state(status="error", last_error=str(exc))
            stop_event.set()

    capture_thread = threading.Thread(target=capture_worker, name="whisperflow-capture")
    capture_thread.start()

    def handle_request(message: dict[str, Any]) -> dict[str, Any]:
        command = message.get("command")
        if command == "stop":
            update_state(status="stopping")
            logger.info("Stop request received.")
            stop_event.set()
            return {"ok": True, "message": "Stopping daemon."}
        if command == "status":
            return {"ok": True, "state": state}
        return {"ok": False, "error": f"Unknown command: {command}"}

    _install_signal_handlers(stop_event)
    serve(SOCKET_PATH, stop_event, handle_request)

    capture_thread.join()
    if web_server:
        web_server.server_close()
    _finalize_transcript(state, config, update_state)
    update_state(status="stopped", stopped_at=_now_iso())
    logger.info("Daemon stopped.")
    _cleanup_socket()
    _remove_pid()


def _build_state(config: dict[str, Any]) -> dict[str, Any]:
    live = config["live_capture"]
    audio = live["audio"]
    output_dir = Path(config["output_dir"])
    raw_path = output_dir / live["raw_transcript_filename"]
    final_path = output_dir / live["final_transcript_filename"]
    return {
        "status": "starting",
        "pid": os.getpid(),
        "started_at": _now_iso(),
        "stopped_at": None,
        "output_dir": str(output_dir),
        "raw_transcript_path": str(raw_path),
        "final_transcript_path": str(final_path),
        "backend": live["backend"],
        "device": audio["device"],
        "sample_rate": audio["sample_rate"],
        "channels": audio["channels"],
        "model": config["model"],
        "language": config["language"],
        "task": config["task"],
        "output_format": config["output_format"],
        "web_url": None,
        "web_error": None,
        "last_error": None,
    }


def _finalize_transcript(
    state: dict[str, Any], config: dict[str, Any], update_state: Any
) -> None:
    raw_path = Path(state["raw_transcript_path"])
    final_path = Path(state["final_transcript_path"])
    try:
        if raw_path.exists():
            content = raw_path.read_text(encoding="utf-8")
        else:
            content = ""
        write_transcript(content, str(final_path))
        update_state(finalized_at=_now_iso())
        _copy_final_transcript(content, config)
    except OSError as exc:
        update_state(status="error", last_error=f"Failed to finalize transcript: {exc}")


def _copy_final_transcript(text: str, config: dict[str, Any]) -> None:
    clipboard = config.get("clipboard", {})
    if not isinstance(clipboard, dict):
        return
    if not clipboard.get("enabled", False):
        return
    tool = clipboard.get("tool", "auto")
    copy_to_clipboard(text, tool=tool)


def _install_signal_handlers(stop_event: threading.Event) -> None:
    def handler(_signum: int, _frame: Any) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def _ensure_run_dir() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)


def _cleanup_socket() -> None:
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()


def _cleanup_stale_files() -> None:
    if PID_PATH.exists() and not _daemon_running():
        _remove_pid()
    if SOCKET_PATH.exists() and not _daemon_running():
        _cleanup_socket()


def _daemon_running() -> bool:
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_daemon_ready(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if SOCKET_PATH.exists() and _pid_running(pid):
            return True
        time.sleep(0.1)
    return False


def _wait_for_daemon_exit(timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _daemon_running():
            return True
        time.sleep(0.1)
    return False


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_pid() -> int | None:
    try:
        return int(PID_PATH.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def _write_pid() -> None:
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")


def _remove_pid() -> None:
    if PID_PATH.exists():
        PID_PATH.unlink()


def _read_state() -> dict[str, Any]:
    try:
        with STATE_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_state(state: dict[str, Any]) -> None:
    tmp_path = STATE_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    tmp_path.replace(STATE_PATH)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def _print_state_line(state: dict[str, Any], key: str, label: str) -> None:
    value = state.get(key)
    if value is None or value == "":
        return
    print(f"{label}: {value}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Whisperflow daemon process."""
    parser = argparse.ArgumentParser(description="Whisperflow daemon process.")
    parser.add_argument(
        "--config", required=True, help="Path to the daemon config JSON file."
    )
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1

    _run_daemon(config_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["start_daemon", "stop_daemon", "show_status"]
