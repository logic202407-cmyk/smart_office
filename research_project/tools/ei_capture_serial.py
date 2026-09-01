"""Capture SmartOffice USB-CDC telemetry as append-only JSONL for EI experiments.

Example:
  python tools/ei_capture_serial.py --port COM13 --trial-id distance_100cm_r01 --duration 30

The program never sends serial commands.  It records every received line with a
host timestamp, preserves non-JSON diagnostics, and writes a separate metadata
file so that each trial can be audited independently.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    import serial
except ImportError as exc:  # pragma: no cover - depends on local runtime
    raise SystemExit(
        "Missing pyserial. Run this script with the SmartOffice PC-client Python "
        "environment, where pyserial is installed."
    ) from exc


VALID_STATES = {
    "NORMAL",
    "HUMAN_DETECTED",
    "APPROACHING",
    "SUSPECTED_PEEPING",
    "PRIVACY_PROTECT",
    "ALARM",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def safe_name(value: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    result = "".join(char if char in allowed else "_" for char in value)
    return result.strip("_") or "trial"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="USB CDC port, e.g. COM13")
    parser.add_argument("--baud", type=int, default=115200, help="USB CDC baud rate")
    parser.add_argument("--trial-id", required=True, help="Unique, pre-registered trial identifier")
    parser.add_argument("--duration", type=float, required=True, help="Capture duration in seconds")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ei_experiments") / "raw",
        help="Directory for JSONL and metadata files",
    )
    parser.add_argument("--operator", default="", help="Optional operator identifier")
    parser.add_argument("--scenario", default="", help="Optional pre-registered scenario label")
    return parser.parse_args()


def classify(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "json_non_object"
    if payload.get("type") == "heartbeat":
        return "heartbeat"
    if payload.get("type") == "measurement":
        return "measurement"
    if payload.get("state") in VALID_STATES:
        return "state"
    return "json_other"


def main() -> int:
    args = parse_args()
    if args.duration <= 0:
        raise SystemExit("--duration must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_name(args.trial_id)
    jsonl_path = args.output_dir / f"{stem}.jsonl"
    meta_path = args.output_dir / f"{stem}.metadata.json"
    if jsonl_path.exists() or meta_path.exists():
        raise SystemExit(f"Refusing to overwrite existing trial files for {args.trial_id!r}")

    start_wall = utc_now()
    start_mono = time.monotonic()
    metadata = {
        "schema_version": "1.0",
        "trial_id": args.trial_id,
        "operator": args.operator,
        "scenario": args.scenario,
        "serial": {"port": args.port, "baud": args.baud, "timeout_s": 0.25},
        "capture_started_utc": start_wall,
        "requested_duration_s": args.duration,
        "tool": "tools/ei_capture_serial.py",
        "data_status": "raw_unreviewed",
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    counts = {"measurement": 0, "state": 0, "heartbeat": 0, "json_other": 0, "json_non_object": 0, "non_json": 0}
    print(f"Capturing {args.port} at {args.baud} baud for {args.duration:g}s -> {jsonl_path}")
    try:
        with serial.Serial(args.port, args.baud, timeout=0.25, write_timeout=1) as port:
            with jsonl_path.open("x", encoding="utf-8", newline="\n") as sink:
                while time.monotonic() - start_mono < args.duration:
                    raw = port.readline()
                    if not raw:
                        continue
                    record: dict[str, Any] = {
                        "received_at_utc": utc_now(),
                        "elapsed_s": round(time.monotonic() - start_mono, 6),
                        "raw_utf8": raw.decode("utf-8", errors="replace").rstrip("\r\n"),
                    }
                    try:
                        payload = json.loads(record["raw_utf8"])
                        record["payload"] = payload
                        kind = classify(payload)
                    except json.JSONDecodeError:
                        kind = "non_json"
                    record["record_type"] = kind
                    counts[kind] += 1
                    sink.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                    sink.flush()
    except serial.SerialException as exc:
        jsonl_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        raise SystemExit(f"Cannot open {args.port}: {exc}") from exc

    metadata.update(
        {
            "capture_finished_utc": utc_now(),
            "actual_duration_s": round(time.monotonic() - start_mono, 3),
            "record_counts": counts,
            "data_status": "raw_complete_pending_annotation",
        }
    )
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Capture complete:", json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
