"""
serial_simulator.py — PC端测试串口模拟器
===========================================

功能：
  1. 创建虚拟串口对（模拟 ESP32 发送 JSON 行）
  2. 可配置场景序列，自动循环发送
  3. 模拟6种状态循环（NORMAL → HUMAN_DETECTED → APPROACHING
     → SUSPECTED_PEEPING → PRIVACY_PROTECT → ALARM）
  4. 支持自定义场景脚本
  5. 支持距离渐变、能量变化等动态行为

用法：
    # 启动模拟器，使用虚拟串口
    python serial_simulator.py --port /dev/ttyV0 --baud 115200

    # 使用默认场景序列（6状态循环）
    python serial_simulator.py

    # 使用自定义场景文件
    python serial_simulator.py --scenario my_scenario.json

    # 查看可用的虚拟串口
    python serial_simulator.py --list

依赖：
    pip install pyserial

注意：
    在 Linux 上需要 socat 或 tty0tty 创建虚拟串口。
    或使用 pty 模式自动创建伪终端对。
"""

import argparse
import json
import logging
import os
import random
import signal
import subprocess
import sys
import time
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SerialSimulator")


# ============================================================
# 场景定义
# ============================================================

@dataclass
class StateEntry:
    """场景中的一个状态条目"""
    state: str                          # 状态名
    target_state: int = 1               # 目标类型 (0=无, 1=运动, 2=静止, 3=运动+静止)
    distance_cm: int = 200              # 目标距离 (cm)
    moving_energy: int = 30             # 运动能量
    static_energy: int = 0              # 静止能量
    detect_distance_cm: int = 600       # 探测距离
    duration_ms: int = 1000             # 该状态的持续时间 (ms)
    transition: Optional[str] = None    # 可选: 下一状态名 (None=按顺序)


@dataclass
class Scenario:
    """场景：一系列状态条目"""
    name: str = "默认6状态循环"
    entries: List[StateEntry] = field(default_factory=list)
    loop: bool = True                   # 是否循环
    interval_ms: int = 100              # 发送间隔 (ms)

    def get_default_scenario() -> 'Scenario':
        """创建默认的6状态循环场景"""
        return Scenario(
            name="6状态循环",
            entries=[
                StateEntry("NORMAL",            0, 0,   0, 0,   600, 3000),
                StateEntry("HUMAN_DETECTED",    1, 200, 30, 0,  600, 3000),
                StateEntry("APPROACHING",       1, 120, 45, 0,  400, 3000),
                StateEntry("SUSPECTED_PEEPING", 3, 65,  20, 50, 300, 3000),
                StateEntry("PRIVACY_PROTECT",   3, 45,  15, 70, 200, 3000),
                StateEntry("ALARM",             1, 30,  60, 0,  200, 3000),
            ],
            loop=True,
            interval_ms=200,
        )

    def get_gradual_approach_scenario() -> 'Scenario':
        """创建渐进靠近模拟场景"""
        entries = []
        # 从远到近逐步靠近
        distances = [400, 350, 300, 250, 200, 180, 160, 140, 120, 100,
                     90, 80, 70, 60, 50, 40, 30, 25]
        states = (["NORMAL"] * 3 + ["HUMAN_DETECTED"] * 5 +
                  ["APPROACHING"] * 3 + ["SUSPECTED_PEEPING"] * 3 +
                  ["PRIVACY_PROTECT"] * 2 + ["ALARM"] * 2)

        for i, (state, dist) in enumerate(zip(states, distances)):
            entries.append(StateEntry(
                state=state,
                target_state=1 if state != "NORMAL" else 0,
                distance_cm=dist,
                moving_energy=max(10, 70 - dist // 5),
                static_energy=0,
                detect_distance_cm=600,
                duration_ms=1000,
            ))

        return Scenario(name="渐进靠近", entries=entries, loop=True, interval_ms=200)

    def get_random_walk_scenario() -> 'Scenario':
        """创建随机行走模拟场景"""
        entries = []
        all_states = ["NORMAL", "HUMAN_DETECTED", "APPROACHING",
                      "SUSPECTED_PEEPING", "PRIVACY_PROTECT", "ALARM"]
        current_state = "NORMAL"
        for i in range(50):
            # 随机走动：50% 保持，50% 切换相邻状态
            if random.random() < 0.5:
                idx = all_states.index(current_state)
                delta = random.choice([-1, 0, 1])
                if delta == 0:
                    pass  # 保持
                else:
                    new_idx = max(0, min(len(all_states) - 1, idx + delta))
                    current_state = all_states[new_idx]

            dist = random.randint(20, 400)
            entries.append(StateEntry(
                state=current_state,
                target_state=0 if current_state == "NORMAL" else random.choice([1, 2, 3]),
                distance_cm=dist,
                moving_energy=random.randint(0, 80),
                static_energy=random.randint(0, 50),
                detect_distance_cm=600,
                duration_ms=random.randint(500, 3000),
            ))

        return Scenario(name="随机行走", entries=entries, loop=True, interval_ms=300)

    def get_static_person_scenario() -> 'Scenario':
        """创建静止人体模拟场景（模拟有人坐着不动）"""
        return Scenario(
            name="静止人体",
            entries=[
                StateEntry("NORMAL",            0, 0,   0, 0,  600, 2000),
                StateEntry("HUMAN_DETECTED",    2, 100, 0, 60, 600, 5000),
                StateEntry("APPROACHING",       2, 60,  0, 55, 300, 5000),
                StateEntry("SUSPECTED_PEEPING", 2, 40,  0, 70, 200, 4000),
                StateEntry("PRIVACY_PROTECT",   2, 30,  0, 80, 200, 4000),
                StateEntry("ALARM",             2, 20,  0, 90, 200, 5000),
            ],
            loop=True,
            interval_ms=200,
        )

    def to_dict(self) -> dict:
        """序列化为字典（可用于 JSON 保存）"""
        return {
            "name": self.name,
            "loop": self.loop,
            "interval_ms": self.interval_ms,
            "entries": [
                {
                    "state": e.state,
                    "target_state": e.target_state,
                    "distance_cm": e.distance_cm,
                    "moving_energy": e.moving_energy,
                    "static_energy": e.static_energy,
                    "detect_distance_cm": e.detect_distance_cm,
                    "duration_ms": e.duration_ms,
                }
                for e in self.entries
            ],
        }

    @staticmethod
    def from_dict(data: dict) -> 'Scenario':
        """从字典恢复场景"""
        entries = [
            StateEntry(
                state=e["state"],
                target_state=e.get("target_state", 0),
                distance_cm=e.get("distance_cm", 0),
                moving_energy=e.get("moving_energy", 0),
                static_energy=e.get("static_energy", 0),
                detect_distance_cm=e.get("detect_distance_cm", 600),
                duration_ms=e.get("duration_ms", 1000),
            )
            for e in data.get("entries", [])
        ]
        return Scenario(
            name=data.get("name", "自定义场景"),
            entries=entries,
            loop=data.get("loop", True),
            interval_ms=data.get("interval_ms", 200),
        )

    def save_json(self, path: str):
        """保存场景到 JSON 文件"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"场景已保存到 {path}")

    @staticmethod
    def load_json(path: str) -> 'Scenario':
        """从 JSON 文件加载场景"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return Scenario.from_dict(data)


# ============================================================
# JSON 行生成器
# ============================================================

def build_json_line(entry: StateEntry, timestamp_ms: int) -> str:
    """
    根据状态条目和时间戳构建 JSON 行。

    格式（与 firmware/privacy_state_machine.cpp getStateJSON 一致）:
        {"state":"APPROACHING","target_state":1,"distance_cm":120,
         "moving_energy":45,"static_energy":0,"detect_distance_cm":200,
         "timestamp_ms":12345}
    """
    data = {
        "state": entry.state,
        "target_state": entry.target_state,
        "distance_cm": entry.distance_cm,
        "moving_energy": entry.moving_energy,
        "static_energy": entry.static_energy,
        "detect_distance_cm": entry.detect_distance_cm,
        "timestamp_ms": timestamp_ms,
    }
    return json.dumps(data, ensure_ascii=False) + "\n"


# ============================================================
# 串口模拟器
# ============================================================

class SerialSimulator:
    """
    串口模拟器 — 向虚拟串口发送 JSON 行。

    启动方式：
        1. 自动模式：使用 socat 创建虚拟串口对
        2. 手动模式：连接到已有的虚拟串口
        3. 文件模式：写入文件（供测试读取）
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 115200,
        scenario: Optional[Scenario] = None,
        write_to_file: Optional[str] = None,
    ):
        """
        初始化串口模拟器。

        参数:
            port: 串口设备路径（None=自动创建虚拟串口）
            baudrate: 波特率
            scenario: 场景定义（None=默认6状态循环）
            write_to_file: 写入文件路径（替代串口）
        """
        self.port = port
        self.baudrate = baudrate
        self.scenario = scenario or Scenario.get_default_scenario()
        self.write_to_file = write_to_file

        self._serial = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # socat 子进程（自动创建虚拟串口）
        self._socat_proc: Optional[subprocess.Popen] = None

        # 统计
        self.lines_sent = 0
        self.cycles_completed = 0
        self.current_entry_idx = 0
        self.start_time = 0

        # 回调
        self.on_send: Optional[Callable[[str], None]] = None

        # 用于模拟距离渐变
        self._distance_jitter = False

    def enable_distance_jitter(self, max_jitter_cm: int = 10):
        """启用距离抖动模拟（更真实的传感器数据）"""
        self._distance_jitter = True
        self._jitter_range = max_jitter_cm

    # ------------------------------------------------------------------
    # 启动/停止
    # ------------------------------------------------------------------

    def start(self):
        """启动模拟器"""
        if self._running:
            logger.warning("模拟器已在运行")
            return

        self._running = True
        self._stop_event.clear()
        self.lines_sent = 0
        self.cycles_completed = 0
        self.current_entry_idx = 0
        self.start_time = time.time()

        if self.write_to_file:
            # 文件模式
            self._thread = threading.Thread(target=self._run_file, daemon=True)
        else:
            # 串口模式
            self._open_serial()
            if self._serial:
                self._thread = threading.Thread(target=self._run_serial, daemon=True)
            else:
                logger.error("无法打开串口，模拟器启动失败")
                self._running = False
                return

        self._thread.start()
        logger.info(f"串口模拟器已启动: {self.port or self.write_to_file}")
        self._print_scenario_info()

    def stop(self):
        """停止模拟器"""
        logger.info("正在停止模拟器...")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

        self._close_serial()
        self._kill_socat()
        self._running = False

        duration = time.time() - self.start_time
        logger.info(
            f"模拟器已停止 | 发送 {self.lines_sent} 行 | "
            f"运行 {duration:.1f}s | 循环 {self.cycles_completed} 次"
        )

    def _print_scenario_info(self):
        """打印场景信息"""
        logger.info(f"场景: {self.scenario.name}")
        logger.info(f"状态条目: {len(self.scenario.entries)}")
        logger.info(f"循环: {'是' if self.scenario.loop else '否'}")
        logger.info(f"发送间隔: {self.scenario.interval_ms}ms")
        entry_names = [f"{e.state}({e.distance_cm}cm)" for e in self.scenario.entries]
        logger.info(f"顺序: {' → '.join(entry_names)}")

    # ------------------------------------------------------------------
    # 串口操作
    # ------------------------------------------------------------------

    def _open_serial(self):
        """打开串口（自动创建如果需要）"""
        import serial

        if self.port and os.path.exists(self.port):
            logger.info(f"连接到已有串口: {self.port}")
        elif self.port is None:
            self.port = self._create_virtual_port()

        if not self.port:
            logger.error("无法确定串口路径")
            return

        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.1,
                write_timeout=0.1,
            )
            logger.info(f"串口已打开: {self.port} @ {self.baudrate}")
        except Exception as e:
            logger.error(f"打开串口失败: {e}")
            self._serial = None

    def _close_serial(self):
        """关闭串口"""
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
                logger.info("串口已关闭")
            except Exception as e:
                logger.warning(f"关闭串口异常: {e}")
        self._serial = None

    def _create_virtual_port(self) -> Optional[str]:
        """
        使用 socat 创建虚拟串口对。
        返回模拟器端使用的端口。
        """
        try:
            # 创建一对虚拟串口
            result = subprocess.run(
                ["socat", "-d", "-d", "PTY,link=/tmp/ttySim,raw,echo=0",
                 "PTY,link=/tmp/ttyApp,raw,echo=0"],
                capture_output=True, text=True, timeout=5,
            )
            # 检查 socat 是否在后台运行
            self._socat_proc = subprocess.Popen(
                ["socat", "-d", "-d", "PTY,link=/tmp/ttySim,raw,echo=0",
                 "PTY,link=/tmp/ttyApp,raw,echo=0"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(1)  # 等待 socat 创建端口

            if os.path.exists("/tmp/ttySim"):
                logger.info(f"已创建虚拟串口: /tmp/ttySim (模拟器端)")
                logger.info(f"应用程序连接: /tmp/ttyApp")
                return "/tmp/ttySim"
        except FileNotFoundError:
            logger.warning("socat 未安装，请手动创建虚拟串口或使用文件模式")
            logger.warning("安装: apt install socat 或 brew install socat")
        except Exception as e:
            logger.warning(f"创建虚拟串口失败: {e}")

        return None

    def _kill_socat(self):
        """终止 socat 进程"""
        if self._socat_proc:
            try:
                self._socat_proc.terminate()
                self._socat_proc.wait(timeout=3)
                logger.info("socat 进程已终止")
            except Exception as e:
                logger.warning(f"终止 socat 异常: {e}")
            self._socat_proc = None

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def _run_serial(self):
        """串口发送主循环"""
        while not self._stop_event.is_set():
            for entry in self._get_entry_sequence():
                if self._stop_event.is_set():
                    break

                # 发送该条目持续指定时间
                self._send_entry_duration(entry)

                self.current_entry_idx = (self.current_entry_idx + 1) % len(self.scenario.entries)
                if self.current_entry_idx == 0:
                    self.cycles_completed += 1

    def _run_file(self):
        """文件写入模式"""
        import serial

        try:
            with open(self.write_to_file, 'w', encoding='utf-8') as f:
                while not self._stop_event.is_set():
                    for entry in self._get_entry_sequence():
                        if self._stop_event.is_set():
                            break

                        start = time.time()
                        duration_s = entry.duration_ms / 1000.0
                        while time.time() - start < duration_s:
                            if self._stop_event.is_set():
                                break
                            line = build_json_line(
                                entry, int(time.time() * 1000))
                            f.write(line)
                            f.flush()
                            self.lines_sent += 1
                            time.sleep(self.scenario.interval_ms / 1000.0)

                        self.current_entry_idx = (
                            (self.current_entry_idx + 1) % len(self.scenario.entries)
                        )
                        if self.current_entry_idx == 0:
                            self.cycles_completed += 1
        except Exception as e:
            logger.error(f"文件写入异常: {e}")

    def _get_entry_sequence(self):
        """获取场景条目序列（支持循环）"""
        while True:
            for entry in self.scenario.entries:
                yield entry
            if not self.scenario.loop:
                break
            # 循环结束后等待再继续
            if self._stop_event.is_set():
                break

    def _send_entry_duration(self, entry: StateEntry):
        """在指定持续时间内重复发送当前状态"""
        start = time.time()
        duration_s = entry.duration_ms / 1000.0
        interval_s = self.scenario.interval_ms / 1000.0

        while time.time() - start < duration_s:
            if self._stop_event.is_set():
                return

            # 构建 JSON 行
            now_ms = int(time.time() * 1000)
            line = build_json_line(entry, now_ms)

            # 发送
            if self._serial and self._serial.is_open:
                try:
                    self._serial.write(line.encode('utf-8'))
                    self.lines_sent += 1
                except Exception as e:
                    logger.warning(f"串口写入异常: {e}")
                    return

            # 回调
            if self.on_send:
                self.on_send(line.strip())

            time.sleep(interval_s)

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """获取运行状态"""
        elapsed = time.time() - self.start_time if self.start_time else 0
        return {
            "running": self._running,
            "port": self.port or self.write_to_file,
            "scenario": self.scenario.name,
            "lines_sent": self.lines_sent,
            "cycles": self.cycles_completed,
            "current_entry": self.current_entry_idx,
            "elapsed_s": elapsed,
            "entries": len(self.scenario.entries),
        }


# ============================================================
# 预定义的预设场景
# ============================================================

PRESET_SCENARIOS = {
    "6states": Scenario.get_default_scenario(),
    "approach": Scenario.get_gradual_approach_scenario(),
    "random": Scenario.get_random_walk_scenario(),
    "static": Scenario.get_static_person_scenario(),
}


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="ESP32 串口模拟器 — 模拟发送 JSON 状态行到虚拟串口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
    # 默认 6 状态循环
    python serial_simulator.py

    # 使用预设场景
    python serial_simulator.py --preset approach
    python serial_simulator.py --preset random

    # 连接已有虚拟串口
    python serial_simulator.py --port /dev/ttyUSB0

    # 保存场景到文件
    python serial_simulator.py --save-scenario my_scenario.json

    # 从场景文件加载
    python serial_simulator.py --load-scenario my_scenario.json

    # 写入文件模式（供测试读取）
    python serial_simulator.py --output-file simulated_data.jsonl

预设场景:
    6states  - 6状态循环（默认）
    approach - 渐进靠近
    random   - 随机行走
    static   - 静止人体
        """,
    )

    parser.add_argument(
        "--port", "-p",
        help="串口设备路径（默认自动创建虚拟串口）",
    )
    parser.add_argument(
        "--baud", "-b", type=int, default=115200,
        help="波特率 (默认: 115200)",
    )
    parser.add_argument(
        "--preset", choices=list(PRESET_SCENARIOS.keys()), default="6states",
        help="预设场景 (默认: 6states)",
    )
    parser.add_argument(
        "--load-scenario",
        help="从 JSON 文件加载场景",
    )
    parser.add_argument(
        "--save-scenario",
        help="保存当前场景到 JSON 文件",
    )
    parser.add_argument(
        "--output-file", "-o",
        help="写入文件模式（写入此文件替代串口）",
    )
    parser.add_argument(
        "--interval", type=int,
        help="发送间隔 (ms，覆盖场景配置)",
    )
    parser.add_argument(
        "--jitter", type=int, default=0,
        help="距离抖动 (cm，模拟真实传感器波动)",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="列出可用的预设场景",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="只运行一轮（不循环）",
    )

    args = parser.parse_args()

    # 列出预设场景
    if args.list:
        print("可用的预设场景:")
        for name, sc in PRESET_SCENARIOS.items():
            entries = " → ".join(f"{e.state}({e.distance_cm}cm)" for e in sc.entries)
            print(f"  {name:12s} - {sc.name}: {entries}")
        return

    # 加载场景
    if args.load_scenario:
        scenario = Scenario.load_json(args.load_scenario)
        logger.info(f"已加载场景文件: {args.load_scenario}")
    else:
        scenario = PRESET_SCENARIOS[args.preset]

    if args.interval:
        scenario.interval_ms = args.interval

    if args.once:
        scenario.loop = False

    # 保存场景
    if args.save_scenario:
        scenario.save_json(args.save_scenario)
        return

    # 创建模拟器
    sim = SerialSimulator(
        port=args.port,
        baudrate=args.baud,
        scenario=scenario,
        write_to_file=args.output_file,
    )

    if args.jitter > 0:
        sim.enable_distance_jitter(args.jitter)

    # 信号处理（Ctrl+C 优雅退出）
    def signal_handler(sig, frame):
        logger.info("收到终止信号")
        sim.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 启动
    sim.start()

    # 状态报告循环
    try:
        while sim._running:
            time.sleep(5)
            status = sim.get_status()
            log_msg = (
                f"[状态] 已发 {status['lines_sent']} 行 | "
                f"循环 {status['cycles']} 次 | "
                f"已运行 {status['elapsed_s']:.0f}s"
            )
            logger.info(log_msg)
    except KeyboardInterrupt:
        pass
    finally:
        sim.stop()


if __name__ == "__main__":
    main()
