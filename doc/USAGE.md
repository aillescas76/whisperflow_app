# Usage

This app is CLI-first with an optional local web dashboard. All commands are run from the project root.

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

Start capture with system output:

```
uv run python -m whisperflow start --include-output
```

Stop capture and finalize:

```
uv run python -m whisperflow stop
```

## Shortcut scripts

These scripts live in the repo root and already use `uv run` (no manual venv activation):

```
scripts/start_capture_es.sh
scripts/start_capture_en.sh
scripts/stop_capture.sh
```

## Keyboard shortcuts

Before assigning shortcuts, check existing bindings so you avoid conflicts.

Ubuntu (GNOME) check:

```
gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings
```

Kubuntu/Tuxedo OS (KDE) check:

```
grep -n "whisperflow" ~/.config/kglobalshortcutsrc
```

Suggested bindings (adjust if already taken):
- Start Spanish capture: `Super+Alt+S`
- Start English capture: `Super+Alt+E`
- Stop capture: `Super+Alt+X`

Ubuntu (GNOME) create shortcuts:
1. Settings -> Keyboard -> View and Customize Shortcuts -> Custom Shortcuts.
2. Click `+`, set a name, and use the full command path:
   - `/home/aic/code/whisperflow_app/scripts/start_capture_es.sh`
   - `/home/aic/code/whisperflow_app/scripts/start_capture_en.sh`
   - `/home/aic/code/whisperflow_app/scripts/stop_capture.sh`
3. Assign the key combos you want.

Kubuntu (KDE) create shortcuts:
1. System Settings -> Shortcuts -> Custom Shortcuts.
2. Edit -> New -> Global Shortcut -> Command/URL.
3. Set the command to the full script path and assign the key combo.

Tuxedo OS (KDE) create shortcuts:
1. System Settings -> Shortcuts -> Custom Shortcuts.
2. Add a Global Shortcut for a Command/URL.
3. Set the command to the full script path and assign the key combo.

Check status:

```
uv run python -m whisperflow status
```

Live capture outputs:
- Raw transcript: `./output/live_raw.txt`
- Final transcript on stop: `./output/transcript.txt`
- Output raw transcript (when enabled): `./output/live_output_raw.txt`
- Output final transcript (when enabled): `./output/transcript_output.txt`
- Per-segment files: `./output/live_segments/`
- Output per-segment files: `./output/live_output_segments/`
- On start, existing transcript files and segment folders are backed up with a timestamp suffix.

## Live dashboard

When `web.enabled` is true, the daemon serves a local dashboard at
`http://127.0.0.1:8787` with chunk timing stats and recent segments. Configure
`web.host` and `web.port` to change the bind address.

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
Output capture settings live under `live_capture.audio.include_output`,
`live_capture.output_vad`, and the `live_capture.output_*` filenames (raw/final transcripts).
On PipeWire, output capture autodetects the default sink node and uses `pw-record`.
If the sink cannot be resolved, output capture exits with an error while input capture continues.

Web dashboard options live under `web`:
- `enabled`: `true` to start the local server
- `host`: bind address (default `127.0.0.1`)
- `port`: bind port (default `8787`)

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
