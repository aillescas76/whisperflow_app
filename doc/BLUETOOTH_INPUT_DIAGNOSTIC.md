# Whisperflow Bluetooth Input Mapping Issue

## Summary
When using Bluetooth headsets selected via the desktop Sound Settings UI, `sounddevice` (PortAudio/ALSA) often does not expose the same device that PipeWire/PulseAudio advertises as the default input. This causes Whisperflow to log warnings like:

```
Unable to map system default source 'bluez_input.00:1B:66:0F:E8:1B' to a sounddevice input.
```

The result is that Whisperflow falls back to PortAudio's default device, which may not match the system-selected input.

## System Information (Observed)
From diagnostics run in the current environment:

- Audio stack: PipeWire (PulseAudio compatibility layer)
- `pactl info` reports:
  - Server Name: `PulseAudio (on PipeWire 1.4.9)`
  - Default Source: `bluez_input.00:1B:66:0F:E8:1B`
  - Default Sample Rate: 48000 Hz
- `pactl list sources short` includes:
  - `bluez_input.00:1B:66:0F:E8:1B` (Bluetooth mic)
  - `alsa_input.pci-0000_06_00.6.analog-stereo`
  - `alsa_input.usb-DisplayLink_Dell_D3100_USB3.0_Dock...`
  - `alsa_input.usb-TTGK_Technology_USB_Audio...`
- `sounddevice.query_devices()` returns ALSA devices (e.g., `USB Audio`, `ALC274 Analog`) but does not list the PipeWire `bluez_input` source directly.

## Expected Behavior
Whisperflow should capture from the same input device selected in the OS Sound Settings UI. In PipeWire/PulseAudio environments, that means following the default source reported by `pactl info` and resolving it to a usable capture device.

## Current Behavior
- `open_audio_capture()` defaults to `sounddevice` when available.
- `sounddevice` is resolved using ALSA/PortAudio device names that may not include the PipeWire Bluetooth source.
- If the Bluetooth source is idle or not active, it can be absent from `sounddevice` entirely.
- Mapping fails, and the app logs a warning and falls back to the default PortAudio device.

## Relevant Code (Current)

### Resolver entry point
From `whisperflow/audio.py`:

```
    if resolved == "sounddevice":
        resolved_device = device
        if device == "default":
            system_device = _resolve_system_default_device()
            if system_device is not None:
                resolved_device = system_device
                logger.info("Resolved system default input device to %s.", system_device)
        return _SoundDeviceCapture(resolved_device, sample_rate, channels, chunk_ms)
```

### PipeWire default-source lookup

```
    def _pactl_default_source() -> str | None:
        result = subprocess.run(["pactl", "info"], capture_output=True, text=True, check=False)
        for line in result.stdout.splitlines():
            if line.startswith("Default Source:"):
                return line.split(":", 1)[1].strip()
        return None
```

### Metadata parsing + matching

```
    metadata = _pactl_source_metadata(default_source)
    ...
    score = _score_device_match(
        default_source,
        description,
        device_description,
        product_name,
        card_name,
        long_card_name,
        device_name=name,
    )
```

### Mapping failure logging

```
    if best_score == 0:
        logger.warning(
            "Unable to map system default source '%s' to a sounddevice input.",
            default_source,
        )
        _log_sounddevice_inputs(devices)
        return None
```

## Root Cause Hypothesis
- The Sound Settings UI uses PipeWire's default source (Bluetooth input), but PortAudio/ALSA (and thus `sounddevice`) may not expose the Bluetooth source name.
- Bluetooth capture devices can enter a sleep/idle mode. In that state, they often do not present as ALSA capture devices, so `sounddevice.query_devices()` never lists them.
- Result: mapping fails even when PipeWire reports the Bluetooth source as default.

## Suggested Directions for a Proper Fix

1. **Prefer PipeWire-native capture for Bluetooth sources**
   - If the default source name starts with `bluez_input`, consider using the `pw-record` backend rather than `sounddevice`.
   - This keeps capture in PipeWire, which aligns with the system UI selection.

2. **Add a keep-alive / activation probe**
   - Attempt a short PipeWire capture (via `pw-record` or `pactl`) to wake the Bluetooth device before querying `sounddevice`.

3. **Enhance resolver fallback**
   - If Bluetooth mapping fails, log a clear message and suggest switching to `pw-record`.
   - Provide a config flag such as `live_capture.audio.device: "system"` that explicitly uses PipeWire defaults.

4. **Expose detected defaults in logs**
   - Always log the PipeWire default source, device properties, and the list of sounddevice inputs.

5. **Optional UI/CLI diagnostics command**
   - A `whisperflow diagnose audio` command could print PipeWire and PortAudio views side-by-side for faster troubleshooting.

## Next Steps (Investigation)
- Inspect PipeWire source properties for the Bluetooth headset to see which identifiers can be matched to ALSA devices.
- Confirm whether the Bluetooth source becomes visible in `sounddevice` after a short recording starts.
- Evaluate switching to the `pw-record` backend for Bluetooth sources by default.
