# Usage

This app is CLI-only. All commands are run from the project root.

## Help

```
uv run python -m whisperflow --help
```

## Quick example

```
uv run python -m whisperflow transcribe /path/to/audio.wav \
  --model small \
  --language en \
  --task transcribe \
  --output_format srt \
  --output_dir ./output
```

## Live capture (with daemon)

Start capture:

```
uv run python -m whisperflow start
```

Stop capture and finalize:

```
uv run python -m whisperflow stop
```

Check status:

```
uv run python -m whisperflow status
```

Live capture outputs:
- Raw transcript: `./output/live_raw.txt`
- Final transcript on stop: `./output/transcript.txt`
- Per-segment files: `./output/live_segments/`

## File-based transcription

```
uv run python -m whisperflow transcribe /path/to/audio.wav \
  --model small \
  --language en \
  --task transcribe \
  --output_format txt \
  --output_dir ./output
```

Example output file: `./output/audio.txt`

## Batch transcription

```
uv run python -m whisperflow batch /path/to/folder \
  --model medium \
  --language auto \
  --task translate \
  --output_format srt \
  --output_dir ./output
```

Example output file: `./output/audio.srt`

## Common options
- `--model`: `small`, `medium`, `large-v3`
- `--language`: `auto` or a language code like `en`
- `--task`: `transcribe` or `translate`
- `--output_format`: `txt`, `srt`, `vtt`, `json`
- `--output_dir`: directory for outputs
- `--config`: use a non-default config path (can appear before or after a command)

Supported audio extensions: `.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`, `.opus`,
`.aac`, `.wma`, `.webm`, `.mp4`

## Config

Defaults live in `config/config.json`. CLI flags override config values.
Live capture tuning lives under `live_capture.audio` and `live_capture.vad`.

Logging options live under `logging`:
- `level`: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- `console`: `true` to emit logs to stdout/stderr
- `file`: path to a log file (empty disables file logging)

Example config override:

```
uv run python -m whisperflow start --config ./config/config.json --model medium --output_dir ./output
```

## Tests

```
uv run pytest
```
