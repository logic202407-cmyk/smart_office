# SmartOffice PeepPrevention PC Client

This directory contains the desktop-side software for the SmartOffice privacy
protection prototype. It receives JSON telemetry from the ESP32 over serial and
drives two presentation layers:

- a native PyQt6 privacy overlay application
- a lightweight browser dashboard for demo and debugging

## Features

- Serial JSON ingestion with auto reconnect
- Multi-monitor full-screen privacy overlay
- Privacy state driven opacity and warning text
- Alarm audio playback with fallback behavior
- Optional system tray integration
- Cross-platform lock-screen trigger
- Web dashboard with live state, distance curve, and raw line viewer

## Requirements

- Python 3.9+
- Windows 10/11 recommended
- An ESP32 board sending one JSON object per line over serial

Install dependencies:

```bash
pip install -r requirements.txt
```

## Files

- `main.py`: desktop application entry point
- `config_manager.py`: YAML config loading and defaults
- `serial_reader.py`: serial thread, parsing, reconnect logic
- `overlay_window.py`: privacy overlay UI
- `tray_app.py`: tray icon and quick actions
- `sound_alarm.py`: alarm sound control
- `lock_screen.py`: platform-specific lock-screen helpers
- `web_dashboard.py`: browser demo dashboard
- `config.yaml`: local runtime configuration

## 1. Run The Native Overlay App

```bash
python main.py
```

Useful options:

```bash
python main.py -c config.yaml
python main.py -d
python main.py -h
```

The app will:

- connect to the serial device automatically if `serial.port` is empty
- create one overlay window per monitor
- react to privacy states such as `APPROACHING` and `PRIVACY_PROTECT`
- start a lock-screen countdown when configured

## 2. Run The Web Dashboard

```bash
python web_dashboard.py --serial COM5
```

If you prefer the PlatformIO runtime:

```bash
C:\.platformio\penv\Scripts\python.exe web_dashboard.py --serial COM5
```

Then open:

```text
http://127.0.0.1:8765/
```

Useful options:

```bash
python web_dashboard.py --serial COM5 --http-port 8765
python web_dashboard.py --serial COM5 --baud 115200
python web_dashboard.py --serial COM5 --open
```

The dashboard ignores human-readable debug lines such as `[PRIVACY_TEST] ...`
and only consumes JSON telemetry.

## Serial JSON Format

Example payload:

```json
{
  "state": "PRIVACY_PROTECT",
  "distance_cm": 78,
  "avg_distance_cm": 74,
  "display_distance_cm": 76,
  "trend": "STABLE",
  "present": true,
  "frames": 1452,
  "hold_ms": 58231,
  "state_hold_ms": 21450,
  "downgrade_hold_ms": 0,
  "moving_distance_cm": 81,
  "moving_energy": 92,
  "static_distance_cm": 79,
  "static_energy": 100,
  "age_ms": 24
}
```

## Configuration

Edit `config.yaml` to tune behavior.

Typical fields include:

- serial port and baud rate
- overlay opacity per state
- distance and alarm thresholds
- lock-screen delay
- logging verbosity

## Troubleshooting

### Serial port not found

- Check that the ESP32 is powered and recognized by the system
- Set `serial.port` manually in `config.yaml`
- Close other tools that may already hold the COM port

### No sound

- Ensure `pygame` is installed
- Verify the configured sound file path
- The app can fall back to simpler system alert behavior

### Lock screen does not trigger

- Windows uses `LockWorkStation`
- macOS uses `osascript`
- Linux support depends on the desktop environment and available lock command
