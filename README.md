# Whisperflow-Like CLI App

Local, offline-first transcription and translation using Faster-Whisper.

Docs:
- Requirements: `doc/REQUIREMENTS.md`
- Architecture: `doc/ARCHITECTURE.md`
- Tasks: `doc/TASKS.md`
- Usage: `doc/USAGE.md`
- Capture notes: `doc/linux_audio_capture_python.md`

Quick start:
- Edit config: `config/config.json`
- Run help: `uv run python -m whisperflow --help`

Notes:
- Uses `/usr/local/bin/faster-whisper-gpu` as the backend.
- Models must be cached under `/opt/faster-whisper/models`.
- Logging is configured via `logging.level`, `logging.console`, and `logging.file`
  in `config/config.json`.
- Live dashboard is available at `http://127.0.0.1:8787` when `web.enabled` is true.

Install:
- Python 3.10+ is required.
- Live capture defaults to `sounddevice` with PortAudio.
  - System deps: `sudo apt install libportaudio2 portaudio19-dev`
  - Python deps (installs into `.venv`): `uv pip install sounddevice numpy`
- If you do not want `sounddevice`, install `arecord` or `pw-record` and set
  `live_capture.backend` to `arecord` or `pw-record`.
- System tray indicator on KDE (AppIndicator):
  - System deps: `sudo apt install libayatana-appindicator3-1 gir1.2-ayatanaappindicator3-0 libgtk-3-0 libnotify-bin`
  - Python deps: `uv pip install .[tray]`

Run:
- Show CLI help: `uv run python -m whisperflow --help`
- Transcribe a file: `uv run python -m whisperflow transcribe /path/to/audio.wav --output_dir ./output`
- Start live capture: `uv run python -m whisperflow start`
- Stop live capture: `uv run python -m whisperflow stop`

Shortcut scripts (repo root):
- Spanish capture: `scripts/start_capture_es.sh`
- English capture: `scripts/start_capture_en.sh`
- Stop capture: `scripts/stop_capture.sh`

Keyboard shortcut setup (Ubuntu/Kubuntu/Tuxedo OS):
- See `doc/USAGE.md` for suggested keybindings and step-by-step setup.

Usage example:
```bash
uv run python -m whisperflow transcribe /path/to/audio.wav \
  --model small \
  --language en \
  --task transcribe \
  --output_format srt \
  --output_dir ./output
```

Troubleshooting:
- Missing backend: install `sounddevice` or a CLI backend (`arecord`/`pw-record`),
  or set `live_capture.backend` to a tool that exists.
- "PortAudio library not found": install PortAudio packages (see
  `doc/linux_audio_capture_python.md`).
- Slow or choppy capture: tune `live_capture.audio.chunk_ms` and VAD settings in
  `config/config.json` (see `doc/linux_audio_capture_python.md`).
- Transcription failures: confirm `/usr/local/bin/faster-whisper-gpu` is
  executable and models exist under `/opt/faster-whisper/models`.
