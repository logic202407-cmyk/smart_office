"""
serial_reader.py - 串口线程读取 + JSON 解析 + 自动重连
==========================================================
功能：
  1. 后台线程读取串口数据（JSON 行协议）
  2. JSON 解析与字段校验
  3. 断线自动重连（指数退避）
  4. 解析错误容错（坏行丢弃）
  5. 信号槽通知状态变化

通信协议：
  ESP32 发送 JSON 行，格式：
  {"state":"SUSPECTED_PEEPING","target_state":2,"distance_cm":95,
   "moving_energy":12,"static_energy":58,"detect_distance_cm":300,
   "timestamp_ms":123456}
"""

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)


# ==================================================================
# 数据模型
# ==================================================================
class SensorData:
    """ESP32 上报的传感器数据"""

    def __init__(self, data: Optional[Dict[str, Any]] = None) -> None:
        # 状态字段（默认 NORMAL）
        self.state: str = "NORMAL"
        # 目标状态
        self.target_state: int = 0
        # 距离 (cm)
        self.distance_cm: float = 0.0
        # 运动能量
        self.moving_energy: float = 0.0
        # 静止能量
        self.static_energy: float = 0.0
        # 检测距离 (cm)
        self.detect_distance_cm: float = 0.0
        # 时间戳 (ms)
        self.timestamp_ms: int = 0

        if data:
            self.update(data)

    def update(self, data: Dict[str, Any]) -> None:
        """用字典数据更新字段"""
        self.state = str(data.get("state", self.state))
        self.target_state = int(data.get("target_state", self.target_state))
        self.distance_cm = float(data.get("distance_cm", self.distance_cm))
        self.moving_energy = float(data.get("moving_energy", self.moving_energy))
        self.static_energy = float(data.get("static_energy", self.static_energy))
        self.detect_distance_cm = float(data.get("detect_distance_cm", self.detect_distance_cm))
        self.timestamp_ms = int(data.get("timestamp_ms", self.timestamp_ms))

    def __repr__(self) -> str:
        return (
            f"SensorData(state={self.state}, dist={self.distance_cm:.0f}cm, "
            f"moving={self.moving_energy:.0f}, static={self.static_energy:.0f})"
        )


# 全部有效状态的列表
VALID_STATES = {
    "NORMAL",
    "HUMAN_DETECTED",
    "APPROACHING",
    "SUSPECTED_PEEPING",
    "PRIVACY_PROTECT",
    "ALARM",
}


# ==================================================================
# 串口解析器
# ==================================================================
class SerialReader:
    """
    串口读取器 - 在独立线程中循环读取、解析 JSON、自动重连。

    用法:
        reader = SerialReader(port="/dev/ttyUSB0", baudrate=115200,
                              on_data=lambda data: print(data.state))
        reader.start()
        ...
        reader.stop()
    """

    def __init__(
        self,
        port: str = "",
        baudrate: int = 115200,
        timeout: float = 0.5,
        reconnect_params: Optional[Dict[str, float]] = None,
        on_data: Optional[Callable[[SensorData], None]] = None,
        on_connection_change: Optional[Callable[[bool], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        参数:
            port: 串口端口（空字符串表示自动检测）
            baudrate: 波特率
            timeout: 串口读取超时
            reconnect_params: 重连参数 {min_delay, max_delay, backoff}
            on_data: 收到有效数据时的回调
            on_connection_change: 连接状态变化回调 (connected: bool)
            on_error: 错误回调
        """
        self._port: str = port
        self._baudrate: int = baudrate
        self._timeout: float = timeout

        # 重连参数
        params = reconnect_params or {}
        self._reconnect_min: float = params.get("min_delay", 1.0)
        self._reconnect_max: float = params.get("max_delay", 60.0)
        self._reconnect_backoff: float = params.get("backoff", 2.0)

        # 回调
        self.on_data: Optional[Callable[[SensorData], None]] = on_data
        self.on_connection_change: Optional[Callable[[bool], None]] = on_connection_change
        self.on_error: Optional[Callable[[str], None]] = on_error

        # 内部状态
        self._serial: Optional[serial.Serial] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connected: bool = False
        self._lock = threading.Lock()

        # 最近的传感器数据
        self._last_data: Optional[SensorData] = None
        self._read_buffer: str = ""

        logger.info(
            f"SerialReader 初始化: port={self._port or '(auto)'}, "
            f"baudrate={baudrate}"
        )

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_data(self) -> Optional[SensorData]:
        return self._last_data

    def start(self) -> None:
        """启动串口读取线程"""
        if self._thread and self._thread.is_alive():
            logger.warning("SerialReader 已经在运行")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="SerialReader")
        self._thread.start()
        logger.info("SerialReader 线程已启动")

    def stop(self) -> None:
        """停止串口读取线程"""
        logger.info("正在停止 SerialReader...")
        self._stop_event.set()
        self._close_serial()
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("SerialReader 已停止")

    def send_command(self, command: str) -> bool:
        """向串口发送命令"""
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    cmd = (command + "\n").encode("utf-8")
                    self._serial.write(cmd)
                    logger.debug(f"发送命令: {command}")
                    return True
                except Exception as e:
                    logger.error(f"发送命令失败: {e}")
        return False

    # ------------------------------------------------------------------
    # 内部方法 - 主循环
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """主循环：连接 -> 读取 -> 重连"""
        while not self._stop_event.is_set():
            try:
                self._connect_and_read()
            except Exception as e:
                logger.error(f"读取循环异常: {e}")
                self._set_connected(False)
                self._reconnect_delay()
        self._close_serial()

    def _connect_and_read(self) -> None:
        """连接串口并持续读取"""
        if not self._open_serial():
            self._reconnect_delay()
            return

        self._set_connected(True)
        logger.info("串口已连接，开始读取数据")

        self._read_buffer = ""
        while not self._stop_event.is_set():
            try:
                if not self._serial or not self._serial.is_open:
                    break
                # 读取一行（串口数据以换行符分隔）
                raw = self._serial.readline()
                if not raw:
                    continue  # 超时无数据
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    self._parse_line(line)
            except serial.SerialException as e:
                logger.warning(f"串口读取异常: {e}")
                break
            except Exception as e:
                logger.error(f"数据解析异常: {e}")
                continue

        self._close_serial()
        self._set_connected(False)

    def _parse_line(self, line: str) -> None:
        """解析一行 JSON 数据"""
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                return

            # 校验 state 字段
            state = data.get("state", "")
            if state not in VALID_STATES:
                logger.debug(f"忽略无效状态: {state}")
                return

            sensor_data = SensorData(data)
            self._last_data = sensor_data

            # 通知回调
            if self.on_data:
                self.on_data(sensor_data)

        except json.JSONDecodeError:
            logger.debug(f"JSON 解析失败 (行将被忽略): {line[:80]}...")
        except Exception as e:
            logger.warning(f"数据解析异常: {e}")

    # ------------------------------------------------------------------
    # 串口操作
    # ------------------------------------------------------------------

    def _open_serial(self) -> bool:
        """打开串口（支持自动检测端口）"""
        port = self._port or self._auto_detect_port()
        if not port:
            logger.debug("未找到可用串口")
            return False

        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=self._baudrate,
                timeout=self._timeout,
                write_timeout=1,
            )
            logger.info(f"串口已打开: {port} @ {self._baudrate}")
            return True
        except serial.SerialException as e:
            logger.debug(f"打开串口失败 {port}: {e}")
            self._serial = None
            return False

    def _close_serial(self) -> None:
        """关闭串口"""
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                    logger.info("串口已关闭")
                except Exception as e:
                    logger.warning(f"关闭串口异常: {e}")
            self._serial = None

    def _set_connected(self, connected: bool) -> None:
        """更新连接状态并触发回调"""
        if self._connected != connected:
            self._connected = connected
            logger.info(f"连接状态: {'已连接' if connected else '已断开'}")
            if self.on_connection_change:
                self.on_connection_change(connected)

    # ------------------------------------------------------------------
    # 自动检测 & 重连
    # ------------------------------------------------------------------

    def _auto_detect_port(self) -> Optional[str]:
        """自动检测 ESP32 串口"""
        try:
            ports = list(serial.tools.list_ports.comports())
            for p in ports:
                desc = (p.description or "").lower()
                # ESP32 通常显示为 USB-SERIAL CH340 / CP210x / Silicon Labs
                if any(kw in desc for kw in ("ch34", "cp210", "silicon", "usb serial", "uart")):
                    logger.info(f"自动检测到串口: {p.device} ({p.description})")
                    return p.device
            # fallback: 返回第一个可用的 USB 串口
            for p in ports:
                if "usb" in (p.description or "").lower():
                    logger.info(f"自动检测到 USB 串口: {p.device}")
                    return p.device
        except Exception as e:
            logger.warning(f"自动检测串口失败: {e}")
        return None

    def _reconnect_delay(self) -> None:
        """指数退避等待重连"""
        delay = self._reconnect_min
        while not self._stop_event.is_set():
            logger.debug(f"等待 {delay:.1f}s 后重连...")
            if self._stop_event.wait(delay):
                return
            # 尝试连接
            if self._open_serial():
                return
            # 指数退避
            delay = min(delay * self._reconnect_backoff, self._reconnect_max)
