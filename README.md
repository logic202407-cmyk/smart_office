# SmartOffice Privacy Radar

SmartOffice Privacy Radar is an embedded-plus-PC privacy protection prototype
for office and study scenarios. The system uses an ESP32-S3, an LD2410B mmWave
radar, an OLED display, and a PAJ7620U2 gesture sensor to detect nearby human
presence, estimate risk states, and trigger local privacy responses.

The project currently includes:

- ESP32 firmware for radar parsing, distance tracking, privacy state logic, OLED
  rendering, and gesture input
- a Python desktop client for full-screen privacy overlay and lock-screen flow
- a browser dashboard for live demo, telemetry visualization, and debugging

## Demo Goals

- Detect people approaching from behind or beside the screen
- Convert noisy radar data into stable privacy states
- Show local status on OLED in real time
- Support gesture interaction for local control
- Provide a stronger demo experience through a PC-side live dashboard

## Hardware Stack

- `ESP32-S3-WROOM-1`
- `HLK-LD2410B-P` mmWave radar
- `0.96"` I2C OLED display
- `PAJ7620U2` gesture sensor
- USB Type-C power/programming interface

## Repository Layout

```text
smart_office/
├─ firmware/      ESP32 PlatformIO project
├─ pc_client/     Python desktop client and web dashboard
├─ tests/         parser and state-machine tests, hardware checklist
├─ docs/          implementation change notes
├─ documents/     architecture and planning notes
└─ tools/         flashing helpers and binary artifacts
```

## Current Implemented Capabilities

### Firmware

- LD2410B radar frame parsing
- target fusion and primary-distance selection
- distance smoothing and display filtering
- privacy state machine with hold and downgrade timing
- OLED status page rendering
- PAJ7620U2 gesture sensor integration
- serial JSON telemetry output for PC tools
- human-readable debug logs for tuning

### PC Client

- PyQt6 privacy overlay application
- serial JSON reader with reconnect support
- cross-platform lock-screen helper
- alarm audio support
- live web dashboard at `http://127.0.0.1:8765/`

## Quick Start

## 1. Firmware

Location:

`firmware/`

Build:

```bash
cd firmware
pio run
```

Upload:

```bash
pio run -t upload
```

Monitor:

```bash
pio device monitor
```

The firmware target is defined in [firmware/platformio.ini](firmware/platformio.ini).

## 2. PC Client

Location:

`pc_client/`

Install dependencies:

```bash
cd pc_client
pip install -r requirements.txt
```

Run desktop overlay app:

```bash
python main.py
```

Run browser dashboard:

```bash
python web_dashboard.py --serial COM5
```

Open:

```text
http://127.0.0.1:8765/
```

More details are in [pc_client/README.md](pc_client/README.md).

## Telemetry Interface

The firmware emits one JSON line per sample for the PC-side tools. Example:

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
  "downgrade_hold_ms": 0
}
```

The dashboard ignores non-JSON tuning logs such as `[RADAR_TRACK]` or
`[PRIVACY_TEST]`, so debug output and structured telemetry can coexist.

## Development Notes

- `firmware/.gitignore` excludes PlatformIO build output
- top-level `.gitignore` excludes local cache and IDE files
- `tools/` currently contains helper binaries and flashing-related assets
- `documents/` contains working design notes rather than polished end-user docs

## Suggested Workflow

1. Flash the firmware to the ESP32-S3.
2. Verify OLED output and gesture sensor behavior locally.
3. Watch raw serial output to confirm telemetry stability.
4. Run the web dashboard for state and distance visualization.
5. Tune thresholds and filtering in firmware based on live results.

## Status

This repository is an actively iterated prototype rather than a frozen release.
The strongest current focus is improving radar distance stability, state
responsiveness, and overall demo smoothness in real office-like environments.
