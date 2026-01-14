"""IPC helpers for the Whisperflow daemon."""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from typing import Any, Callable

from whisperflow.errors import WhisperflowRuntimeError

IPCMessage = dict[str, Any]
IPCHandler = Callable[[IPCMessage], IPCMessage]


def send_command(socket_path: Path, command: str, payload: IPCMessage | None = None) -> IPCMessage:
    """Send a command to the daemon over a Unix socket."""
    if not socket_path.exists():
        raise WhisperflowRuntimeError(f"Daemon socket not found at {socket_path}.")

    message = {"command": command, "payload": payload or {}}
    encoded = json.dumps(message).encode("utf-8")

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2.0)
            client.connect(str(socket_path))
            client.sendall(encoded)
            client.shutdown(socket.SHUT_WR)
            response = _recv_all(client)
    except (OSError, json.JSONDecodeError) as exc:
        raise WhisperflowRuntimeError(f"Failed to communicate with daemon at {socket_path}.") from exc

    try:
        decoded = json.loads(response.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise WhisperflowRuntimeError("Daemon returned invalid response data.") from exc
    if not isinstance(decoded, dict):
        raise WhisperflowRuntimeError("Daemon returned an unexpected response format.")
    return decoded


def serve(socket_path: Path, stop_event: threading.Event, handler: IPCHandler) -> None:
    """Serve incoming IPC requests until the stop event is set."""
    if socket_path.exists():
        socket_path.unlink()

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path))
        server.listen(5)
        server.settimeout(0.5)
        while not stop_event.is_set():
            try:
                connection, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                continue
            with connection:
                response = _handle_connection(connection, handler)
                try:
                    connection.sendall(response)
                except OSError:
                    continue


def _handle_connection(connection: socket.socket, handler: IPCHandler) -> bytes:
    data = _recv_all(connection)
    try:
        request = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError:
        return json.dumps({"ok": False, "error": "Invalid request payload."}).encode("utf-8")
    if not isinstance(request, dict):
        return json.dumps({"ok": False, "error": "Invalid request format."}).encode("utf-8")

    try:
        response = handler(request)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": f"Handler error: {exc}"}).encode("utf-8")
    if not isinstance(response, dict):
        return json.dumps({"ok": False, "error": "Handler returned invalid response."}).encode("utf-8")
    return json.dumps(response).encode("utf-8")


def _recv_all(connection: socket.socket) -> bytes:
    chunks: list[bytes] = []
    while True:
        data = connection.recv(4096)
        if not data:
            break
        chunks.append(data)
    return b"".join(chunks)


__all__ = ["send_command", "serve"]
