# Architecture

## Overview
System architecture for a CLI-only Whisperflow-like transcription app that supports
file-based and live mic capture with system hotkeys on Kubuntu.

## Goals
- Offline-first transcription using Faster-Whisper.
- Foreground CLI with hotkey-controlled live capture.
- Final transcript saved to file and copied to clipboard.
- Optional post-processing enrichment via LLMs.

## Components
- CLI entrypoint
- Config loader (reads `config/config.json`)
- Audio capture pipeline (streaming mic)
- Live transcription loop
- Post-processing/enrichment (optional)
- Output writer (raw + final transcript files)
- Clipboard writer (auto-detect tool)
- Hotkey integration (system shortcut commands)

## Data Flow
1) System shortcut invokes CLI "start" command.
2) CLI loads config defaults, applies CLI overrides.
3) Audio capture streams chunks to transcription loop.
4) Live transcription appends to raw transcript file.
5) System shortcut invokes CLI "stop" command.
6) CLI finalizes transcript, optionally enriches via LLM.
7) Final transcript saved to file and copied to clipboard.

## Recommended Option: CLI + Local Daemon
Use a lightweight local daemon to own capture/transcription state, while
foreground CLI commands act as control clients.

### Roles
- `whisperflow start`: launches/attaches to the daemon, begins capture.
- `whisperflow stop`: tells the daemon to stop capture and finalize.
- `whisperflow status`: reports current state and output paths.

### IPC and State
- IPC via Unix socket (e.g., `./run/whisperflow.sock`).
- PID/state files in `./run/` for recovery and stale-daemon detection.
- Raw transcript file path and final transcript path are part of daemon state.

### Lifecycle
1) Start command spawns daemon if not running.
2) Daemon loads config defaults, applies CLI overrides.
3) Daemon starts audio capture and live transcription loop.
4) Live transcript is appended to raw file during capture.
5) Stop command requests finalize; daemon stops capture.
6) Daemon runs optional LLM enrichment and writes final transcript.
7) Daemon copies final transcript to clipboard and exits (or idles).

### Benefits
- Reliable start/stop with system hotkeys that launch CLI commands.
- Clean separation of capture state from CLI invocation.
- Easier recovery if a CLI command is interrupted.

## Decisions
- Hotkeys are system-level shortcuts that launch CLI commands, not app-captured hooks.
- Live transcription writes to disk during capture.
- Config file location is `config/config.json`.
- Clipboard tool is auto-detected at runtime (Kubuntu defaults).

## Open Questions
- Default model and language behavior for CLI when config is missing.
- Clipboard tool detection order (xclip vs xsel vs wl-copy) and fallback behavior.
