"""Capture SmartOffice ESP32 SoftAP/TCP telemetry as append-only JSONL.

Example:
  python tools/ei_capture_tcp.py --trial-id ipad_user_only_r01 --duration 20

Connect the computer to the ESP32 access point first. The program only opens a
TCP receive connection and never sends a command to the device.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import sys
import time
from pathlib import Path
from typing import Any


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.4.1", help="ESP32 SoftAP address")
    parser.add_argument("--tcp-port", type=int, default=3333, help="ESP32 telemetry TCP port")
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


def main() -> int:
    args = parse_args()
    if args.duration <= 0:
        raise SystemExit("--duration must be positive")
    if not 1 <= args.tcp_port <= 65535:
        raise SystemExit("--tcp-port must be between 1 and 65535")

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
        "transport": {"kind": "tcp", "host": args.host, "port": args.tcp_port, "timeout_s": 0.25},
        "capture_started_utc": start_wall,
        "requested_duration_s": args.duration,
        "tool": "tools/ei_capture_tcp.py",
        "data_status": "raw_unreviewed",
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    counts = {"measurement": 0, "state": 0, "heartbeat": 0, "json_other": 0, "json_non_object": 0, "non_json": 0}
    source = f"tcp://{args.host}:{args.tcp_port}"
    print(f"Capturing {source} for {args.duration:g}s -> {jsonl_path}")
    try:
        with socket.create_connection((args.host, args.tcp_port), timeout=5) as connection:
            connection.settimeout(0.25)
            receive_buffer = bytearray()
            with jsonl_path.open("x", encoding="utf-8", newline="\n") as sink:
                while time.monotonic() - start_mono < args.duration:
                    while b"\n" not in receive_buffer:
                        try:
                            chunk = connection.recv(4096)
                        except socket.timeout:
                            chunk = b""
                        if not chunk:
                            break
                        receive_buffer.extend(chunk)
                    if b"\n" not in receive_buffer:
                        continue
                    raw, _, remainder = receive_buffer.partition(b"\n")
                    receive_buffer = bytearray(remainder)
                    record: dict[str, Any] = {
                        "received_at_utc": utc_now(),
                        "elapsed_s": round(time.monotonic() - start_mono, 6),
                        "raw_utf8": raw.decode("utf-8", errors="replace").rstrip("\r"),
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
    except OSError as exc:
        jsonl_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        raise SystemExit(f"Cannot connect to {source}: {exc}") from exc

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
