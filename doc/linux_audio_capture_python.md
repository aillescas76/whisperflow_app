# Architectural Analysis and Implementation Strategy for Real-Time Audio Capture on Linux Audio Subsystems

## 1. Executive Summary and System Architecture Overview
The evolution of the Linux audio landscape, particularly with Ubuntu 24.04 LTS and derivatives such as TUXEDO OS 24.04, represents a fundamental shift in how applications interact with hardware. The transition from the PulseAudio/JACK split to the unified PipeWire multimedia server creates new opportunities for low-latency audio capture and also new configuration constraints for Python applications. This document provides an engineering analysis of methods for implementing live, chunked audio capture for offline transcription using Faster-Whisper.

The target environment (TUXEDO OS 24.04, kernel 6.14, Python 3.12.3) favors a modern approach to audio handling. Legacy libraries that access ALSA hardware directly can fail in a PipeWire-managed environment, causing "Device Busy" errors or silent failures. The requirement for 16 kHz mono PCM capture for Faster-Whisper imposes strict data formatting constraints that influence library selection.

After evaluating available options, this analysis recommends `sounddevice` (PortAudio via CFFI) for capture and a rolling-buffer design gated by silence detection (VAD-style). This avoids context loss from naive 1-second chunking while keeping latency low.

Important: transcription must use the system CLI wrapper `/usr/local/bin/faster-whisper-gpu` and only the supported options (model, language, task, output_format, output_dir). Any example here should feed audio to that CLI rather than calling a Python inference API.

## 2. Linux Audio Subsystem in 2026: TUXEDO OS 24.04 Context
### 2.1 Kernel Layer: ALSA and Kernel 6.14
At the lowest level, Linux manages audio hardware through ALSA. ALSA exposes hardware devices as nodes such as `/dev/snd/pcmC0D0c`.

Historically, applications would open ALSA devices directly. In modern desktop environments, the sound server (PipeWire) takes exclusive control of these ALSA devices. A Python script that opens `hw:0,0` directly while the desktop stack is running will often get a "Device or resource busy" error.

Implication: the application should connect to the sound server (via ALSA plugin or PulseAudio compatibility) instead of bypassing it.

### 2.2 Sound Server Layer: PipeWire vs. PulseAudio vs. JACK
PipeWire is now the central graph-based media engine, unifying consumer and professional audio pipelines. On TUXEDO OS 24.04, it provides:

- Compatibility layers for PulseAudio and JACK
- An ALSA plugin that routes ALSA API calls into PipeWire
- Dynamic latency control (quantum) based on application needs
- Session management and device routing through WirePlumber

For Python libraries such as `sounddevice` and `pyaudio`, the data path typically looks like:

- App -> PortAudio -> ALSA -> PipeWire ALSA plugin -> PipeWire daemon -> Kernel

This is the most stable path for desktop audio capture in 2026.

### 2.3 Headless and CLI Constraints
This project avoids GUI dependencies, but device selection must still work in a CLI. PipeWire maintains a default input device, so connecting to the generic "default" source allows the app to stay hardware-agnostic. This is important for both laptops and external USB microphones.

## 3. Comparative Technical Evaluation of Capture Options
### 3.1 Option A: `sounddevice` (Recommended)
`sounddevice` provides Python bindings for PortAudio using CFFI.

Architectural advantages:
- Zero-copy transfers into NumPy arrays
- Supports float32 sample format natively
- Non-blocking callbacks enable a clean producer-consumer design

Compatibility and stability:
- Works well with the PipeWire ALSA bridge
- Good low-latency behavior on Ubuntu 24.04

Constraints:
- Requires system PortAudio libraries (runtime and headers)

### 3.2 Option B: `pyaudio` (Legacy)
`pyaudio` is a long-standing PortAudio binding, but it is less friendly on modern Python.

Limitations:
- Byte-string output requires conversion to floats
- Python 3.12 build friction is common
- Blocking reads can overflow if inference takes too long

### 3.3 Option C: `ffmpeg` (Subprocess)
Spawning `ffmpeg` and reading PCM from stdout is robust but has tradeoffs.

Advantages:
- Process isolation reduces GC interference
- High-quality resampling filters

Limitations:
- Buffering can increase latency
- Parsing raw streams is error-prone
- Extra IPC overhead vs. in-process capture

### 3.4 Option D: `pw-record` (PipeWire CLI)
`pw-record` is the native PipeWire recorder.

Advantages:
- Direct PipeWire integration
- Available by default on TUXEDO OS

Limitations:
- Coarse process-level control
- Still requires PCM stream parsing in Python

### 3.5 Summary of Evaluation
| Feature | sounddevice | pyaudio | ffmpeg CLI | pw-record |
| --- | --- | --- | --- | --- |
| Primary interface | CFFI (PortAudio) | C extension (PortAudio) | Subprocess (pipe) | Subprocess (pipe) |
| Output data | NumPy float32 | Raw bytes | Raw bytes | Raw bytes |
| Whisper integration | Feed CLI wrapper | Feed CLI wrapper | Feed CLI wrapper | Feed CLI wrapper |
| Latency | Low | Medium | High (buffered) | Low |
| CPU efficiency | High | High | Medium | Very high |
| Installation ease | Moderate (system deps) | Difficult (3.12) | Easy (apt) | Easy (apt) |
| Stability on 24.04 | Excellent | Good | Excellent | Excellent |

Conclusion: `sounddevice` is the best default choice for clean, low-latency capture in Python.

## 4. Theoretical Framework for Real-Time Transcription
### 4.1 The Physics of Digital Audio Capture
The requirement specifies 16 kHz mono capture:

- Sample rate: 16,000 Hz, sufficient for speech (up to 8 kHz)
- Bit depth: Faster-Whisper expects float32 or 16-bit PCM
- Conversion: `float = int16 / 32768.0`
- Data rate: `16000 * 4 bytes = 64 KB/s`

### 4.2 The Chunking Fallacy and Context Loss
Whisper models are trained on longer windows (around 30 seconds). Cutting into strict 1-second chunks can lose context and produce errors at word boundaries. This manifests as split or hallucinated words.

### 4.3 The Rolling Buffer Architecture
A rolling buffer keeps a recent window of audio and only triggers transcription when silence is detected. This preserves speech context while keeping latency low.

#### 4.3.1 Circular Buffering
- Capture micro-chunks (e.g., 20 to 100 ms)
- Append to a rolling buffer
- Analyze the buffer for speech boundaries

#### 4.3.2 VAD-Gated Transcription
- Monitor energy or use VAD
- When silence exceeds a threshold (e.g., 0.5 s), treat the buffered audio as a phrase
- Transcribe the phrase, then clear the buffer

## 5. Detailed Engineering and Implementation Strategy
### 5.1 System Configuration and Dependencies
Install system libraries for PortAudio and Python headers:

```bash
sudo apt update
sudo apt install libportaudio2 portaudio19-dev python3-dev
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install Python packages for capture and buffering:

```bash
uv pip install sounddevice numpy  # installs into .venv
```

Note: transcription should still be performed via `/usr/local/bin/faster-whisper-gpu` with supported options only.

### 5.2 Software Architecture: Producer-Consumer Pattern
- Producer: audio callback that pushes captured frames into a thread-safe queue
- Consumer: main loop that processes the queue, builds a rolling buffer, and triggers transcription based on silence

### 5.3 Integration Strategy with the CLI Wrapper
Instead of using a Python inference API, the live loop should:

1) Capture audio into a rolling buffer.
2) When silence is detected, write a temporary WAV file for the buffered phrase.
3) Call `/usr/local/bin/faster-whisper-gpu` with the supported options:
   - `--model`, `--language`, `--task`, `--output_format`, `--output_dir`
4) Read the resulting transcript from the output file and append to the raw transcript log.

This preserves the offline-only, CLI-wrapper requirement and avoids extra dependencies.

## 6. Performance Optimization and System Tuning
Total latency can be expressed as:

```
Latency_total = Latency_buffer + Latency_inference + Latency_system
```

### 6.1 Inference Optimization (Biggest Bottleneck)
- Model selection:
  - `small` is fast but less accurate
  - `medium` balances speed and quality
  - `large-v3` is most accurate but slower on CPU
- Beam size: stick with wrapper defaults unless options expand later

### 6.2 System-Level Tuning (TUXEDO OS)
If inference competes with the audio thread, dropouts can occur.

- Real-time priority:
  - Check: `ulimit -r`
  - Configure `/etc/security/limits.d/audio.conf`:

```conf
@audio - rtprio 95
@audio - memlock unlimited
```

- Add user to the audio group:

```bash
sudo usermod -aG audio "$USER"
```

- CPU governor: set to a performance profile in TUXEDO Control Center.

## 7. Troubleshooting Guide
### 7.1 Error: "PortAudio library not found"
Cause: `libportaudio.so.2` is missing or not in the linker path.

Fix:
- Verify installation: `dpkg -L libportaudio2`
- Update linker cache: `sudo ldconfig`

### 7.2 Error: "Device Unavailable" or "Busy"
Cause: the script is trying to open a hardware device directly.

Fix:
- Use the default device (`DEVICE_INDEX = None`) or select a PipeWire device
- Do not open `hw:0` directly

### 7.3 Symptom: Hallucinations ("Thank you", "Subtitles by...")
Cause: whisper is very sensitive to silence and low-level noise.

Fix:
- Gate transcription by RMS threshold
- Avoid sending silent buffers to the model

## 8. Conclusion
Building a reliable real-time transcription system on TUXEDO OS 24.04 requires a modern capture path that coexists with PipeWire and preserves speech context. `sounddevice` plus a VAD-gated rolling buffer offers the best mix of performance and maintainability. Avoid fixed 1-second chunks and prioritize buffering strategies that align with how Whisper models were trained.

## Final Recommendations Checklist
- Library: use `sounddevice` (not `pyaudio`)
- Architecture: producer-consumer with `queue.Queue`
- Strategy: VAD-gated rolling buffer (not fixed chunks)
- Format: float32 or 16-bit PCM, 16 kHz, mono
- Backend: `/usr/local/bin/faster-whisper-gpu` only
- System: set audio thread priority and CPU governor for stability
