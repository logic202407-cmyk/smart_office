#!/usr/bin/env python3
"""Capture HLK-LD2453 multi-target frames as line-delimited JSON.

Usage (after the CH340 adapter is connected):
  py tools/ld2453_reader.py --port COM7 --output ei_experiments/raw/ld2453_pilot.jsonl
  py tools/ld2453_reader.py --self-test

The parser implements the V1.0 user-manual data frame:
  AA FF 03 00 + 3 * 8-byte target records + 55 CC
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Iterator

FRAME_HEADER = bytes((0xAA, 0xFF, 0x03, 0x00))
FRAME_TAIL = bytes((0x55, 0xCC))
TARGET_BYTES = 8
TARGET_COUNT = 3
FRAME_BYTES = len(FRAME_HEADER) + TARGET_COUNT * TARGET_BYTES + len(FRAME_TAIL)


def decode_signed_magnitude(raw: int) -> int:
    """Decode the LD2453 sign-bit format used for x, y, and speed."""
    magnitude = raw & 0x7FFF
    if magnitude == 0:
        return 0
    return magnitude if raw & 0x8000 else -magnitude


def parse_target(record: bytes, index: int) -> dict | None:
    if len(record) != TARGET_BYTES:
        raise ValueError("target record must contain 8 bytes")
    x_raw = int.from_bytes(record[0:2], byteorder="little")
    y_raw = int.from_bytes(record[2:4], byteorder="little")
    speed_raw = int.from_bytes(record[4:6], byteorder="little")
    distance_mm = int.from_bytes(record[6:8], byteorder="little")
    if record == b"\x00" * TARGET_BYTES:
        return None
    return {
        "slot": index,
        "x_mm": decode_signed_magnitude(x_raw),
        "y_mm": decode_signed_magnitude(y_raw),
        "speed_cm_s": decode_signed_magnitude(speed_raw),
        "pixel_distance_mm": distance_mm,
    }


def parse_frame(frame: bytes) -> list[dict]:
    if len(frame) != FRAME_BYTES:
        raise ValueError(f"invalid frame length {len(frame)}; expected {FRAME_BYTES}")
    if not frame.startswith(FRAME_HEADER) or not frame.endswith(FRAME_TAIL):
        raise ValueError("invalid LD2453 frame delimiters")
    targets: list[dict] = []
    offset = len(FRAME_HEADER)
    for index in range(1, TARGET_COUNT + 1):
        target = parse_target(frame[offset : offset + TARGET_BYTES], index)
        if target is not None:
            targets.append(target)
        offset += TARGET_BYTES
    return targets


def frames_from_stream(serial_port) -> Iterator[bytes]:
    buffer = bytearray()
    while True:
        chunk = serial_port.read(serial_port.in_waiting or 1)
        if not chunk:
            continue
        buffer.extend(chunk)
        while True:
            start = buffer.find(FRAME_HEADER)
            if start < 0:
                del buffer[:-len(FRAME_HEADER) + 1]
                break
            if start > 0:
                del buffer[:start]
            if len(buffer) < FRAME_BYTES:
                break
            candidate = bytes(buffer[:FRAME_BYTES])
            if candidate.endswith(FRAME_TAIL):
                del buffer[:FRAME_BYTES]
                yield candidate
            else:
                del buffer[0]


def self_test() -> None:
    # Example target from the LD2453 V1.0 user manual: x=-782 mm, y=1713 mm,
    # speed=-16 cm/s, distance=360 mm.  The other two slots are empty.
    example = (
        FRAME_HEADER
        + bytes((0x0E, 0x03, 0xB1, 0x86, 0x10, 0x00, 0x68, 0x01))
        + b"\x00" * (TARGET_BYTES * 2)
        + FRAME_TAIL
    )
    result = parse_frame(example)
    expected = [{"slot": 1, "x_mm": -782, "y_mm": 1713,
                 "speed_cm_s": -16, "pixel_distance_mm": 360}]
    if result != expected:
        raise AssertionError(f"parser mismatch: {result!r}")
    print("LD2453 parser self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Windows serial port, e.g. COM7")
    parser.add_argument("--baud", type=int, default=256000)
    parser.add_argument("--output", type=Path, help="append parsed frames to this JSONL file")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.port or not args.output:
        parser.error("--port and --output are required unless --self-test is used")
    try:
        import serial  # type: ignore[import-not-found]
    except ImportError:
        print("Missing dependency: install with `py -m pip install pyserial`.", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    print(f"Opening {args.port} at {args.baud} baud; Ctrl+C stops capture.")
    try:
        with serial.Serial(args.port, args.baud, timeout=0.2) as serial_port, args.output.open(
            "a", encoding="utf-8"
        ) as output:
            for frame in frames_from_stream(serial_port):
                record = {
                    "type": "ld2453_targets",
                    "t_ms": round((time.monotonic() - started) * 1000),
                    "targets": parse_frame(frame),
                    "raw_hex": frame.hex(),
                }
                line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                print(line)
                output.write(line + "\n")
                output.flush()
    except KeyboardInterrupt:
        print("Capture stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
