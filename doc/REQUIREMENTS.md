# Whisperflow-Like App - Provisional Requirements

## Goal
Build a local application that mimics Whisperflow-style audio transcription and translation, using the Faster-Whisper tooling available on this system.

## Available System Capability (from faster_whisper.md)
- CLI wrapper: `/usr/local/bin/faster-whisper-gpu`
- Virtualenv: `/opt/faster-whisper/venv`
- Model cache: `/opt/faster-whisper/models`
- Supports GPU via `dgpu-run` when available; falls back to CPU
- Models: `small`, `medium`, `large-v3`
- Tasks: `transcribe`, `translate`
- Output formats: `txt`, `srt`, `vtt`, `json`
- Output directory support: `--output_dir`

## Functional Requirements
- Accept audio files for transcription.
- Support live mic capture and continuous transcription in a foreground CLI session.
- Provide system-level hotkeys on Kubuntu to start/stop capture by launching CLI commands:
  - Start capture: `Ctrl+Alt+Shift+R` (suggested)
  - Stop capture: `Ctrl+Alt+Shift+S` (suggested)
- Allow selecting model size: `small`, `medium`, `large-v3`.
- Allow setting language (default: auto-detect or `en`).
- Allow task selection: `transcribe` or `translate`.
- Allow selecting output format: `txt`, `srt`, `vtt`, `json`.
- Allow choosing an output directory via a config file.
- Display progress and completion status.
- Support batch processing of a folder of audio files.
- While live capture runs, write live transcription updates to disk as a raw transcript file.
- On stop, write the final transcript to a text file and copy it to the clipboard.
- Optional post-processing/enrichment via an LLM, enabled by CLI param or config value.

## Non-Functional Requirements
- Must run fully offline once models are cached in `/opt/faster-whisper/models`.
- Must work on CPU if GPU or `dgpu-run` is not available.
- Avoid destructive operations on model cache by default.
- Provide clear error messages for missing audio files or unsupported formats.

## Config Schema (Provisional)
Config file: `config/config.json`

Defaults must be provided for all options:
```
{
  "output_dir": "./output",
  "model": "small",
  "language": "auto",
  "task": "transcribe",
  "output_format": "txt",
  "batch": false,
  "live_capture": {
    "enabled": true,
    "raw_transcript_filename": "live_raw.txt",
    "final_transcript_filename": "transcript.txt",
    "audio": {
      "device": "default",
      "sample_rate": 16000,
      "channels": 1,
      "chunk_ms": 1000
    }
  },
  "postprocess": {
    "enabled": false,
    "provider": "llm",
    "profile": "default"
  },
  "clipboard": {
    "enabled": true,
    "tool": "auto"
  }
}
```

## Interface Options (TBD)
- CLI only.
- Foreground CLI session acceptable for hotkey-driven live capture.
- If GUI: include file picker, batch folder selection, and status panel.

## Assumptions
- `faster-whisper-gpu` is installed and available in PATH.
- Supported audio formats are those accepted by Faster-Whisper/ffmpeg.
- Config file lives at `config/config.json` in the project root.

## Open Questions
- Default model choice and language behavior?
- Should outputs be auto-opened or just saved to disk?
- Which clipboard tool should be default on Kubuntu (xclip vs xsel), and how to detect it?

## Example CLI Invocation (baseline)
```
/usr/local/bin/faster-whisper-gpu --model small --language en --task transcribe --output_format txt --output_dir /path/to/output /path/to/audio.wav
```
