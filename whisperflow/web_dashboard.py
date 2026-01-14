"""Lightweight web dashboard for live transcription stats."""

from __future__ import annotations

import json
import queue
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Deque
from urllib.parse import urlparse


@dataclass(frozen=True)
class SegmentMetrics:
    index: int
    audio_ms: float
    transcribe_ms: float
    realtime_factor: float
    success: bool
    transcript_chars: int
    started_at: str
    finished_at: str
    preview: str


class LiveDashboard:
    """Collect and broadcast live transcription stats."""

    def __init__(self, config: dict[str, Any], *, history_limit: int = 20) -> None:
        self._lock = threading.Lock()
        self._queues: list[queue.Queue[dict[str, Any]]] = []
        self._segments: Deque[SegmentMetrics] = deque(maxlen=history_limit)
        self._status = "starting"
        self._started_at = _now_iso()
        self._current_segment: dict[str, Any] | None = None
        self._total_audio_ms = 0.0
        self._total_transcribe_ms = 0.0
        self._segments_total = 0
        self._segments_failed = 0
        self._last_error: str | None = None
        self._model = config.get("model", "unknown")
        self._language = config.get("language", "auto")
        self._task = config.get("task", "transcribe")
        self._output_format = config.get("output_format", "txt")

    def set_status(self, status: str) -> None:
        with self._lock:
            self._status = status
        self.publish_snapshot()

    def mark_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
        self.publish_snapshot()

    def segment_started(self, index: int, audio_ms: float) -> None:
        started_at = _now_iso()
        with self._lock:
            self._status = "transcribing"
            self._current_segment = {
                "index": index,
                "audio_ms": round(audio_ms, 2),
                "started_at": started_at,
            }
        self.publish_snapshot()

    def segment_finished(
        self,
        index: int,
        audio_ms: float,
        transcribe_ms: float,
        success: bool,
        transcript_preview: str,
    ) -> None:
        finished_at = _now_iso()
        transcript_chars = len(transcript_preview)
        realtime_factor = _safe_divide(transcribe_ms, audio_ms)
        metrics = SegmentMetrics(
            index=index,
            audio_ms=round(audio_ms, 2),
            transcribe_ms=round(transcribe_ms, 2),
            realtime_factor=round(realtime_factor, 3),
            success=success,
            transcript_chars=transcript_chars,
            started_at=self._current_segment.get("started_at", finished_at)
            if self._current_segment
            else finished_at,
            finished_at=finished_at,
            preview=transcript_preview,
        )

        with self._lock:
            self._segments_total += 1
            self._total_audio_ms += audio_ms
            self._total_transcribe_ms += transcribe_ms
            if not success:
                self._segments_failed += 1
            self._segments.appendleft(metrics)
            self._current_segment = None
            self._status = "listening"

        self.publish_snapshot()

    def register_listener(self) -> queue.Queue[dict[str, Any]]:
        listener: queue.Queue[dict[str, Any]] = queue.Queue()
        with self._lock:
            self._queues.append(listener)
        return listener

    def unregister_listener(self, listener: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            if listener in self._queues:
                self._queues.remove(listener)

    def publish_snapshot(self) -> None:
        snapshot = self.snapshot()
        self._broadcast(snapshot)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total_audio_s = self._total_audio_ms / 1000.0
            total_transcribe_s = self._total_transcribe_ms / 1000.0
            average_audio_ms = _safe_divide(self._total_audio_ms, self._segments_total)
            average_transcribe_ms = _safe_divide(
                self._total_transcribe_ms, self._segments_total
            )
            realtime_factor = _safe_divide(total_transcribe_s, total_audio_s)
            return {
                "status": self._status,
                "started_at": self._started_at,
                "model": self._model,
                "language": self._language,
                "task": self._task,
                "output_format": self._output_format,
                "segments_total": self._segments_total,
                "segments_failed": self._segments_failed,
                "total_audio_seconds": round(total_audio_s, 2),
                "total_transcribe_seconds": round(total_transcribe_s, 2),
                "average_audio_ms": round(average_audio_ms, 2),
                "average_transcribe_ms": round(average_transcribe_ms, 2),
                "realtime_factor": round(realtime_factor, 3),
                "current_segment": self._current_segment,
                "last_error": self._last_error,
                "recent_segments": [
                    segment.__dict__ for segment in list(self._segments)
                ],
            }

    def _broadcast(self, payload: dict[str, Any]) -> None:
        with self._lock:
            listeners = list(self._queues)
        for listener in listeners:
            listener.put(payload)


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Whisperflow Live Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #0b0f19;
      --panel: #111827;
      --panel-light: #1f2937;
      --accent: #38bdf8;
      --accent-2: #22d3ee;
      --text: #f9fafb;
      --muted: #9ca3af;
      --border: #273142;
      --success: #34d399;
      --danger: #f87171;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: "Inter", "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #1f2937 0%, #0b0f19 60%);
      color: var(--text);
    }

    header {
      padding: 28px 28px 12px;
    }

    h1 {
      margin: 0;
      font-size: 28px;
      letter-spacing: 0.5px;
    }

    .subtitle {
      margin-top: 6px;
      color: var(--muted);
      font-size: 14px;
    }

    main {
      padding: 16px 28px 36px;
      display: grid;
      gap: 18px;
    }

    .grid {
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }

    .panel {
      background: linear-gradient(180deg, rgba(31,41,55,0.95), rgba(17,24,39,0.95));
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.35);
    }

    .card {
      background: var(--panel-light);
      border: 1px solid rgba(255,255,255,0.05);
      border-radius: 12px;
      padding: 14px;
    }

    .label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }

    .value {
      font-size: 20px;
      font-weight: 600;
      margin-top: 6px;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      background: rgba(56, 189, 248, 0.2);
      color: var(--accent);
    }

    .pill.success { color: var(--success); background: rgba(52, 211, 153, 0.2); }
    .pill.danger { color: var(--danger); background: rgba(248, 113, 113, 0.2); }

    .section-title {
      margin: 0 0 12px 0;
      font-size: 16px;
      color: var(--text);
    }

    .row {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }

    .list {
      list-style: none;
      margin: 0;
      padding: 0;
    }

    .list li {
      padding: 8px 0;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      color: var(--muted);
    }

    .list li:last-child {
      border-bottom: none;
    }

    .transcript {
      background: #0f172a;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px;
      padding: 16px;
      font-family: "JetBrains Mono", "Fira Code", monospace;
      font-size: 14px;
      line-height: 1.6;
      min-height: 160px;
      color: var(--text);
      white-space: pre-wrap;
    }

    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }

    .meta-item {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .muted { color: var(--muted); }
    code { background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 6px; }
  </style>
</head>
<body>
  <header>
    <h1>Whisperflow Live Dashboard</h1>
    <div class="subtitle">Live stream of capture + transcription stats.</div>
  </header>

  <main>
    <section class="panel">
      <div class="meta">
        <div class="pill" id="status_badge">Starting</div>
        <div class="meta-item">Started: <span id="started_at">-</span></div>
      </div>
      <div class="grid" style="margin-top: 14px;">
        <div class="card">
          <div class="label">Status</div>
          <div class="value" id="status">starting</div>
        </div>
        <div class="card">
          <div class="label">Model</div>
          <div class="value" id="model">-</div>
        </div>
        <div class="card">
          <div class="label">Task</div>
          <div class="value" id="task">-</div>
        </div>
        <div class="card">
          <div class="label">Language</div>
          <div class="value" id="language">-</div>
        </div>
        <div class="card">
          <div class="label">Output Format</div>
          <div class="value" id="output_format">-</div>
        </div>
      </div>
    </section>

    <section class="panel">
      <h2 class="section-title">Totals</h2>
      <div class="row">
        <div class="card">
          <div class="label">Segments</div>
          <div class="value" id="segments_total">0</div>
        </div>
        <div class="card">
          <div class="label">Failures</div>
          <div class="value" id="segments_failed">0</div>
        </div>
        <div class="card">
          <div class="label">Total Audio (s)</div>
          <div class="value" id="total_audio">0</div>
        </div>
        <div class="card">
          <div class="label">Total Transcribe (s)</div>
          <div class="value" id="total_transcribe">0</div>
        </div>
        <div class="card">
          <div class="label">Realtime Factor</div>
          <div class="value" id="realtime_factor">0</div>
        </div>
      </div>
    </section>

    <section class="panel">
      <h2 class="section-title">Live Transcript</h2>
      <div class="transcript" id="live_transcript">Waiting for transcript...</div>
    </section>

    <section class="panel">
      <h2 class="section-title">Current Segment</h2>
      <div class="row">
        <div class="card">
          <div class="label">Index</div>
          <div class="value" id="current_index">-</div>
        </div>
        <div class="card">
          <div class="label">Audio (ms)</div>
          <div class="value" id="current_audio">-</div>
        </div>
        <div class="card">
          <div class="label">Started</div>
          <div class="value" id="current_started">-</div>
        </div>
      </div>
    </section>

    <section class="panel">
      <h2 class="section-title">Last Segment</h2>
      <div class="row">
        <div class="card">
          <div class="label">Index</div>
          <div class="value" id="last_index">-</div>
        </div>
        <div class="card">
          <div class="label">Audio (ms)</div>
          <div class="value" id="last_audio">-</div>
        </div>
        <div class="card">
          <div class="label">Transcribe (ms)</div>
          <div class="value" id="last_transcribe">-</div>
        </div>
        <div class="card">
          <div class="label">Realtime Factor</div>
          <div class="value" id="last_rtf">-</div>
        </div>
        <div class="card">
          <div class="label">Status</div>
          <div class="value" id="last_status">-</div>
        </div>
      </div>
      <div style="margin-top: 12px;" class="muted">Preview</div>
      <div style="margin-top: 6px;" class="transcript" id="last_preview">-</div>
    </section>

    <section class="panel">
      <h2 class="section-title">Recent Segments</h2>
      <ul class="list" id="recent_segments"></ul>
    </section>

    <section class="panel">
      <h2 class="section-title">Last Error</h2>
      <div class="muted" id="last_error">-</div>
    </section>
  </main>

  <script>
    const source = new EventSource("/events");
    const statusBadge = document.getElementById("status_badge");

    function setText(id, value) {
      const node = document.getElementById(id);
      if (node) {
        node.textContent = value ?? "-";
      }
    }

    function setStatusBadge(status) {
      if (!statusBadge) {
        return;
      }
      const normalized = String(status || "unknown").toLowerCase();
      statusBadge.textContent = normalized;
      statusBadge.classList.remove("success", "danger");
      if (normalized === "listening" || normalized === "running" || normalized === "transcribing") {
        statusBadge.classList.add("success");
      }
      if (normalized === "error" || normalized === "stopped") {
        statusBadge.classList.add("danger");
      }
    }

    source.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setText("status", data.status);
      setText("model", data.model);
      setText("task", data.task);
      setText("language", data.language);
      setText("output_format", data.output_format);
      setText("segments_total", data.segments_total);
      setText("segments_failed", data.segments_failed);
      setText("total_audio", data.total_audio_seconds);
      setText("total_transcribe", data.total_transcribe_seconds);
      setText("realtime_factor", data.realtime_factor);
      setText("last_error", data.last_error || "-");
      setText("started_at", data.started_at);
      setStatusBadge(data.status);

      const current = data.current_segment || {};
      setText("current_index", current.index);
      setText("current_audio", current.audio_ms);
      setText("current_started", current.started_at);

      const last = (data.recent_segments || [])[0] || {};
      setText("last_index", last.index);
      setText("last_audio", last.audio_ms);
      setText("last_transcribe", last.transcribe_ms);
      setText("last_rtf", last.realtime_factor);
      setText("last_status", last.success ? "ok" : "failed");
      setText("last_preview", last.preview || "-");

      const list = document.getElementById("recent_segments");
      if (list) {
        list.innerHTML = "";
        (data.recent_segments || []).forEach((segment) => {
          const li = document.createElement("li");
          li.textContent = `#${segment.index} · audio ${segment.audio_ms}ms · transcribe ${segment.transcribe_ms}ms · rtf ${segment.realtime_factor} · ${segment.success ? "ok" : "fail"}`;
          list.appendChild(li);
        });
      }

      const live = document.getElementById("live_transcript");
      if (live) {
        const transcript = (data.recent_segments || [])
          .slice()
          .reverse()
          .map((segment) => segment.preview)
          .filter(Boolean)
          .join(" ");
        live.textContent = transcript || "Waiting for transcript...";
      }
    };
  </script>
</body>
</html>
"""


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Serve the dashboard HTML and SSE stats stream."""

    def __init__(
        self,
        *args: Any,
        dashboard: LiveDashboard,
        stop_event: threading.Event,
        **kwargs: Any,
    ) -> None:
        self._dashboard = dashboard
        self._stop_event = stop_event
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/":
            self._handle_index()
            return
        if route == "/events":
            self._handle_events()
            return
        if route == "/stats":
            self._handle_stats()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_index(self) -> None:
        payload = DASHBOARD_HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_stats(self) -> None:
        payload = json.dumps(self._dashboard.snapshot()).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_events(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        listener = self._dashboard.register_listener()
        try:
            self._send_event(self._dashboard.snapshot())
            while not self._stop_event.is_set():
                try:
                    payload = listener.get(timeout=0.5)
                except queue.Empty:
                    self._send_comment("heartbeat")
                    continue
                self._send_event(payload)
        except (ConnectionResetError, BrokenPipeError):
            return
        finally:
            self._dashboard.unregister_listener(listener)

    def _send_event(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload)
        message = f"data: {data}\n\n".encode("utf-8")
        self.wfile.write(message)
        self.wfile.flush()

    def _send_comment(self, comment: str) -> None:
        message = f": {comment}\n\n".encode("utf-8")
        self.wfile.write(message)
        self.wfile.flush()


def start_dashboard_server(
    dashboard: LiveDashboard,
    stop_event: threading.Event,
    host: str,
    port: int,
) -> ThreadingHTTPServer:
    """Start the dashboard web server in a background thread."""

    def handler_factory(*args: Any, **kwargs: Any) -> DashboardRequestHandler:
        return DashboardRequestHandler(
            *args, dashboard=dashboard, stop_event=stop_event, **kwargs
        )

    server = ThreadingHTTPServer((host, port), handler_factory)

    thread = threading.Thread(
        target=server.serve_forever, name="whisperflow-dashboard", daemon=True
    )
    thread.start()

    def shutdown_server() -> None:
        stop_event.wait()
        server.shutdown()

    stopper = threading.Thread(
        target=shutdown_server, name="whisperflow-dashboard-stop", daemon=True
    )
    stopper.start()

    return server


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["LiveDashboard", "start_dashboard_server"]
