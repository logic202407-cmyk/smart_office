#!/usr/bin/env python3
"""Serial-to-web dashboard for the ESP32 privacy prototype."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

try:
    import serial
    import serial.tools.list_ports
except ImportError as exc:
    raise SystemExit("pyserial is required. Run: python -m pip install pyserial") from exc


DEFAULT_BAUD = 115200
MAX_SAMPLES = 300


class DashboardState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.latest: dict[str, Any] = {
            "connected": False,
            "state": "OFFLINE",
            "distance_cm": 0,
            "avg_distance_cm": 0,
            "trend": "NONE",
            "present": False,
            "frames": 0,
            "age_ms": 0,
            "message": "Waiting for serial data",
        }
        self.samples: deque[dict[str, Any]] = deque(maxlen=MAX_SAMPLES)
        self.raw_lines: deque[str] = deque(maxlen=20)

    def update_sample(self, sample: dict[str, Any]) -> None:
        now = int(time.time() * 1000)
        sample = dict(sample)
        sample["pc_time_ms"] = now
        sample["connected"] = True
        sample.setdefault("message", "Live")
        with self._lock:
            self.latest = sample
            self.samples.append(sample)

    def update_message(self, message: str, connected: bool = False) -> None:
        with self._lock:
            self.latest = dict(self.latest)
            self.latest["message"] = message
            self.latest["connected"] = connected
            if not connected and self.latest.get("state") == "OFFLINE":
                self.latest["state"] = "OFFLINE"

    def add_raw_line(self, line: str) -> None:
        with self._lock:
            self.raw_lines.append(line[-240:])

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "latest": dict(self.latest),
                "samples": list(self.samples),
                "raw_lines": list(self.raw_lines),
            }


class SerialWorker(threading.Thread):
    def __init__(self, state: DashboardState, port: str, baud: int) -> None:
        super().__init__(daemon=True)
        self.state = state
        self.port = port
        self.baud = baud
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                port = self.port or auto_detect_port()
                if not port:
                    self.state.update_message("No serial port found", connected=False)
                    time.sleep(1.0)
                    continue

                self.state.update_message(f"Opening {port} @ {self.baud}", connected=False)
                with serial.Serial(port, self.baud, timeout=0.5) as ser:
                    ser.dtr = False
                    ser.rts = False
                    self.state.update_message(f"Connected to {port}", connected=True)
                    while not self.stop_event.is_set():
                        raw = ser.readline()
                        if not raw:
                            continue
                        line = raw.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        self.state.add_raw_line(line)
                        if not line.startswith("{"):
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if "state" in data and "distance_cm" in data:
                            self.state.update_sample(data)
            except serial.SerialException as exc:
                self.state.update_message(f"Serial error: {exc}", connected=False)
                time.sleep(1.0)

    def stop(self) -> None:
        self.stop_event.set()


def auto_detect_port() -> str:
    ports = list(serial.tools.list_ports.comports())
    for item in ports:
        desc = f"{item.description} {item.manufacturer or ''} {item.hwid}".lower()
        if any(token in desc for token in ("esp", "usb", "uart", "serial", "jtag", "cp210", "ch34")):
            return item.device
    return ports[0].device if ports else ""


def make_handler(state: DashboardState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self._send_html(INDEX_HTML)
            elif path == "/api/state":
                self._send_json(state.snapshot())
            else:
                self.send_error(404, "Not found")

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send_html(self, content: str) -> None:
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Privacy Radar Dashboard</title>
<style>
:root {
  --bg: #10130f;
  --panel: rgba(246, 239, 218, 0.08);
  --panel-strong: rgba(246, 239, 218, 0.14);
  --text: #f7efd8;
  --muted: #bdb49d;
  --line: rgba(247, 239, 216, 0.18);
  --green: #9fd86b;
  --amber: #f2b84b;
  --orange: #ff7f4d;
  --red: #ff4d57;
  --blue: #7ab7ff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  color: var(--text);
  font-family: "Bahnschrift", "Aptos Display", "Segoe UI", sans-serif;
  overflow-x: hidden;
  background:
    radial-gradient(circle at 12% 18%, rgba(127, 184, 255, 0.18), transparent 28rem),
    radial-gradient(circle at 86% 8%, rgba(255, 127, 77, 0.16), transparent 25rem),
    linear-gradient(135deg, #0c0f0a 0%, #151a12 48%, #090a08 100%);
}
.shell { width: min(1180px, calc(100vw - 32px)); margin: 0 auto; padding: 34px 0; }
.topbar { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 26px; }
h1 { margin: 0; font-size: clamp(34px, 5vw, 68px); letter-spacing: -0.06em; line-height: 0.92; }
.subtitle { color: var(--muted); max-width: 520px; line-height: 1.5; margin: 12px 0 0; }
.pill { border: 1px solid var(--line); border-radius: 999px; padding: 10px 14px; color: var(--muted); background: rgba(0,0,0,0.18); white-space: nowrap; }
.grid {
  display: grid;
  grid-template-columns: minmax(360px, 0.85fr) minmax(520px, 1.35fr);
  grid-template-areas:
    "state telemetry"
    "chart raw";
  gap: 18px;
}
.panel { border: 1px solid var(--line); background: var(--panel); border-radius: 28px; padding: 22px; box-shadow: 0 24px 80px rgba(0,0,0,0.24); backdrop-filter: blur(16px); }
.hero-state { grid-area: state; min-height: 290px; display: flex; flex-direction: column; justify-content: space-between; position: relative; overflow: hidden; }
.hero-state:after { content: ""; position: absolute; inset: auto -12% -35% 40%; height: 180px; background: radial-gradient(circle, currentColor, transparent 68%); opacity: 0.18; }
.state-name { font-size: clamp(34px, 4.7vw, 68px); letter-spacing: -0.06em; line-height: 0.9; margin: 14px 0; white-space: pre-line; overflow-wrap: anywhere; }
.state-meta { display: flex; gap: 10px; flex-wrap: wrap; position: relative; z-index: 1; }
.metric { border-radius: 20px; background: rgba(0,0,0,0.18); border: 1px solid var(--line); padding: 14px 16px; min-width: 124px; }
.metric span { display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.12em; }
.metric strong { display: block; margin-top: 8px; font-size: 28px; letter-spacing: -0.04em; }
.chart { grid-area: chart; height: 360px; }
canvas { width: 100%; height: 280px; display: block; margin-top: 14px; }
.side { grid-area: telemetry; display: grid; gap: 18px; }
.kv { display: grid; gap: 11px; margin-top: 14px; }
.row { display: flex; justify-content: space-between; gap: 20px; color: var(--muted); border-bottom: 1px solid rgba(247,239,216,0.1); padding-bottom: 9px; }
.row strong { color: var(--text); text-align: right; }
.raw-panel { grid-area: raw; min-width: 0; }
.raw { font-family: "Cascadia Mono", Consolas, monospace; color: #d6ceb7; font-size: 12px; line-height: 1.55; max-height: 210px; overflow: auto; white-space: pre; max-width: 100%; }
.normal { color: var(--green); }
.human { color: var(--blue); }
.approach { color: var(--amber); }
.suspect { color: var(--orange); }
.protect { color: var(--red); }
.offline { color: var(--muted); }
@media (max-width: 860px) {
  .topbar { align-items: start; flex-direction: column; }
  .grid { grid-template-columns: 1fr; grid-template-areas: "state" "telemetry" "chart" "raw"; }
  .shell { width: min(100vw - 22px, 640px); padding-top: 22px; }
}
</style>
</head>
<body>
<main class="shell">
  <section class="topbar">
    <div>
      <h1>Privacy Radar<br>Live Console</h1>
      <p class="subtitle">ESP32 serial JSON becomes a live product demo: state, distance, trend, and protection timing in one screen.</p>
    </div>
    <div id="conn" class="pill">Connecting...</div>
  </section>
  <section class="grid">
    <article id="statePanel" class="panel hero-state offline">
      <div>
        <div class="pill" id="message">Waiting for serial data</div>
        <div id="stateName" class="state-name">OFFLINE</div>
      </div>
      <div class="state-meta">
        <div class="metric"><span>Distance</span><strong id="distance">-- cm</strong></div>
        <div class="metric"><span>Average</span><strong id="avg">-- cm</strong></div>
        <div class="metric"><span>Trend</span><strong id="trend">NONE</strong></div>
      </div>
    </article>
    <aside class="side">
      <article class="panel">
        <h2>Live Telemetry</h2>
        <div class="kv">
          <div class="row"><span>Present</span><strong id="present">--</strong></div>
          <div class="row"><span>Frames</span><strong id="frames">--</strong></div>
          <div class="row"><span>Display distance</span><strong id="displayDistance">-- cm</strong></div>
          <div class="row"><span>Raw target</span><strong id="rawDistance">-- cm</strong></div>
          <div class="row"><span>Gesture</span><strong id="gesture">NONE</strong></div>
          <div class="row"><span>Gesture age</span><strong id="gestureAge">-- ms</strong></div>
          <div class="row"><span>State hold</span><strong id="stateHold">-- ms</strong></div>
          <div class="row"><span>Downgrade hold</span><strong id="downHold">-- ms</strong></div>
          <div class="row"><span>Radar age</span><strong id="dataAge">-- ms</strong></div>
          <div class="row"><span>Moving</span><strong id="moving">--</strong></div>
          <div class="row"><span>Static</span><strong id="static">--</strong></div>
        </div>
      </article>
    </aside>
    <article class="panel chart">
      <h2>Distance Curve</h2>
      <canvas id="chart" width="900" height="280"></canvas>
    </article>
    <article class="panel raw-panel">
      <h2>Recent Raw Lines</h2>
      <div id="raw" class="raw"></div>
    </article>
  </section>
</main>
<script>
const classes = {
  NORMAL: "normal",
  HUMAN_DETECTED: "human",
  APPROACHING: "approach",
  SUSPECTED_PEEPING: "suspect",
  PRIVACY_PROTECT: "protect",
  OFFLINE: "offline"
};
const stateLabels = {
  NORMAL: "NORMAL",
  HUMAN_DETECTED: "HUMAN\nDETECTED",
  APPROACHING: "APPROACHING",
  SUSPECTED_PEEPING: "SUSPECTED\nPEEPING",
  PRIVACY_PROTECT: "PRIVACY\nPROTECT",
  OFFLINE: "OFFLINE"
};

function text(id, value) {
  document.getElementById(id).textContent = value;
}

function drawChart(samples) {
  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "rgba(247,239,216,.14)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = 20 + i * ((h - 42) / 4);
    ctx.beginPath();
    ctx.moveTo(10, y);
    ctx.lineTo(w - 10, y);
    ctx.stroke();
  }
  const data = samples.filter(s => Number(s.distance_cm) > 0).slice(-120);
  if (data.length < 2) return;
  const maxY = Math.max(150, ...data.map(s => Number(s.distance_cm) || 0));
  const minY = 0;
  const x = i => 14 + i * ((w - 28) / Math.max(1, data.length - 1));
  const y = v => h - 22 - ((v - minY) / (maxY - minY)) * (h - 46);
  const grad = ctx.createLinearGradient(0, 0, w, 0);
  grad.addColorStop(0, "#9fd86b");
  grad.addColorStop(.55, "#f2b84b");
  grad.addColorStop(1, "#ff4d57");
  ctx.strokeStyle = grad;
  ctx.lineWidth = 4;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.beginPath();
  data.forEach((s, i) => {
    const px = x(i), py = y(Number(s.distance_cm) || 0);
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  });
  ctx.stroke();
  ctx.fillStyle = "rgba(247,239,216,.55)";
  ctx.font = "13px Cascadia Mono, monospace";
  ctx.fillText("0 cm", 14, h - 8);
  ctx.fillText(`${maxY} cm`, 14, 18);
}

async function refresh() {
  try {
    const res = await fetch("/api/state", { cache: "no-store" });
    const payload = await res.json();
    const latest = payload.latest || {};
    const state = latest.state || "OFFLINE";
    const cls = classes[state] || "offline";
    const panel = document.getElementById("statePanel");
    panel.className = `panel hero-state ${cls}`;
    text("conn", latest.connected ? "Serial online" : "Serial offline");
    text("message", latest.message || "Live");
    text("stateName", stateLabels[state] || state.replace("_", "\n"));
    const displayDistance = latest.display_distance_cm || latest.distance_cm || 0;
    text("distance", displayDistance ? `${displayDistance} cm` : "-- cm");
    text("avg", latest.avg_distance_cm ? `${latest.avg_distance_cm} cm` : "-- cm");
    text("trend", latest.trend || "NONE");
    text("present", latest.present ? "yes" : "no");
    text("frames", latest.frames ?? "--");
    text("displayDistance", displayDistance ? `${displayDistance} cm` : "-- cm");
    text("rawDistance", latest.raw_distance_cm ? `${latest.raw_distance_cm} cm` : "-- cm");
    text("gesture", latest.gesture || "NONE");
    text("gestureAge", `${latest.gesture_age_ms ?? 0} ms`);
    text("stateHold", `${latest.state_hold_ms ?? 0} ms`);
    text("downHold", `${latest.downgrade_hold_ms ?? 0} ms`);
    text("dataAge", `${latest.age_ms ?? 0} ms`);
    text("moving", `${latest.moving_distance_cm ?? 0} cm / ${latest.moving_energy ?? 0}%`);
    text("static", `${latest.static_distance_cm ?? 0} cm / ${latest.static_energy ?? 0}%`);
    text("raw", (payload.raw_lines || []).slice(-10).join("\n"));
    drawChart(payload.samples || []);
  } catch (err) {
    text("conn", "Dashboard error");
  }
}
refresh();
setInterval(refresh, 120);
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ESP32 privacy radar web dashboard")
    parser.add_argument("--serial", default="", help="Serial port, for example COM5")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="Serial baud rate")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host")
    parser.add_argument("--http-port", type=int, default=8765, help="HTTP port")
    parser.add_argument("--open", action="store_true", help="Open browser automatically")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = DashboardState()
    worker = SerialWorker(state, args.serial, args.baud)
    worker.start()

    server = ThreadingHTTPServer((args.host, args.http_port), make_handler(state))
    url = f"http://{args.host}:{args.http_port}/"
    print(f"Dashboard: {url}")
    print(f"Serial: {args.serial or 'auto'} @ {args.baud}")
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        worker.stop()
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
