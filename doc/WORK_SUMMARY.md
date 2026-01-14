# Work Summary

## What was built
- Offline-first CLI for file, batch, and live transcription using `faster-whisper-gpu`.
- Config loader/validator with defaults and CLI overrides.
- Live capture daemon with IPC, rolling buffer, VAD gating, and transcript output.
- Clipboard copy on finalize plus a placeholder postprocess hook.

## Key files added or changed
- `whisperflow/cli.py`
- `whisperflow/config.py`
- `whisperflow/transcribe.py`
- `whisperflow/live.py`
- `whisperflow/daemon.py`
- `tests/`

## How to run
- Edit `config/config.json`, then run `python -m whisperflow --help`.
- File transcription: `python -m whisperflow transcribe /path/to/audio.wav --output_dir ./output`
- Live capture: `python -m whisperflow start` then `python -m whisperflow stop`

## Known limitations or follow-ups
- Requires `/usr/local/bin/faster-whisper-gpu` and cached models under `/opt/faster-whisper/models`.
- Live capture depends on `sounddevice`/PortAudio or a CLI backend (`arecord`/`pw-record`).
- Postprocess is a placeholder and needs a local provider configuration if enabled.

## Verification
- Not run (docs-only update).
