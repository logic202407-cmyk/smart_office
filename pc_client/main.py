"""
main.py - 程序入口，整合所有模块
====================================
功能：
  1. 初始化配置管理器
  2. 初始化串口读取器（后台线程）
  3. 初始化全屏遮罩窗口（多显示器支持）
  4. 初始化系统托盘
  5. 初始化声音报警
  6. 状态机：根据 ESP32 状态驱动遮罩、声音、锁屏
  7. 看门狗：监控串口连接和数据超时

启动命令:
    python main.py                    # 使用默认配置
    python main.py -c config.yaml     # 指定配置文件
    python main.py -d                 # DEBUG 日志模式
"""

import argparse
import logging
import logging.handlers
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

# 本地模块
from config_manager import ConfigManager
from serial_reader import SerialReader, SensorData
from overlay_window import OverlayWindow
from tray_app import TrayApp
from sound_alarm import SoundAlarm
from lock_screen import lock_screen

logger = logging.getLogger("PeepPrevention")


# ==================================================================
# 看门狗状态
# ==================================================================
class WatchdogState:
    """看门狗状态跟踪"""

    def __init__(self, timeout_sec: float = 5.0) -> None:
        self.timeout_sec = timeout_sec
        self._last_update = time.time()
        self._lock = threading.Lock()
        self._last_state: str = "NORMAL"

    def update(self, state: str) -> None:
        with self._lock:
            self._last_update = time.time()
            self._last_state = state

    def check_timeout(self) -> bool:
        """返回 True 表示超时（数据太久没更新）"""
        with self._lock:
            elapsed = time.time() - self._last_update
            return elapsed > self.timeout_sec

    @property
    def last_state(self) -> str:
        with self._lock:
            return self._last_state


# ==================================================================
# 隐私保护应用程序
# ==================================================================
class PeepPreventionApp:
    """
    隐私保护主应用程序 - 整合所有子模块。

    状态驱动逻辑:
        NORMAL            → 隐藏遮罩, 停止报警
        HUMAN_DETECTED    → 托盘黄色, 无遮罩
        APPROACHING       → 半透明遮罩 ~40%
        SUSPECTED_PEEPING → 遮罩 ~60%, 弹窗文字
        PRIVACY_PROTECT   → 遮罩 ~80%, 警告文字, 倒计时
        ALARM             → 遮罩 ~90%, 声音报警, 锁屏
    """

    def __init__(self, config_path: str = "config.yaml") -> None:
        self._config_path = config_path

        # --- 配置 ---
        self._config = ConfigManager(config_path)
        self._setup_logging()

        logger.info("=" * 60)
        logger.info("SmartOffice PeepPrevention - PC端隐私保护程序 启动")
        logger.info("=" * 60)

        # --- Qt 应用 ---
        self._app = QApplication(sys.argv)
        self._app.setApplicationName("PeepPrevention")
        self._app.setQuitOnLastWindowClosed(False)

        # --- 串口读取器 ---
        self._serial_reader = SerialReader(
            port=self._config.get_serial_port(),
            baudrate=self._config.get_serial_baudrate(),
            timeout=self._config.get_serial_timeout(),
            reconnect_params=self._config.get_reconnect_params(),
            on_data=self._on_sensor_data,
            on_connection_change=self._on_connection_change,
            on_error=self._on_serial_error,
        )

        # --- 遮罩窗口 (多显示器) ---
        self._overlays: List[OverlayWindow] = []
        self._setup_overlays()

        # --- 看门狗 ---
        self._watchdog = WatchdogState(timeout_sec=5.0)

        # --- 声音报警 ---
        self._sound_alarm = SoundAlarm()
        self._init_sound()

        # --- 系统托盘 ---
        self._tray = TrayApp(
            app=self._app,
            on_show_overlay=self._show_overlays,
            on_hide_overlay=self._hide_overlays,
            on_lock_screen=self._trigger_lock_screen,
            on_quit=self.quit,
            show_toast=self._config.get("tray", "show_toast_on_state", default=True),
        )

        # --- 锁屏状态 ---
        self._lock_screen_triggered = False
        self._lock_screen_delay = self._config.get_lock_screen_delay()
        self._countdown_active = False

        # --- 定时器: 看门狗检查 ---
        self._watchdog_timer = QTimer()
        self._watchdog_timer.timeout.connect(self._watchdog_check)
        self._watchdog_timer.start(1000)  # 每秒检查

        # --- 定时器: 锁屏延迟 ---
        self._lock_timer = QTimer()
        self._lock_timer.timeout.connect(self._execute_lock_screen)

        logger.info("所有模块初始化完成")

    # ------------------------------------------------------------------
    # 启动 / 运行
    # ------------------------------------------------------------------

    def run(self) -> None:
        """启动应用程序主循环"""
        # 启动串口读取
        self._serial_reader.start()
        logger.info("串口读取器已启动")

        # 进入 Qt 事件循环
        exit_code = self._app.exec()

        # 退出清理
        self._cleanup()
        sys.exit(exit_code)

    def quit(self) -> None:
        """退出应用程序"""
        logger.info("正在退出...")
        self._app.quit()

    # ------------------------------------------------------------------
    # 遮罩管理
    # ------------------------------------------------------------------

    def _setup_overlays(self) -> None:
        """为每个显示器创建遮罩窗口"""
        screens = self._app.screens()
        opacity_levels = self._config.get("overlay", "opacity_levels", default={})
        overlay_color = self._config.get_overlay_color()
        warning_color = self._config.get_warning_color()

        for i, screen in enumerate(screens):
            overlay = OverlayWindow(
                screen_index=i,
                opacity_levels=opacity_levels,
                overlay_color=overlay_color,
                warning_color=warning_color,
            )
            geometry = screen.geometry()
            overlay.show_on_screen(geometry)
            self._overlays.append(overlay)

        logger.info(f"已创建 {len(screens)} 个遮罩窗口")

    def _show_overlays(self) -> None:
        """显示所有遮罩"""
        for overlay in self._overlays:
            overlay.signals.show_overlay.emit()

    def _hide_overlays(self) -> None:
        """隐藏所有遮罩"""
        for overlay in self._overlays:
            overlay.signals.hide_overlay.emit()

    def _update_overlays(self, state: str, distance: float, moving_energy: float, static_energy: float) -> None:
        """更新所有遮罩状态"""
        for overlay in self._overlays:
            overlay.update_state(state, distance, moving_energy, static_energy)

    def _start_countdown(self) -> None:
        """启动所有遮罩的锁屏倒计时"""
        if self._countdown_active:
            return
        self._countdown_active = True
        for overlay in self._overlays:
            overlay.start_countdown(self._lock_screen_delay)
        # 启动实际锁屏定时器
        self._lock_timer.start(self._lock_screen_delay * 1000)

    def _stop_countdown(self) -> None:
        """停止锁屏倒计时"""
        self._countdown_active = False
        self._lock_timer.stop()
        self._lock_screen_triggered = False
        for overlay in self._overlays:
            overlay.stop_countdown()

    # ------------------------------------------------------------------
    # 串口回调
    # ------------------------------------------------------------------

    def _on_sensor_data(self, data: SensorData) -> None:
        """
        收到 ESP32 传感器数据的回调。
        这是从串口线程调用的。
        """
        state = data.state
        distance = data.distance_cm
        moving_energy = data.moving_energy
        static_energy = data.static_energy

        logger.debug(f"收到数据: state={state}, dist={distance:.0f}cm")

        # 更新看门狗
        self._watchdog.update(state)

        # 更新托盘状态（线程安全通过信号）
        self._tray.set_state(state)

        # 更新托盘提示
        self._tray.set_tooltip(
            f"隐私保护 - {state}\n"
            f"距离: {distance:.0f}cm | "
            f"运动: {moving_energy:.0f} | "
            f"静止: {static_energy:.0f}"
        )

        # 状态驱动逻辑
        self._handle_state(state, distance, moving_energy, static_energy)

    def _on_connection_change(self, connected: bool) -> None:
        """串口连接状态变化"""
        if connected:
            logger.info("串口已连接")
            self._tray.show_message("串口已连接", "ESP32 传感器已连接")
        else:
            logger.warning("串口已断开，尝试重连...")
            self._tray.show_message(
                "串口已断开",
                "正在尝试重新连接...",
                QSystemTrayIcon.MessageIcon.Warning,  # type: ignore
            )

    def _on_serial_error(self, error: str) -> None:
        """串口错误回调"""
        logger.error(f"串口错误: {error}")

    # ------------------------------------------------------------------
    # 状态处理逻辑
    # ------------------------------------------------------------------

    def _handle_state(
        self,
        state: str,
        distance: float,
        moving_energy: float,
        static_energy: float,
    ) -> None:
        """
        核心状态处理逻辑 - 根据 ESP32 状态驱动 PC 端动作。

        ESP32 状态        PC 响应
        ─────────────────────────────────
        NORMAL            关闭遮罩 / 恢复桌面
        HUMAN_DETECTED    托盘变色（黄色）
        APPROACHING       半透明遮罩 ~40% + 文字提示
        SUSPECTED_PEEPING 半透明遮罩 ~60% + 警告
        PRIVACY_PROTECT   全屏遮罩 ~80% + 警告文字 + 倒计时
        ALARM             全屏遮罩 ~90% + 声音 + 锁屏
        """
        if state == "NORMAL":
            self._on_normal()
        elif state == "HUMAN_DETECTED":
            self._on_human_detected()
        elif state == "APPROACHING":
            self._on_approaching(distance)
        elif state == "SUSPECTED_PEEPING":
            self._on_suspected_peeping(distance)
        elif state == "PRIVACY_PROTECT":
            self._on_privacy_protect(distance)
        elif state == "ALARM":
            self._on_alarm(distance)
        else:
            logger.warning(f"未知状态: {state}")

    def _on_normal(self) -> None:
        """NORMAL: 恢复桌面"""
        self._stop_countdown()
        self._hide_overlays()
        self._sound_alarm.stop()
        self._lock_screen_triggered = False

    def _on_human_detected(self) -> None:
        """HUMAN_DETECTED: 仅托盘变色，无遮罩"""
        self._stop_countdown()
        self._hide_overlays()
        self._sound_alarm.stop()

    def _on_approaching(self, distance: float) -> None:
        """APPROACHING: 半透明遮罩 ~40% + 提示"""
        self._stop_countdown()
        self._update_overlays("APPROACHING", distance, 0, 0)
        self._show_overlays()
        self._sound_alarm.stop()
        self._lock_screen_triggered = False

    def _on_suspected_peeping(self, distance: float) -> None:
        """SUSPECTED_PEEPING: 遮罩 ~60% + 警告"""
        self._stop_countdown()
        self._update_overlays("SUSPECTED_PEEPING", distance, 0, 0)
        self._show_overlays()
        self._sound_alarm.stop()

    def _on_privacy_protect(self, distance: float) -> None:
        """PRIVACY_PROTECT: 遮罩 ~80% + 倒计时"""
        self._update_overlays("PRIVACY_PROTECT", distance, 0, 0)
        self._show_overlays()
        self._sound_alarm.stop()
        # 开始锁屏倒计时（如果尚未开始）
        if not self._countdown_active:
            self._start_countdown()
            logger.info(f"隐私保护: 开始 {self._lock_screen_delay}s 锁屏倒计时")

    def _on_alarm(self, distance: float) -> None:
        """ALARM: 遮罩 ~90% + 声音 + 锁屏"""
        self._update_overlays("ALARM", distance, 0, 0)
        self._show_overlays()

        # 播放报警声音
        if not self._sound_alarm.is_playing:
            alarm_cfg = self._config.get_alarm_config()
            self._sound_alarm.play(loop=alarm_cfg.get("sound_loop", True))

        # 锁屏（只执行一次）
        if not self._lock_screen_triggered:
            self._lock_screen_triggered = True
            logger.warning("ALARM 状态: 触发锁屏")
            self._execute_lock_screen()

    # ------------------------------------------------------------------
    # 锁屏
    # ------------------------------------------------------------------

    def _trigger_lock_screen(self) -> None:
        """用户通过菜单触发的锁屏"""
        self._execute_lock_screen()

    def _execute_lock_screen(self) -> None:
        """执行跨平台锁屏"""
        logger.warning("执行锁屏操作...")
        self._lock_timer.stop()

        success, msg = lock_screen()
        if not success:
            logger.error(f"锁屏失败: {msg}")
            self._tray.show_message("锁屏失败", msg, QSystemTrayIcon.MessageIcon.Critical)  # type: ignore

    # ------------------------------------------------------------------
    # 看门狗
    # ------------------------------------------------------------------

    def _watchdog_check(self) -> None:
        """看门狗定时检查 - 数据超时则恢复默认状态"""
        if self._watchdog.check_timeout():
            # 超时时间：5秒没有收到任何数据
            last_state = self._watchdog.last_state
            if last_state != "NORMAL":
                logger.warning(f"看门狗触发: {last_state} → NORMAL (数据超时)")
                self._on_normal()
                self._tray.set_state("NORMAL")
                self._tray.set_tooltip("隐私保护 - 未收到传感器数据")
                self._watchdog.update("NORMAL")

    # ------------------------------------------------------------------
    # 声音初始化
    # ------------------------------------------------------------------

    def _init_sound(self) -> None:
        """初始化报警声音"""
        alarm_cfg = self._config.get_alarm_config()
        sound_file = alarm_cfg.get("sound_file", "alarm.wav")
        volume = alarm_cfg.get("sound_volume", 0.7)

        # 尝试在多个路径查找声音文件
        search_paths = [
            sound_file,
            os.path.join(os.path.dirname(self._config_path), sound_file),
            os.path.join(os.path.dirname(__file__), sound_file),
        ]

        found = False
        for path in search_paths:
            if os.path.exists(path):
                self._sound_alarm.initialize(path, volume)
                found = True
                break

        if not found:
            logger.warning(f"报警声音文件未找到 ({sound_file})，报警时将使用系统蜂鸣")
            self._sound_alarm.initialize("", volume)

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------

    def _setup_logging(self) -> None:
        """配置日志系统"""
        level_str = self._config.get("logging", "level", default="INFO")
        level = getattr(logging, level_str.upper(), logging.INFO)
        log_file = self._config.get("logging", "file", default="peep_prevention.log")
        max_mb = int(self._config.get("logging", "max_size_mb", default=10))
        backup = int(self._config.get("logging", "backup_count", default=3))

        # 格式
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # 控制台 handler
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        console.setLevel(level)

        # 文件 handler（带轮转）
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_mb * 1024 * 1024, backupCount=backup, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)

        # 根 logger
        root = logging.getLogger()
        root.setLevel(level)
        root.addHandler(console)
        root.addHandler(file_handler)

        # 第三方库降噪
        logging.getLogger("PyQt6").setLevel(logging.WARNING)
        logging.getLogger("serial").setLevel(logging.WARNING)

        logger.info(f"日志系统初始化: level={level_str}, file={log_file}")

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def _cleanup(self) -> None:
        """程序退出时的清理工作"""
        logger.info("正在清理资源...")
        self._watchdog_timer.stop()
        self._lock_timer.stop()
        self._sound_alarm.cleanup()
        self._serial_reader.stop()
        self._tray.cleanup()

        for overlay in self._overlays:
            overlay.close()

        logger.info("程序已退出")


# ==================================================================
# 启动入口
# ==================================================================
def main() -> None:
    """程序入口"""
    parser = argparse.ArgumentParser(
        description="SmartOffice PeepPrevention - PC端隐私保护程序",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                    # 使用默认配置
  python main.py -c my_config.yaml  # 使用自定义配置
  python main.py -d                 # 调试模式
        """,
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)",
    )
    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        help="启用 DEBUG 日志级别",
    )
    args = parser.parse_args()

    # 配置文件路径
    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(os.path.dirname(__file__), config_path)

    # 如果是 DEBUG 模式，先设置日志，再初始化 App
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] %(levelname)-7s %(name)s - %(message)s")
        logger = logging.getLogger("PeepPrevention")
        logger.info("DEBUG 模式已启用")

    try:
        app = PeepPreventionApp(config_path=config_path)
        app.run()
    except Exception as e:
        logger.critical(f"程序启动失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
