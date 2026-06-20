# PC 端隐私保护程序设计方案

> **项目**：SmartOffice PeepPrevention — 办公防偷窥雷达系统  
> **模块**：PC 上位机客户端（Privacy Shield Client）  
> **技术栈**：Python 3.10+ / pyserial / PyQt6  
> **生成日期**：2026-05-08  
> **文档版本**：v1.0

---

## 目录

1. [Python 技术栈选型](#1-python-技术栈选型)
2. [串口读取实现方案（JSON 行解析）](#2-串口读取实现方案json-行解析)
3. [屏幕遮罩 UI 设计](#3-屏幕遮罩-ui-设计)
4. [系统锁屏触发](#4-系统锁屏触发)
5. [macOS/Linux 跨平台兼容方案](#5-macoslinux-跨平台兼容方案)
6. [状态响应映射表](#6-状态响应映射表)
7. [配置参数设计](#7-配置参数设计)
8. [托盘图标 / 后台运行设计](#8-托盘图标--后台运行设计)
9. [错误重连机制](#9-错误重连机制)
10. [测试调试方案](#10-测试调试方案)

---

## 1. Python 技术栈选型

### 1.1 核心选型表

| 模块 | 技术 | 版本要求 | 说明 |
|------|------|---------|------|
| **运行环境** | Python | ≥ 3.10 | f-string 增强、`match` 语句便利 |
| **串口通信** | **pyserial** | ≥ 3.5 | 跨平台串口库，支持事件驱动的 read 线程 |
| **GUI 框架** | **PyQt6** | ≥ 6.5 | Qt6 绑定，原生支持透明窗口、托盘图标、多屏 |
| **JSON 解析** | 标准库 `json` | — | 轻量、可靠，不引入第三方 JSON 库 |
| **日志** | 标准库 `logging` | — | 按天轮转、ERROR 级别直接弹窗 |
| **打包分发** | **Nuitka** / PyInstaller | — | 单文件 exe 或 macOS .app 发布 |

### 1.2 为什么选择 PyQt6 而非 tkinter

| 对比项 | PyQt6 | tkinter |
|--------|-------|---------|
| 全屏透明遮罩 | ✅ `Qt.WA_TranslucentBackground` + `Qt.WindowStaysOnTopHint` | ⚠️ 需 `attributes('-transparentcolor')` 变通，抖动频繁 |
| 多屏支持 | ✅ 原生 `QScreen` API，可获取每块屏幕几何 | ❌ 需手动遍历 `winfo_screen*`，多屏兼容差 |
| 托盘图标 | ✅ `QSystemTrayIcon` 开箱即用 | ❌ 需 `pystray` 第三方库 |
| 动画/渐变 | ✅ `QPropertyAnimation` 原生支持 | ❌ 需手动计时器实现 |
| 富文本/HTML | ✅ `QLabel` 支持简单 HTML | ❌ 仅支持纯文本 |
| 系统集成 | ✅ Windows/macOS/Linux 平台行为一致 | ⚠️ Linux 下 tray 支持不统一 |
| 包大小 | ~80MB（编译后） | ~15MB（含 Python 解释器） |

> **结论**：隐私保护场景要求实时、稳定、跨平台的全屏遮罩+托盘图标，**PyQt6 是唯一能满足所有需求的选择**。若设备资源极度受限（如老旧 PC），可降级为 tkinter + pystray 方案，但需接受多屏和动画缺陷。

### 1.3 PyQt6 vs PySide6

| 对比项 | PyQt6 | PySide6 |
|--------|-------|---------|
| 授权 | GPL / 商业授权（Riverbank） | LGPL（Qt 官方） |
| API 一致性 | 略低（部分方法名不同） | 与 Qt 官方 C++ API 一致 |
| 社区活跃度 | 高 | 高 |
| 打包兼容性 | 较好 | 较好 |

**推荐 PyQt6**：本项目为内部工具无需商业授权顾虑，PyQt6 在托盘消息、Windows 锁屏回调方面集成更成熟。

---

## 2. 串口读取实现方案（JSON 行解析）

### 2.1 通信物理层

| 参数 | 值 |
|------|-----|
| 接口 | USB CDC（虚拟串口） |
| 默认波特率 | **256000**（与 LD2410B 雷达相同） |
| 数据位 | 8 |
| 校验位 | None |
| 停止位 | 1 |
| 编码 | UTF-8 |
| 消息分隔 | 换行符 `\n`（0x0A） |

> **注意**：USB CDC 的波特率在 USB 协议层面实际无效（由 USB 速率决定），但 `pyserial` 需要设置一个值以完成 `open()`。建议默认 256000，可在配置中调整。

### 2.2 协议格式（JSON 行）

ESP32 每行输出一个 JSON 对象，以 `\n` 结尾，PC 按行读取解析。

**上行状态上报示例**：
```json
{"type":"state_report","timestamp_ms":1234567,"data":{"state":"APPROACHING","target_state":2,"distance_cm":95,"moving_energy":12,"static_energy":58,"detect_distance_cm":300,"uptime_ms":1234567}}
```

**上行事件通知示例**：
```json
{"type":"event","timestamp_ms":1234567,"data":{"event":"gesture_detected","detail":"UP"}}
```

**简版格式（兼容旧固件）** ：
```json
{"state":"SUSPECTED_PEEPING","target_state":2,"distance_cm":95,"moving_energy":12,"static_energy":58,"detect_distance_cm":300,"timestamp_ms":123456}
```

### 2.3 串口读取引擎实现

```python
# serial_reader.py — 核心串口读取引擎
import serial
import serial.tools.list_ports
import json
import threading
import queue
import time
import logging

logger = logging.getLogger(__name__)


class SerialReader:
    """串口读取器：后台线程读取 → JSON 解析 → 回调/队列分发"""

    def __init__(self, config: dict, callback=None):
        self.port = config.get("port", "auto")       # "auto" 自动检测
        self.baudrate = config.get("baudrate", 256000)
        self.timeout = config.get("timeout", 0.1)     # 100ms 读取超时
        self.callback = callback                      # on_message(json_dict)
        self._running = False
        self._thread = None
        self._serial = None
        self._line_buffer = b""
        self.error_queue = queue.Queue()              # 错误信息队列

    # ── 自动检测串口 ──
    @staticmethod
    def auto_detect_port():
        """自动扫描可用串口，返回第一个 CDC 设备或含 'USB' 的端口名"""
        ports = serial.tools.list_ports.comports()
        for p in sorted(ports):
            # 优先匹配 USB CDC / CP210x / CH340 / FTDI
            if any(kw in (p.description or "").lower() or kw in (p.hwid or "").lower()
                   for kw in ["usb", "cdc", "cp210", "ch340", "ftdi", "arduino"]):
                return p.device
        # 退回到第一个可用串口
        if ports:
            return ports[0].device
        return None

    # ── 启动 ──
    def start(self):
        if self._running:
            return
        # 自动检测端口
        if self.port == "auto":
            detected = self.auto_detect_port()
            if not detected:
                raise RuntimeError("未检测到串口设备，请检查 USB 连接")
            self.port = detected
            logger.info(f"自动检测到串口: {self.port}")

        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
        )
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info(f"串口已打开: {self.port} @ {self.baudrate} baud")

    # ── 后台读取循环 ──
    def _read_loop(self):
        while self._running:
            try:
                data = self._serial.read(1024)
                if not data:
                    continue
                self._line_buffer += data
                # 按 \n 拆分
                while b"\n" in self._line_buffer:
                    line, self._line_buffer = self._line_buffer.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    self._parse_line(line)
            except serial.SerialException as e:
                logger.error(f"串口异常: {e}")
                self.error_queue.put({"type": "serial_error", "msg": str(e)})
                self._reconnect()          # 尝试重连
                break
            except Exception as e:
                logger.exception(f"读取线程异常: {e}")

    # ── JSON 行解析 ──
    def _parse_line(self, line: bytes):
        try:
            msg = json.loads(line.decode("utf-8"))
            # 标准化消息格式
            # 若只有顶层 state 字段（简版格式），包装为统一结构
            if "state" in msg and "type" not in msg:
                normalized = {
                    "type": "state_report",
                    "timestamp_ms": msg.get("timestamp_ms", 0),
                    "data": {
                        "state": msg["state"],
                        "target_state": msg.get("target_state", 0),
                        "distance_cm": msg.get("distance_cm", 0),
                        "moving_energy": msg.get("moving_energy", 0),
                        "static_energy": msg.get("static_energy", 0),
                        "detect_distance_cm": msg.get("detect_distance_cm", 0),
                        "uptime_ms": msg.get("uptime_ms", 0),
                    }
                }
                msg = normalized
            # 分发
            if self.callback:
                self.callback(msg)
        except json.JSONDecodeError:
            logger.warning(f"JSON 解析失败: {line[:200]}")

    # ── 停止 ──
    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("串口已关闭")

    # ── 重连（内部调用） ──
    def _reconnect(self):
        self.stop()
        time.sleep(2)
        logger.info("尝试重连串口...")
        try:
            self.start()
        except Exception as e:
            logger.error(f"重连失败: {e}")
            self.error_queue.put({"type": "reconnect_failed", "msg": str(e)})
```

### 2.4 模块架构图

```
┌──────────────────────────────────────────────────────────────┐
│                    SerialReader Thread                        │
│                                                              │
│  serial.read(1024)                                           │
│       │                                                      │
│       ▼                                                      │
│  line_buffer += data                                         │
│       │                                                      │
│       ▼ (split by \n)                                        │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐               │
│  │ Line 1    │  │ Line 2    │  │ Line 3    │  ...           │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘               │
│        │              │              │                       │
│        ▼              ▼              ▼                       │
│  json.loads() → dict                                         │
│        │                                                      │
│        ▼                                                      │
│  callback(normalized_msg)  ──→  App Main Thread (信号/槽)    │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 屏幕遮罩 UI 设计

### 3.1 遮罩层次结构

```
┌────────────────────────────────────────────────────────────────┐
│  【桌面 / 应用窗口】                                            │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  【全屏半透明遮罩 — QWidget】                             │  │
│  │  • Qt.WindowStaysOnTopHint（置顶）                        │  │
│  │  • Qt.FramelessWindowHint（无边框）                       │  │
│  │  • Qt.WA_TranslucentBackground（透明背景）                 │  │
│  │  • setWindowOpacity(opacity) 控制整体透明度                 │  │
│  │  • setGeometry → 覆盖所有屏幕（多屏扩展模式）               │  │
│  │  ┌──────────────────────────────────────────────────┐    │  │
│  │  │  【中央警告面板 — QFrame】                         │    │  │
│  │  │  • 状态图标（⚠️/🔒/🚨 等 Emoji 或 SVG 图标）      │    │  │
│  │  │  • 大号警告文字（如 "检测到异常接近！"）             │    │  │
│  │  │  • 实时状态信息（距离、能量值）                     │    │  │
│  │  │  • 倒计时进度条（进入隐私保护/锁屏倒计时）           │    │  │
│  │  │  • 「解锁」按钮（输入密码 / Ctrl+Alt+Del 确认身份）  │    │  │
│  │  └──────────────────────────────────────────────────┘    │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### 3.2 不同状态下的遮罩参数

| 状态 | 遮罩不透明度 | 显示内容 | 交互 |
|------|-------------|---------|------|
| **NORMAL** | 0%（无遮罩） | — | 正常操作 |
| **HUMAN_DETECTED** | 0%（无遮罩） | 托盘图标变色（黄） | 正常操作 |
| **APPROACHING** | **40%** | 半透明遮罩 + 小字提示 | 鼠标可穿透（`setAttribute(Qt.WA_TransparentForMouseEvents)`） |
| **SUSPECTED_PEEPING** | **60%** | 遮罩 + 弹窗警告 + 距离显示 | 弹窗可关闭 |
| **PRIVACY_PROTECT** | **80%** | 深度遮罩 + 大号警告 + 解锁按钮 | 解锁需输入密码 |
| **ALARM** | **90%** | 最深遮罩 + 闪烁红色文字 + 锁屏倒计时 | 自动锁屏 |

### 3.3 PyQt6 遮罩窗口实现

```python
# overlay.py — 全屏遮罩窗口
import sys
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QFrame, QApplication, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon


class PrivacyOverlay(QWidget):
    """全屏隐私保护遮罩窗口"""

    unlock_requested = pyqtSignal()  # 用户请求解锁

    STATE_CONFIG = {
        "NORMAL":             {"opacity": 0.0,  "bg_color": (0, 0, 0),     "text": "",                "mouse_passthrough": True},
        "HUMAN_DETECTED":     {"opacity": 0.0,  "bg_color": (0, 0, 0),     "text": "",                "mouse_passthrough": True},
        "APPROACHING":        {"opacity": 0.4,  "bg_color": (0, 0, 0),     "text": "有人接近中…",     "mouse_passthrough": True},
        "SUSPECTED_PEEPING":  {"opacity": 0.6,  "bg_color": (0, 0, 0),     "text": "⚠ 检测到异常接近", "mouse_passthrough": False},
        "PRIVACY_PROTECT":    {"opacity": 0.8,  "bg_color": (0, 0, 0),     "text": "🔒 隐私保护已激活", "mouse_passthrough": False},
        "ALARM":              {"opacity": 0.9,  "bg_color": (180, 0, 0),   "text": "🚨 告警！即将锁屏", "mouse_passthrough": False},
    }

    def __init__(self, app: QApplication):
        super().__init__()
        self._app = app
        self._current_state = "NORMAL"
        self._alarm_countdown = 0          # 告警倒计时秒数
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._tick_countdown)

        # ── 窗口属性 ──
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool                    # 不在任务栏显示
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        # ── 覆盖所有屏幕 ──
        self._update_geometry()

        # ── UI 构建 ──
        self._build_ui()

        # 初始状态 = NORMAL → 隐藏
        self.set_state("NORMAL")

    def _update_geometry(self):
        """覆盖所有可用屏幕（多屏扩展模式）"""
        total_rect = None
        for screen in self._app.screens():
            geom = screen.geometry()
            if total_rect is None:
                total_rect = geom
            else:
                total_rect = total_rect.united(geom)
        if total_rect:
            self.setGeometry(total_rect)

    def _build_ui(self):
        """构建中央警告面板"""
        # 主布局
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 中央卡片
        self.card = QFrame(self)
        self.card.setObjectName("warning_card")
        self.card.setStyleSheet("""
            #warning_card {
                background-color: rgba(30, 30, 30, 200);
                border-radius: 16px;
                border: 2px solid rgba(255, 100, 100, 200);
                padding: 40px;
            }
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(20)

        # 状态图标
        self.icon_label = QLabel("🔒")
        self.icon_label.setFont(QFont("Segoe UI Emoji", 64))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.icon_label)

        # 警告标题
        self.title_label = QLabel("隐私保护已激活")
        self.title_label.setFont(QFont("Microsoft YaHei", 32, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: white;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.title_label)

        # 详细信息
        self.info_label = QLabel("距离: 45 cm  |  状态: 疑似偷窥")
        self.info_label.setFont(QFont("Microsoft YaHei", 16))
        self.info_label.setStyleSheet("color: rgba(255,255,255,200);")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.info_label)

        # 倒计时进度条（仅 ALARM 状态显示）
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(400)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                border-radius: 8px;
                background: #333;
                height: 20px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff4444, stop:1 #ff8800);
                border-radius: 7px;
            }
        """)
        self.progress_bar.hide()
        card_layout.addWidget(self.progress_bar)

        # 解锁按钮
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unlock_btn = QPushButton("🔓 解锁屏幕")
        self.unlock_btn.setFont(QFont("Microsoft YaHei", 18))
        self.unlock_btn.setFixedSize(220, 60)
        self.unlock_btn.setStyleSheet("""
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4CAF50, stop:1 #45a049);
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #66BB6A;
            }
            QPushButton:pressed {
                background-color: #388E3C;
            }
        """)
        self.unlock_btn.clicked.connect(self.unlock_requested.emit)
        btn_layout.addWidget(self.unlock_btn)
        card_layout.addLayout(btn_layout)

        layout.addWidget(self.card, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_state(self, state: str, distance_cm: int = 0, energy: int = 0):
        """切换遮罩状态"""
        self._current_state = state
        cfg = self.STATE_CONFIG.get(state, self.STATE_CONFIG["NORMAL"])

        # 透明度
        self.setWindowOpacity(cfg["opacity"])

        # 鼠标穿透
        if cfg["mouse_passthrough"]:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        # 背景色（ALARM 用红色）
        r, g, b = cfg["bg_color"]
        self.setStyleSheet(f"background-color: rgba({r},{g},{b},0);")

        # 显示/隐藏
        if state in ("NORMAL", "HUMAN_DETECTED"):
            self.hide()
            self._countdown_timer.stop()
        else:
            # 更新信息
            self.title_label.setText(cfg["text"])
            info_parts = []
            if distance_cm > 0:
                info_parts.append(f"距离: {distance_cm} cm")
            if energy > 0:
                info_parts.append(f"能量: {energy}")
            if info_parts:
                self.info_label.setText("  |  ".join(info_parts))
            else:
                self.info_label.setText("")

            # 倒计时处理
            if state == "ALARM":
                self._alarm_countdown = 8   # 8秒锁屏倒计时
                self.progress_bar.show()
                self.progress_bar.setValue(100)
            else:
                self._alarm_countdown = 0
                self.progress_bar.hide()
                self._countdown_timer.stop()

            self.show()
            self.raise_()
            self.activateWindow()

    def _tick_countdown(self):
        """倒计时每秒更新"""
        self._alarm_countdown -= 1
        pct = int((self._alarm_countdown / 8) * 100)
        self.progress_bar.setValue(pct)
        if self._alarm_countdown <= 0:
            self._countdown_timer.stop()
            # 触发锁屏（由主控制器处理）

    def start_alarm_countdown(self, seconds: int = 8):
        """启动锁屏倒计时"""
        self._alarm_countdown = seconds
        self.progress_bar.show()
        self.progress_bar.setValue(100)
        self._countdown_timer.start(1000)  # 每秒触发

    def update_info(self, distance_cm: int, energy: int):
        """实时更新距离/能量显示"""
        self.info_label.setText(f"距离: {distance_cm} cm  |  能量: {energy}")
```

### 3.4 弹窗提醒设计

对于 `SUSPECTED_PEEPING` 状态，除遮罩外还需要弹窗提醒：

```python
# alert_dialog.py — 弹窗提醒
from PyQt6.QtWidgets import QMessageBox


def show_privacy_alert(parent, distance_cm: int, on_unlock):
    """弹出疑似偷窥提醒对话框"""
    msg = QMessageBox(parent)
    msg.setWindowTitle("⚠️ 隐私保护提醒")
    msg.setText(f"检测到有人异常接近（距离: {distance_cm} cm）")
    msg.setInformativeText(
        "系统已启动屏幕遮罩保护。\n"
        "如为误报，请点击「解锁」验证身份。\n\n"
        "若 5 秒内未操作，将自动进入深度保护模式。"
    )
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setStandardButtons(
        QMessageBox.StandardButton.Ok |
        QMessageBox.StandardButton.Cancel
    )
    msg.button(QMessageBox.StandardButton.Ok).setText("🔓 解锁")
    msg.button(QMessageBox.StandardButton.Cancel).setText("保持保护")
    msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
    result = msg.exec()
    if result == QMessageBox.StandardButton.Ok:
        on_unlock()
```

---

## 4. 系统锁屏触发

### 4.1 Windows 锁屏

```python
# lock_screen.py — 跨平台锁屏模块
import sys
import subprocess
import platform
import logging

logger = logging.getLogger(__name__)


def lock_screen_windows():
    """Windows 锁屏 — 调用 LockWorkStation API"""
    try:
        import ctypes
        result = ctypes.windll.user32.LockWorkStation()
        if result == 0:
            # 失败时回退到 rundll32
            subprocess.run(
                ["rundll32.exe", "user32.dll,LockWorkStation"],
                check=True, timeout=5
            )
        logger.info("Windows 锁屏已触发")
    except Exception as e:
        logger.error(f"Windows 锁屏失败: {e}")
```

### 4.2 macOS 锁屏

```python
def lock_screen_macos():
    """macOS 锁屏 — 通过 osascript 触发屏幕保护/Siri 快捷键"""
    try:
        # 方案 A：触发屏幕保护（最可靠）
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to start current screen saver'],
            check=True, timeout=5
        )
        # 方案 B：锁屏快捷键（备用）
        # osascript -e 'tell application "System Events" to keystroke "q" using {command down, control down}'
        logger.info("macOS 锁屏已触发")
    except subprocess.TimeoutExpired:
        logger.warning("macOS 锁屏超时")
    except Exception as e:
        logger.error(f"macOS 锁屏失败: {e}")
```

### 4.3 Linux 锁屏

```python
def lock_screen_linux():
    """Linux 锁屏 — 尝试多种桌面环境协议"""
    # 按优先级尝试
    commands = [
        # GNOME / Wayland
        ["loginctl", "lock-session"],
        # GNOME X11
        ["gnome-screensaver-command", "--lock"],
        # KDE Plasma
        ["qdbus", "org.freedesktop.ScreenSaver", "/ScreenSaver", "Lock"],
        # Xfce
        ["xflock4"],
        # i3 / sway
        ["i3lock-fancy"],
        ["swaylock"],
        # 通用（需要 xtrlock）
        ["xtrlock"],
    ]
    for cmd in commands:
        try:
            subprocess.run(cmd, check=True, timeout=5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"Linux 锁屏成功: {' '.join(cmd)}")
            return
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            continue
    logger.error("Linux 锁屏失败: 未找到可用的锁屏命令")
```

### 4.4 统一锁屏入口

```python
def lock_screen():
    """跨平台锁屏 — 自动选择平台锁屏方案"""
    system = platform.system()
    logger.info(f"触发锁屏 (platform={system})")
    if system == "Windows":
        lock_screen_windows()
    elif system == "Darwin":
        lock_screen_macos()
    elif system == "Linux":
        lock_screen_linux()
    else:
        logger.warning(f"不支持的平台: {system}")
```

---

## 5. macOS/Linux 跨平台兼容方案

### 5.1 跨平台矩阵

| 功能 | Windows | macOS | Linux |
|------|---------|-------|-------|
| **串口访问** | `COMx` (COM3) | `/dev/cu.usbmodem*` | `/dev/ttyUSB0`, `/dev/ttyACM0` |
| **全屏遮罩** | ✅ 原生 | ✅（需辅助功能权限） | ✅ X11/Wayland |
| **托盘图标** | ✅ | ✅ | ✅（部分 DE 需 `libappindicator`） |
| **锁屏** | ✅ `LockWorkStation` | ✅ `osascript` | ✅ `loginctl` |
| **音频提醒** | ✅ `winsound` / `playsound` | ✅ `afplay` / `osascript` | ✅ `aplay` / `paplay` |
| **快捷键** | ✅ `keyboard` 库 | ✅ `keyboard` 库 | ✅ `keyboard` 库 |

### 5.2 串口路径检测适配

```python
# serial_reader.py 中的端口检测扩展
import platform
import re

def _platform_port_patterns():
    """返回当前平台的串口路径模式列表"""
    system = platform.system()
    if system == "Windows":
        return [r"COM\d+"]
    elif system == "Darwin":
        return [r"/dev/cu\.(usb|wchusb|slab).*", r"/dev/tty\.(usb|wchusb|slab).*"]
    elif system == "Linux":
        return [r"/dev/ttyUSB\d+", r"/dev/ttyACM\d+", r"/dev/ttyS\d+"]
    return []

def auto_detect_port_platform():
    """平台感知的串口自动检测"""
    ports = serial.tools.list_ports.comports()
    patterns = _platform_port_patterns()

    for p in sorted(ports, key=lambda x: x.device):
        # 优先匹配已知设备描述
        desc_lower = (p.description or "").lower()
        hwid_lower = (p.hwid or "").lower()
        keywords = ["usb", "cdc", "cp210", "ch340", "ftdi", "arduino", "serial"]
        if any(kw in desc_lower or kw in hwid_lower for kw in keywords):
            return p.device

    # 回退：按平台模式匹配
    for p in sorted(ports):
        for pat in patterns:
            if re.match(pat, p.device):
                return p.device
    return None
```

### 5.3 Linux/Wayland 特殊处理

Wayland 下全屏置顶窗口存在局限性：

```python
# wayland_workaround.py
import os

def is_wayland():
    """检测是否运行在 Wayland 会话下"""
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"

def apply_wayland_overlay_fix():
    """Wayland 下强制通过 wlr-foreign-toplevel 或 kwin 脚本置顶"""
    if is_wayland():
        # 设置 Qt 环境变量以启用 Wayland 支持
        os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
        os.environ.setdefault("QT_WAYLAND_DISABLE_WINDOWDECORATION", "1")
        # KDE: 使用 kwin 脚本保持窗口置顶
        # GNOME: 需要 gnome-shell 扩展
        logger.info("Wayland 环境检测到，已应用 Qt Wayland 兼容设置")
```

### 5.4 macO 权限要求

macOS 下需要用户授权辅助功能权限：

```python
def check_macos_accessibility_permissions():
    """检查并提示 macOS 辅助功能权限"""
    if platform.system() != "Darwin":
        return True
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get.any process whose name contains "Privacy Shield"'],
            capture_output=True, text=True, timeout=5
        )
        # 若无权限，osascript 返回错误
        return result.returncode == 0
    except Exception:
        # 无法检查，默认假设有权限
        return True

def request_macos_permissions():
    """引导用户开启辅助功能权限"""
    if not check_macos_accessibility_permissions():
        QMessageBox.information(
            None,
            "权限设置",
            "隐私保护客户端需要「辅助功能」权限才能控制遮罩和锁屏。\n\n"
            "请前往：系统设置 → 隐私与安全性 → 辅助功能\n"
            "勾选「Privacy Shield Client」\n\n"
            "设置后请重新启动应用。"
        )
```

---

## 6. 状态响应映射表

### 6.1 完整映射表

| 序号 | ESP32 上报状态 | PC 应响应动作 | 遮罩不透明度 | 声音 | 托盘图标 | 锁屏 |
|------|---------------|-------------|:----------:|:----:|:--------:|:----:|
| 1 | **NORMAL** | 关闭遮罩，恢复桌面正常显示 | 0% | 无 | 🟢 绿色（正常） | ❌ |
| 2 | **HUMAN_DETECTED** | 无遮罩，托盘图标变色提示 | 0% | 无 | 🟡 黄色（有人） | ❌ |
| 3 | **APPROACHING** | **半透明遮罩（40%）**，小字提示"有人接近" | 40% | 无 | 🟠 橙色（接近） | ❌ |
| 4 | **SUSPECTED_PEEPING** | **弹窗提醒** + **半透明遮罩（60%）** + 距离显示 | 60% | 短促提示音 | 🔴 红色（疑似） | ❌ |
| 5 | **PRIVACY_PROTECT** | **全屏遮罩（80%）** + 警告文字 + 解锁按钮 | 80% | 持续提示音 | 🔴 闪烁（保护） | ❌ |
| 6 | **ALARM** | **全屏遮罩（90%）** + 红色闪烁 + 声音提醒 + **锁屏** | 90% | 告警音 | 🔴 快速闪烁 | ✅ **立即锁屏** |

### 6.2 状态响应控制器

```python
# overlay_controller.py — 状态响应控制器
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
import logging

logger = logging.getLogger(__name__)


class OverlayController(QObject):
    """状态 → 遮罩动作 映射控制器"""

    state_changed = pyqtSignal(str)    # 状态变更通知
    lock_screen_requested = pyqtSignal()  # 请求锁屏

    # ── 状态-动作映射表 ──
    ACTION_MAP = {
        "NORMAL":             {"overlay": "NORMAL",             "tray": "normal",       "sound": None,                "lock": False},
        "HUMAN_DETECTED":     {"overlay": "HUMAN_DETECTED",     "tray": "attention",    "sound": None,                "lock": False},
        "APPROACHING":        {"overlay": "APPROACHING",        "tray": "warning",      "sound": "approach_alert",    "lock": False},
        "SUSPECTED_PEEPING":  {"overlay": "SUSPECTED_PEEPING",  "tray": "danger",       "sound": "peep_alert",        "lock": False},
        "PRIVACY_PROTECT":    {"overlay": "PRIVACY_PROTECT",    "tray": "danger",       "sound": "privacy_alert",     "lock": False},
        "ALARM":              {"overlay": "ALARM",              "tray": "alarm",        "sound": "alarm_siren",       "lock": True},
    }

    def __init__(self, overlay, tray_manager, audio_player):
        super().__init__()
        self.overlay = overlay
        self.tray = tray_manager
        self.audio = audio_player
        self._current_state = "NORMAL"
        self._last_distance = 0
        self._last_energy = 0
        self._alarm_timer = QTimer(self)
        self._alarm_timer.timeout.connect(self._on_alarm_timeout)
        self._alarm_triggered = False

    def on_state_report(self, msg: dict):
        """处理 ESP32 上报的状态消息"""
        data = msg.get("data", {})
        state = data.get("state", "NORMAL")
        distance = data.get("distance_cm", 0)
        energy = data.get("moving_energy", 0)
        target_state = data.get("target_state", 0)

        self._last_distance = distance
        self._last_energy = energy

        # 查找映射动作
        action = self.ACTION_MAP.get(state, self.ACTION_MAP["NORMAL"])
        if action is None:
            logger.warning(f"未知状态: {state}，回退到 NORMAL")
            state = "NORMAL"
            action = self.ACTION_MAP["NORMAL"]

        # 仅在状态变更时执行动作
        if state != self._current_state:
            logger.info(f"状态变更: {self._current_state} → {state}")

            # 应用遮罩
            self.overlay.set_state(
                action["overlay"],
                distance_cm=distance,
                energy=energy,
            )

            # 更新托盘
            self.tray.set_state(action["tray"])

            # 声音提醒
            if action["sound"]:
                self.audio.play(action["sound"])

            # 锁屏
            if action["lock"] and not self._alarm_triggered:
                self._alarm_triggered = True
                self.overlay.start_alarm_countdown(8)
                self._alarm_timer.start(8000)  # 8秒后锁屏
                # 同时立即播放锁屏倒计时声音
                self.audio.play("lock_countdown")

            # 通知外部
            self._current_state = state
            self.state_changed.emit(state)

    def on_unlock_requested(self):
        """用户请求解锁"""
        logger.info("用户请求解锁")
        self._alarm_triggered = False
        self._alarm_timer.stop()
        self.overlay.set_state("NORMAL")
        self.tray.set_state("normal")
        self.audio.stop_all()
        self._current_state = "NORMAL"
        self.state_changed.emit("NORMAL")

    def _on_alarm_timeout(self):
        """告警超时 → 触发锁屏"""
        self._alarm_timer.stop()
        logger.warning("告警倒计时结束，触发系统锁屏")
        self.lock_screen_requested.emit()

    def get_current_state(self) -> str:
        return self._current_state
```

### 6.3 状态转移时序图

```
ESP32                              PC Client
  │                                    │
  │── state_report(NORMAL) ──────────► │  → 关闭遮罩, 绿色托盘图标
  │                                    │
  │── state_report(HUMAN_DETECTED) ──► │  → 托盘变黄 (无遮罩)
  │                                    │
  │── state_report(APPROACHING) ─────► │  → 40% 半透明遮罩
  │                                    │
  │── state_report(SUSPECTED_PEEPING) ► │  → 60% 遮罩 + 弹窗 + 提示音
  │                                    │
  │── state_report(PRIVACY_PROTECT) ──►│  → 80% 遮罩 + 持续音 + 解锁按钮
  │                                    │
  │── state_report(ALARM) ────────────►│  → 90% 遮罩 + 倒计时 8s → 锁屏
  │                                    │
  │   (用户点击解锁)                     │
  │◄── command(set_state=NORMAL) ──────│
  │   (或距离恢复正常)                   │
  │── state_report(NORMAL) ──────────► │  → 恢复桌面
```

---

## 7. 配置参数设计

### 7.1 配置参数列表

| 分类 | 参数名 | 默认值 | 说明 |
|------|--------|--------|------|
| **串口** | `port` | `"auto"` | 串口路径，`"auto"`=自动检测 |
| | `baudrate` | `256000` | 波特率（与雷达一致） |
| | `timeout` | `0.1` | 读取超时（秒） |
| | `reconnect_interval` | `3` | 重连间隔（秒） |
| **阈值** | `suspect_time_ms` | `3000` | 疑似判定时间（ms） |
| | `alarm_time_sec` | `8` | 告警→锁屏倒计时（秒） |
| | `lock_screen_enabled` | `true` | 是否启用自动锁屏 |
| **遮罩** | `approaching_opacity` | `0.4` | APPROACHING 不透明度 |
| | `suspect_opacity` | `0.6` | SUSPECTED_PEEPING 不透明度 |
| | `protect_opacity` | `0.8` | PRIVACY_PROTECT 不透明度 |
| | `alarm_opacity` | `0.9` | ALARM 不透明度 |
| **声音** | `sound_enabled` | `true` | 是否启用声音提醒 |
| | `sound_volume` | `0.7` | 音量 (0.0~1.0) |
| **日志** | `log_level` | `"INFO"` | 日志级别 |
| | `log_dir` | `"./logs"` | 日志目录 |
| **解锁** | `unlock_password` | `""` | 解锁密码（空=无需密码） |
| | `unlock_hotkey` | `"Ctrl+Alt+P"` | 解锁快捷键 |

### 7.2 配置文件格式（YAML）

```python
# config_manager.py — 配置管理器
import os
import yaml
from typing import Any

CONFIG_DEFAULTS = {
    "serial": {
        "port": "auto",
        "baudrate": 256000,
        "timeout": 0.1,
        "reconnect_interval": 3,
    },
    "thresholds": {
        "suspect_time_ms": 3000,
        "alarm_time_sec": 8,
        "lock_screen_enabled": True,
    },
    "overlay": {
        "approaching_opacity": 0.4,
        "suspect_opacity": 0.6,
        "protect_opacity": 0.8,
        "alarm_opacity": 0.9,
    },
    "sound": {
        "enabled": True,
        "volume": 0.7,
    },
    "logging": {
        "level": "INFO",
        "dir": "./logs",
    },
    "unlock": {
        "password": "",
        "hotkey": "Ctrl+Alt+P",
    },
}


class ConfigManager:
    """YAML 配置文件读写"""

    def __init__(self, path: str = None):
        self.path = path or os.path.join(
            os.path.dirname(__file__), "config.yaml"
        )
        self._data = {}
        self.load()

    def load(self):
        """加载配置，缺失项用默认值填充"""
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
        else:
            user_config = {}

        # 合并默认值
        self._data = self._deep_merge(CONFIG_DEFAULTS, user_config)

    def save(self):
        """保存配置到文件"""
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, default_flow_style=False,
                      allow_unicode=True, indent=2)

    def get(self, *keys: str, default: Any = None) -> Any:
        """按路径获取配置值，如 get('serial', 'baudrate')"""
        d = self._data
        for k in keys:
            if isinstance(d, dict):
                d = d.get(k)
            else:
                return default
        return d if d is not None else default

    def set(self, value: Any, *keys: str):
        """按路径设置配置值"""
        d = self._data
        for k in keys[:-1]:
            if k not in d:
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """递归合并字典"""
        result = base.copy()
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = ConfigManager._deep_merge(result[k], v)
            else:
                result[k] = v
        return result
```

### 7.3 示例配置（config.yaml）

```yaml
serial:
  port: auto                # 自动检测，或指定如 COM3 / /dev/ttyUSB0
  baudrate: 256000
  timeout: 0.1
  reconnect_interval: 3

thresholds:
  suspect_time_ms: 3000
  alarm_time_sec: 8
  lock_screen_enabled: true

overlay:
  approaching_opacity: 0.4
  suspect_opacity: 0.6
  protect_opacity: 0.8
  alarm_opacity: 0.9

sound:
  enabled: true
  volume: 0.7

logging:
  level: INFO
  dir: ./logs

unlock:
  password: ""
  hotkey: Ctrl+Alt+P
```

---

## 8. 托盘图标 / 后台运行设计

### 8.1 托盘图标状态表

| 状态 | 图标 | 悬停文字 | 右键菜单 |
|------|------|---------|---------|
| **NORMAL** | 🟢 绿色圆点 | "隐私保护 · 正常" | 显示主窗口 / 配置 / 退出 |
| **HUMAN_DETECTED** | 🟡 黄色圆点 | "隐私保护 · 有人" | 同上 + "当前: 检测到人" |
| **APPROACHING** | 🟠 橙色圆点 | "隐私保护 · 接近中 45cm" | 同上 + "距离: 45cm" |
| **SUSPECTED_PEEPING** | 🔴 红色圆点 | "隐私保护 · 疑似偷窥!" | 同上 + "⚠ 疑似偷窥" |
| **PRIVACY_PROTECT** | 🔴 闪烁红色 | "隐私保护 · 已激活" | 同上 + "🔒 隐私保护" |
| **ALARM** | 🔴 快速闪烁 | "🚨 告警！即将锁屏" | 同上 + "🚨 告警中" |

### 8.2 托盘图标实现

```python
# tray_manager.py — 系统托盘管理
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PyQt6.QtCore import QTimer


class TrayManager:
    """托盘图标管理器"""

    # 状态 → 颜色映射（RGB）
    STATE_COLORS = {
        "normal":    (76, 175, 80),     # 🟢 绿色
        "attention": (255, 193, 7),     # 🟡 黄色
        "warning":   (255, 152, 0),     # 🟠 橙色
        "danger":    (244, 67, 54),     # 🔴 红色
        "alarm":     (244, 67, 54),     # 🔴 红色（闪烁）
    }

    def __init__(self, app, on_show_window=None, on_config=None, on_quit=None):
        self.app = app
        self._current_state = "normal"
        self._blink_state = False

        # 创建图标
        self.icon = QIcon()
        self._render_icon(76, 175, 80)   # 初始绿色

        # 托盘
        self.tray = QSystemTrayIcon(self.icon, app.activeWindow())
        self.tray.setToolTip("隐私保护客户端 · 正常")

        # 右键菜单
        self.menu = QMenu()

        self.status_action = QAction("当前状态: 正常")
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)

        self.menu.addSeparator()

        if on_show_window:
            show_action = QAction("📺 显示主窗口")
            show_action.triggered.connect(on_show_window)
            self.menu.addAction(show_action)

        if on_config:
            config_action = QAction("⚙️ 配置")
            config_action.triggered.connect(on_config)
            self.menu.addAction(config_action)

        self.menu.addSeparator()

        if on_quit:
            quit_action = QAction("🚪 退出")
            quit_action.triggered.connect(on_quit)
            self.menu.addAction(quit_action)

        self.tray.setContextMenu(self.menu)

        # 闪烁定时器（仅 ALARM 状态启用）
        self._blink_timer = QTimer()
        self._blink_timer.timeout.connect(self._tick_blink)

        # 显示托盘
        self.tray.show()

    def _render_icon(self, r: int, g: int, b: int, size: int = 32):
        """绘制彩色圆点图标"""
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(r, g, b))
        painter.setPen(QColor(r, g, b))
        painter.drawEllipse(2, 2, size - 4, size - 4)
        painter.end()
        self.icon.addPixmap(pixmap)

    def set_state(self, state: str, distance: int = 0):
        """切换托盘图标状态"""
        self._current_state = state
        color = self.STATE_COLORS.get(state, self.STATE_COLORS["normal"])

        # 文字
        tooltips = {
            "normal":    "隐私保护 · 正常",
            "attention": "隐私保护 · 检测到人",
            "warning":   f"隐私保护 · 接近中 {distance}cm",
            "danger":    "隐私保护 · ⚠ 疑似偷窥!",
            "alarm":     "🚨 隐私保护 · 告警中!",
        }
        self.tray.setToolTip(tooltips.get(state, "隐私保护客户端"))

        # 状态显示
        status_texts = {
            "normal":    "当前状态: 正常",
            "attention": "当前状态: 检测到人",
            "warning":   f"当前状态: 接近中 ({distance}cm)",
            "danger":    "当前状态: ⚠ 疑似偷窥",
            "alarm":     "当前状态: 🚨 告警中",
        }
        self.status_action.setText(status_texts.get(state, "当前状态: 正常"))

        # 图标渲染 / 闪烁控制
        if state == "alarm":
            self._blink_timer.start(500)  # 500ms 闪烁
        else:
            self._blink_timer.stop()
            self._blink_state = False
            self._render_icon(*color)

    def _tick_blink(self):
        """闪烁定时器"""
        self._blink_state = not self._blink_state
        if self._blink_state:
            self._render_icon(244, 67, 54)      # 红色
        else:
            self._render_icon(180, 40, 40)      # 暗红色（半透明效果）

    def show_message(self, title: str, message: str,
                     icon=QSystemTrayIcon.MessageIcon.Information, duration: int = 3000):
        """显示托盘气泡通知"""
        self.tray.showMessage(title, message, icon, duration)

    def set_menu_text(self, text: str):
        """更新菜单中的状态文字"""
        self.status_action.setText(text)
```

### 8.3 后台运行与开机自启

```python
# background.py — 后台运行管理
import sys
import os
import platform


def minimize_to_tray(window):
    """隐藏主窗口到托盘"""
    window.hide()
    # 不退出应用，仅在托盘运行


def setup_autostart(enabled: bool = True):
    """配置开机自启（当前用户）"""
    app_name = "PrivacyShieldClient"
    system = platform.system()

    if system == "Windows":
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        exe_path = sys.executable
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path,
                                0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
                else:
                    winreg.DeleteValue(key, app_name)
        except WindowsError:
            pass

    elif system == "Darwin":
        # macOS LaunchAgents
        plist_path = os.path.expanduser(
            f"~/Library/LaunchAgents/com.nousresearch.{app_name}.plist"
        )
        if enabled:
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nousresearch.{app_name}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{os.path.abspath(__file__)}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>"""
            with open(plist_path, "w") as f:
                f.write(plist_content)
        else:
            if os.path.exists(plist_path):
                os.remove(plist_path)

    elif system == "Linux":
        # Linux .desktop autostart
        autostart_dir = os.path.expanduser("~/.config/autostart")
        desktop_path = os.path.join(autostart_dir, f"{app_name}.desktop")
        if enabled:
            os.makedirs(autostart_dir, exist_ok=True)
            desktop_content = f"""[Desktop Entry]
Type=Application
Name={app_name}
Exec={sys.executable} {os.path.abspath(__file__)}
Terminal=false
X-GNOME-Autostart-enabled=true
"""
            with open(desktop_path, "w") as f:
                f.write(desktop_content)
        else:
            if os.path.exists(desktop_path):
                os.remove(desktop_path)
```

---

## 9. 错误重连机制

### 9.1 串口断连场景

| 场景 | 触发条件 | 恢复方式 |
|------|---------|---------|
| USB 线缆松动 | `SerialException: device reports readiness to read` | 自动重连（指数退避） |
| ESP32 重启/刷固件 | 串口短时间内不可用 | 等待设备枚举完成 |
| PC 休眠后唤醒 | 串口句柄失效 | 主动检测 → 重试打开 |
| 设备被其他应用占用 | `SerialException: could not open port` | 等待释放 + 重试 |
| 波特率不匹配 | 数据全为乱码 | 尝试不同波特率（自动探测） |

### 9.2 重连引擎

```python
# reconnector.py — 智能重连引擎
import time
import threading
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ReconnectStrategy(Enum):
    FIXED = "fixed"          # 固定间隔
    LINEAR = "linear"        # 线性递增
    EXPONENTIAL = "exp"      # 指数退避（默认）
    IMMEDIATE = "immediate"  # 立即重试（仅对瞬时错误）


class SerialReconnector:
    """串口重连管理器：自动检测断连并恢复"""

    def __init__(self, serial_reader_factory, config: dict):
        """
        :param serial_reader_factory: 可调用，返回新的 SerialReader 实例
        :param config: 配置字典
        """
        self._factory = serial_reader_factory
        self._config = config
        self._reader = None
        self._running = False
        self._thread = None

        # 重连参数
        self.strategy = ReconnectStrategy.EXPONENTIAL
        self.base_interval = config.get("serial", {}).get("reconnect_interval", 3)
        self.max_interval = 60          # 最大间隔 60s
        self.max_attempts = 0            # 0 = 无限重试
        self._attempt_count = 0

        # 状态
        self._connected = False
        self._manual_stop = False

    def start(self):
        """启动串口连接 + 重连守护"""
        self._running = True
        self._manual_stop = False
        self._attempt_count = 0
        self._connect()
        # 启动后台监控线程
        self._thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止连接和重连"""
        self._manual_stop = True
        self._running = False
        if self._reader:
            self._reader.stop()
            self._reader = None
        self._connected = False

    def _connect(self):
        """尝试建立连接"""
        try:
            if self._reader:
                self._reader.stop()
            self._reader = self._factory()
            self._reader.start()
            self._connected = True
            self._attempt_count = 0
            logger.info("串口连接成功")
            return True
        except Exception as e:
            self._connected = False
            self._attempt_count += 1
            logger.warning(f"连接失败 (第{self._attempt_count}次): {e}")
            return False

    def _watchdog_loop(self):
        """后台看门狗：监控连接状态，自动重连"""
        while self._running and not self._manual_stop:
            # 检查连接是否还活着
            if not self._is_connection_alive():
                if self._connected:
                    logger.warning("连接断开，启动重连")
                    self._connected = False

                # 计算等待间隔
                delay = self._calc_delay()
                logger.info(f"等待 {delay}s 后重试...")

                # 等待期间检查停止信号
                for _ in range(int(delay * 10)):
                    if not self._running or self._manual_stop:
                        return
                    time.sleep(0.1)

                # 检查最大重试次数
                if self.max_attempts > 0 and self._attempt_count >= self.max_attempts:
                    logger.error(f"重连次数已达上限 ({self.max_attempts})，停止重试")
                    break

                # 重试连接
                self._connect()
            else:
                # 连接正常，休眠后继续检查
                time.sleep(1)

    def _is_connection_alive(self) -> bool:
        """检查串口连接是否存活"""
        if not self._reader or not self._connected:
            return False
        try:
            ser = getattr(self._reader, '_serial', None)
            if ser and ser.is_open:
                # 简单探活：检查是否有错误队列消息
                if not self._reader.error_queue.empty():
                    return False
                return True
            return False
        except Exception:
            return False

    def _calc_delay(self) -> float:
        """根据策略计算重连等待时间"""
        if self.strategy == ReconnectStrategy.FIXED:
            return self.base_interval
        elif self.strategy == ReconnectStrategy.LINEAR:
            return min(self.base_interval * (self._attempt_count + 1), self.max_interval)
        elif self.strategy == ReconnectStrategy.EXPONENTIAL:
            delay = self.base_interval * (2 ** min(self._attempt_count, 6))
            return min(delay, self.max_interval)
        else:  # IMMEDIATE
            return 0.5
```

### 9.3 用户界面反馈

```python
def show_connection_status(tray, status: str):
    """在托盘图标上显示连接状态"""
    icons = {
        "connected":    ("🟢", "已连接"),
        "disconnected": ("🔴", "已断开"),
        "reconnecting": ("🟡", "重连中..."),
        "error":        ("❌", "连接错误"),
    }
    icon, text = icons.get(status, ("❓", "未知状态"))
    tray.setToolTip(f"隐私保护客户端 · {text}")
    if status == "disconnected":
        tray.show_message("连接断开", "串口连接已断开，正在自动重连...",
                          QSystemTrayIcon.MessageIcon.Warning)
    elif status == "reconnecting":
        tray.show_message("重连中", f"正在尝试重新连接串口...",
                          QSystemTrayIcon.MessageIcon.Information)
```

---

## 10. 测试调试方案

### 10.1 测试架构

```
┌──────────────────────────────────────────┐
│               测试体系                      │
├──────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────────┐  │
│  │ 单元测试       │  │ 集成测试          │  │
│  │ • 串口解析     │  │ • 全链路模拟     │  │
│  │ • 状态映射     │  │ • 错误注入       │  │
│  │ • 配置管理     │  │ • 重连测试       │  │
│  │ • 锁屏调用     │  │                  │  │
│  └──────────────┘  └──────────────────┘  │
│  ┌──────────────┐  ┌──────────────────┐  │
│  │ 模拟工具       │  │ 调试工具          │  │
│  │ • 串口模拟器   │  │ • 日志查看器     │  │
│  │ • 状态序列     │  │ • 数据嗅探       │  │
│  │ • 压力测试     │  │ • 性能分析       │  │
│  └──────────────┘  └──────────────────┘  │
└──────────────────────────────────────────┘
```

### 10.2 串口模拟器（用于无硬件调试）

```python
#!/usr/bin/env python3
"""serial_simulator.py — 串口模拟器，模拟 ESP32 发送状态数据"""

import serial
import serial.tools.list_ports
import json
import time
import random
import threading
import sys


class SerialSimulator:
    """虚拟 ESP32 串口设备（使用回环串口对或 TCP 转发）"""

    # 状态序列（模拟真实场景）
    SCENARIOS = {
        "normal": [
            {"state": "NORMAL", "target_state": 0, "distance_cm": 0, "moving_energy": 0, "static_energy": 0, "detect_distance_cm": 300},
        ],
        "approach": [
            {"state": "NORMAL", "target_state": 0, "distance_cm": 0, "moving_energy": 0, "static_energy": 0, "detect_distance_cm": 300},
            {"state": "HUMAN_DETECTED", "target_state": 1, "distance_cm": 200, "moving_energy": 30, "static_energy": 20, "detect_distance_cm": 300},
            {"state": "APPROACHING", "target_state": 2, "distance_cm": 120, "moving_energy": 45, "static_energy": 35, "detect_distance_cm": 300},
            {"state": "APPROACHING", "target_state": 2, "distance_cm": 95, "moving_energy": 50, "static_energy": 40, "detect_distance_cm": 300},
        ],
        "peep": [
            {"state": "SUSPECTED_PEEPING", "target_state": 3, "distance_cm": 65, "moving_energy": 60, "static_energy": 55, "detect_distance_cm": 300},
            {"state": "SUSPECTED_PEEPING", "target_state": 3, "distance_cm": 55, "moving_energy": 65, "static_energy": 60, "detect_distance_cm": 300},
        ],
        "protect": [
            {"state": "PRIVACY_PROTECT", "target_state": 3, "distance_cm": 45, "moving_energy": 70, "static_energy": 65, "detect_distance_cm": 300},
        ],
        "alarm": [
            {"state": "ALARM", "target_state": 3, "distance_cm": 30, "moving_energy": 85, "static_energy": 75, "detect_distance_cm": 300},
        ],
        "full_scenario": [
            # 模拟完整事件序列
            {"state": "NORMAL",          "distance_cm": 0,   "moving_energy": 0,  "static_energy": 0},
            {"state": "HUMAN_DETECTED",  "distance_cm": 220, "moving_energy": 25, "static_energy": 10},
            {"state": "APPROACHING",     "distance_cm": 140, "moving_energy": 40, "static_energy": 30},
            {"state": "APPROACHING",     "distance_cm": 100, "moving_energy": 48, "static_energy": 38},
            {"state": "SUSPECTED_PEEPING","distance_cm": 70, "moving_energy": 55, "static_energy": 50},
            {"state": "SUSPECTED_PEEPING","distance_cm": 55, "moving_energy": 62, "static_energy": 58},
            {"state": "PRIVACY_PROTECT",  "distance_cm": 40, "moving_energy": 70, "static_energy": 65},
            {"state": "ALARM",           "distance_cm": 25, "moving_energy": 85, "static_energy": 78},
            {"state": "NORMAL",          "distance_cm": 0,   "moving_energy": 0,  "static_energy": 0},  # 恢复正常
        ],
    }

    def __init__(self, port: str = "COM10", baudrate: int = 256000):
        self.port = port
        self.baudrate = baudrate
        self._running = False
        self._serial = None

    def start(self):
        """打开串口并开始发送模拟数据"""
        if self.port == "loopback":
            # 使用虚拟串口对（需要 com0com 或 socat）
            self._run_virtual()
        else:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=1)
            self._running = True
            thread = threading.Thread(target=self._send_loop, daemon=True)
            thread.start()
            print(f"模拟器已启动: {self.port} @ {self.baudrate}")

    def _send_loop(self):
        """循环发送模拟数据"""
        scenario = self.SCENARIOS["full_scenario"]
        cycle_count = 0
        while self._running:
            for data in scenario:
                if not self._running:
                    break
                # 构造 JSON 行
                msg = {
                    "type": "state_report",
                    "timestamp_ms": int(time.time() * 1000),
                    "data": data,
                }
                line = json.dumps(msg, ensure_ascii=False) + "\n"
                self._serial.write(line.encode("utf-8"))
                self._serial.flush()
                print(f"[SEND] {data['state']}  dist={data.get('distance_cm',0)}cm")
                time.sleep(1.0)  # 每秒一条
            cycle_count += 1
            print(f"\n=== 场景循环 #{cycle_count} 完成，重新开始 ===\n")

    def stop(self):
        self._running = False
        if self._serial:
            self._serial.close()

    @staticmethod
    def _run_virtual():
        """使用 socat 创建虚拟串口对（Linux/macOS）"""
        import subprocess
        print("启动虚拟串口对 (socat)...")
        subprocess.run([
            "socat", "-d", "-d",
            "PTY,link=/tmp/vcom0,raw,echo=0",
            "PTY,link=/tmp/vcom1,raw,echo=0"
        ])


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "loopback"
    sim = SerialSimulator(port=port)
    try:
        sim.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sim.stop()
        print("\n模拟器已停止")
```

### 10.3 单元测试清单

```python
# test_suite.py — 单元测试用例（pytest）
"""
运行: pytest test_suite.py -v
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

# ── 测试串口解析 ──
class TestSerialReader:
    def test_parse_state_report(self):
        """标准状态上报解析"""
        reader = SerialReader.__new__(SerialReader)
        line = b'{"type":"state_report","timestamp_ms":1000,"data":{"state":"APPROACHING","target_state":2,"distance_cm":95}}'
        result = []
        reader.callback = result.append
        reader._parse_line(line)
        assert len(result) == 1
        assert result[0]["type"] == "state_report"
        assert result[0]["data"]["state"] == "APPROACHING"

    def test_parse_simple_format(self):
        """简版格式（无 type 字段）"""
        reader = SerialReader.__new__(SerialReader)
        line = b'{"state":"SUSPECTED_PEEPING","distance_cm":65,"timestamp_ms":1000}'
        result = []
        reader.callback = result.append
        reader._parse_line(line)
        assert len(result) == 1
        assert result[0]["type"] == "state_report"   # 自动补充
        assert result[0]["data"]["state"] == "SUSPECTED_PEEPING"

    def test_malformed_json(self):
        """损坏的 JSON 行不应导致崩溃"""
        reader = SerialReader.__new__(SerialReader)
        line = b'{broken json}'
        result = []
        reader.callback = result.append
        try:
            reader._parse_line(line)
        except Exception:
            pytest.fail("解析损坏 JSON 不应抛异常")
        assert len(result) == 0

    def test_empty_line(self):
        """空行跳过"""
        reader = SerialReader.__new__(SerialReader)
        result = []
        reader.callback = result.append
        reader._parse_line(b"")
        assert len(result) == 0


# ── 测试状态映射 ──
class TestStateMapping:
    @pytest.fixture
    def controller(self):
        overlay = MagicMock()
        tray = MagicMock()
        audio = MagicMock()
        return OverlayController(overlay, tray, audio)

    def test_normal_state(self, controller):
        """NORMAL → 关闭遮罩"""
        msg = {"type": "state_report", "data": {"state": "NORMAL", "distance_cm": 0}}
        controller.on_state_report(msg)
        controller.overlay.set_state.assert_called_with("NORMAL", distance_cm=0, energy=0)

    def test_approaching_state(self, controller):
        """APPROACHING → 40% 遮罩"""
        msg = {"type": "state_report", "data": {"state": "APPROACHING", "distance_cm": 95, "moving_energy": 12}}
        controller.on_state_report(msg)
        controller.overlay.set_state.assert_called_with("APPROACHING", distance_cm=95, energy=12)
        controller.tray.set_state.assert_called_with("warning")

    def test_alarm_state_triggers_lock(self, controller):
        """ALARM → 触发锁屏信号"""
        msg = {"type": "state_report", "data": {"state": "ALARM", "distance_cm": 25}}
        controller.on_state_report(msg)
        controller.overlay.start_alarm_countdown.assert_called_once()
        # 锁屏信号在倒计时结束后触发

    def test_state_transition_normal_to_peep(self, controller):
        """NORMAL → SUSPECTED_PEEPING 状态切换"""
        msg1 = {"type": "state_report", "data": {"state": "NORMAL"}}
        msg2 = {"type": "state_report", "data": {"state": "SUSPECTED_PEEPING", "distance_cm": 60}}
        controller.on_state_report(msg1)
        controller.on_state_report(msg2)
        # 应调用两次 set_state
        assert controller.overlay.set_state.call_count == 2


# ── 测试锁屏 ──
class TestLockScreen:
    @patch('ctypes.windll.user32.LockWorkStation')
    def test_windows_lock(self, mock_lock):
        """Windows 锁屏调用"""
        lock_screen_windows()
        mock_lock.assert_called_once()

    @patch('subprocess.run')
    def test_macos_lock(self, mock_run):
        """macOS 锁屏调用"""
        lock_screen_macos()
        mock_run.assert_called()

    @patch('subprocess.run')
    def test_linux_lock_gnome(self, mock_run):
        """Linux 锁屏（GNOME）"""
        lock_screen_linux()
        # 应至少调用了一个锁屏命令
        assert mock_run.call_count >= 1


# ── 测试重连 ──
class TestReconnect:
    def test_exponential_backoff(self):
        """指数退避计算"""
        reconnector = SerialReconnector.__new__(SerialReconnector)
        reconnector.base_interval = 3
        reconnector.max_interval = 60
        reconnector.strategy = ReconnectStrategy.EXPONENTIAL
        reconnector._attempt_count = 0
        assert reconnector._calc_delay() == 3     # 3*2^0 = 3
        reconnector._attempt_count = 1
        assert reconnector._calc_delay() == 6     # 3*2^1 = 6
        reconnector._attempt_count = 3
        assert reconnector._calc_delay() == 24    # 3*2^3 = 24
        reconnector._attempt_count = 10
        assert reconnector._calc_delay() == 60    # 上限 60


# ── 测试配置 ──
class TestConfig:
    def test_default_values(self, tmp_path):
        """默认配置加载"""
        config_path = tmp_path / "test_config.yaml"
        mgr = ConfigManager(str(config_path))
        assert mgr.get("serial", "port") == "auto"
        assert mgr.get("serial", "baudrate") == 256000
        assert mgr.get("thresholds", "suspect_time_ms") == 3000

    def test_save_and_load(self, tmp_path):
        """保存后重新加载"""
        config_path = tmp_path / "test_config.yaml"
        mgr = ConfigManager(str(config_path))
        mgr.set("COM5", "serial", "port")
        mgr.set(115200, "serial", "baudrate")
        mgr.save()

        mgr2 = ConfigManager(str(config_path))
        mgr2.load()
        assert mgr2.get("serial", "port") == "COM5"
        assert mgr2.get("serial", "baudrate") == 115200
```

### 10.4 调试工具

| 工具 | 用途 | 命令 |
|------|------|------|
| **串口嗅探** | 查看原始串口数据流 | `python -m serial.tools.miniterm COM3 256000` |
| **状态模拟器** | 无硬件时模拟 ESP32 数据 | `python serial_simulator.py COM10` |
| **日志查看** | 实时查看 PC 客户端日志 | `tail -f logs/privacy_shield.log` |
| **数据录制/回放** | 录制真实数据用于回归测试 | `python replay_recorder.py` |
| **性能分析** | CPU/内存占用分析 | `python -m cProfile -o profile.out main.py` |
| **屏幕截图** | 自动截取各状态下的遮罩效果 | `pytest --screenshot` |

---

## 附录 A：推荐文件结构

```
pc_client/
├── main.py                          # 应用入口
├── requirements.txt                 # 依赖清单
├── config.yaml                      # 用户配置文件
├── config_manager.py                # 配置读写
├── serial_reader.py                 # 串口读取引擎
├── reconnector.py                   # 重连管理器
├── overlay.py                       # 遮罩 UI
├── overlay_controller.py            # 状态响应映射控制器
├── alert_dialog.py                  # 弹窗提醒
├── tray_manager.py                  # 托盘图标
├── lock_screen.py                   # 跨平台锁屏
├── audio_player.py                  # 声音提醒
├── background.py                    # 后台运行/自启
├── wayland_workaround.py            # Wayland 兼容
├── logs/                            # 日志目录
│   └── privacy_shield.log
├── sounds/                          # 音效文件
│   ├── approach_alert.wav
│   ├── peep_alert.wav
│   ├── privacy_alert.wav
│   ├── alarm_siren.wav
│   └── lock_countdown.wav
├── tests/                           # 测试目录
│   ├── test_serial_reader.py
│   ├── test_state_mapping.py
│   ├── test_lock_screen.py
│   ├── test_reconnect.py
│   ├── test_config.py
│   ├── serial_simulator.py          # 串口模拟工具
│   └── replay_recorder.py           # 数据录制回放
└── README.md
```

## 附录 B：依赖清单（requirements.txt）

```
pyserial>=3.5
PyQt6>=6.5
PyQt6.QtSvg>=6.5
pyyaml>=6.0
playsound>=1.3.0
pytest>=7.0
pytest-qt>=4.0
```

## 附录 C：开发路线图

| 阶段 | 内容 | 预计工时 | 可测试标志 |
|------|------|---------|-----------|
| **P0** 核心串口 | 串口读取 + JSON 解析 + 重连 | 2天 | 串口模拟器可收到数据 |
| **P1** 遮罩 UI | 全屏遮罩窗口 + 各状态显示 | 2天 | 各状态遮罩显示正确 |
| **P2** 状态映射 | 状态响应控制器 + 托盘图标 | 1天 | 状态切换时遮罩/图标联动 |
| **P3** 系统集成 | 跨平台锁屏 + 声音提醒 + 快捷键 | 2天 | 锁屏功能正常触发 |
| **P4** 配置与管理 | 配置管理 + 后台运行 + 开机自启 | 1天 | 配置修改保存生效 |
| **P5** 测试完善 | 单元测试 + 集成测试 + 压力测试 | 2天 | 测试覆盖率 > 85% |
| **P6** 打包分发 | Nuitka 编译 + 安装包制作 | 1天 | 单文件可分发运行 |
