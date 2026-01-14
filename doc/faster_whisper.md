---
title: Faster-Whisper Usage
---

# Faster-Whisper Usage

This guide documents the Faster-Whisper installation from `playbooks/faster_whisper_gpu.yml`.

## Install

```
ansible-playbook playbooks/faster_whisper_gpu.yml --ask-become-pass
```

## CLI wrapper

The playbook installs:
- Virtualenv: `/opt/faster-whisper/venv`
- Model cache: `/opt/faster-whisper/models`
- Wrapper: `/usr/local/bin/faster-whisper-gpu`

The wrapper uses `dgpu-run` when available and falls back to CPU if not.

## Basic transcription

```
faster-whisper-gpu --model small /path/to/audio.wav
```

## Common options

- `--model small|medium|large-v3`
- `--language en`
- `--task transcribe|translate`
- `--output_format txt|srt|vtt|json`
- `--output_dir /path/to/output`

## Examples

Transcribe to text:
```
faster-whisper-gpu --model small --language en --task transcribe --output_format txt /path/to/audio.wav
```

Translate to English with subtitles:
```
faster-whisper-gpu --model medium --task translate --output_format srt /path/to/audio.wav
```

Batch process a directory:
```
for f in /path/to/audio/*.wav; do
  faster-whisper-gpu --model small --output_format txt "$f"
done
```

## Model cache and offline use

Models are cached under `/opt/faster-whisper/models`. Once the model is downloaded, Faster-Whisper runs fully offline.

To force a re-download, remove the cached model directory, for example:
```
rm -rf /opt/faster-whisper/models/models--Systran--faster-whisper-small
```

## Troubleshooting

- If `dgpu-run` is missing, install `tuxedo-dgpu-run` or run on CPU.
- If GPU mode fails, test with:
  ```
  dgpu-run nvidia-smi
  ```
