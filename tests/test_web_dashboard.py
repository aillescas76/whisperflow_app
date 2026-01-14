"""Tests for the web dashboard server."""

from __future__ import annotations

import json
import threading
import time
import urllib.request

from whisperflow.web_dashboard import LiveDashboard, start_dashboard_server


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=2) as response:
        return response.read()


def test_dashboard_server_serves_stats() -> None:
    dashboard = LiveDashboard(
        {
            "model": "small",
            "language": "en",
            "task": "transcribe",
            "output_format": "txt",
        }
    )
    stop_event = threading.Event()
    server = start_dashboard_server(dashboard, stop_event, "127.0.0.1", 0)

    host, port = server.server_address[:2]
    stats = json.loads(_fetch(f"http://{host}:{port}/stats"))
    html = _fetch(f"http://{host}:{port}/")

    stop_event.set()
    server.server_close()

    assert stats["status"] == "starting"
    assert b"Whisperflow Live Dashboard" in html


def test_dashboard_server_streams_events() -> None:
    dashboard = LiveDashboard(
        {
            "model": "small",
            "language": "en",
            "task": "transcribe",
            "output_format": "txt",
        }
    )
    stop_event = threading.Event()
    server = start_dashboard_server(dashboard, stop_event, "127.0.0.1", 0)

    host, port = server.server_address[:2]
    with urllib.request.urlopen(f"http://{host}:{port}/events", timeout=2) as response:
        first_line = response.readline()
        response.readline()
        time.sleep(0.6)
        heartbeat = response.readline()

    stop_event.set()
    server.server_close()

    assert b"data:" in first_line
    assert b"heartbeat" in heartbeat


def test_dashboard_listener_lifecycle() -> None:
    dashboard = LiveDashboard(
        {
            "model": "small",
            "language": "en",
            "task": "transcribe",
            "output_format": "txt",
        }
    )
    listener = dashboard.register_listener()
    dashboard.mark_error("boom")
    payload = listener.get(timeout=1)
    dashboard.unregister_listener(listener)

    assert payload["last_error"] == "boom"
