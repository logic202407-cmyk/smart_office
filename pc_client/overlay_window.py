"""
overlay_window.py - 全屏遮罩窗口（PyQt6）
============================================
功能：
  1. 全屏无边框窗口，置顶显示
  2. 6级透明度控制
  3. 显示状态名称、距离、警告图标（emoji）、警告文字
  4. 倒计时进度条 → 自动锁屏
  5. 解锁按钮（点击后关闭遮罩）
  6. 多显示器支持（每个显示器一个实例）

遮罩级别映射:
  NORMAL / HUMAN_DETECTED : 不显示遮罩（透明）
  APPROACHING              : ~40% 透明度 + 提示文字
  SUSPECTED_PEEPING        : ~60% 透明度 + 弹窗警告
  PRIVACY_PROTECT          : ~80% 透明度 + 警告文字
  ALARM                    : ~90% 透明度 + 声音 + 锁屏倒计时
"""

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont, QPainter, QBrush, QPen, QAction, QShowEvent
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QProgressBar,
    QSizePolicy,
)

logger = logging.getLogger(__name__)


# ==================================================================
# 常量
# ==================================================================

# 状态图标映射
STATE_ICONS = {
    "NORMAL": "✅",
    "HUMAN_DETECTED": "👤",
    "APPROACHING": "⚠️",
    "SUSPECTED_PEEPING": "🚨",
    "PRIVACY_PROTECT": "🛡️",
    "ALARM": "🔴",
}

# 状态中文名称
STATE_NAMES_CN = {
    "NORMAL": "正常",
    "HUMAN_DETECTED": "检测到人体",
    "APPROACHING": "正在接近",
    "SUSPECTED_PEEPING": "疑似窥视",
    "PRIVACY_PROTECT": "隐私保护中",
    "ALARM": "报警中",
}

# 状态建议文字
STATE_MESSAGES = {
    "NORMAL": "",
    "HUMAN_DETECTED": "检测到有人靠近",
    "APPROACHING": "请注意，有人正在靠近您的屏幕",
    "SUSPECTED_PEEPING": "警告！疑似有人在窥视您的屏幕！",
    "PRIVACY_PROTECT": "隐私保护已启动，屏幕已遮挡",
    "ALARM": "⚠️ 严重警告！屏幕将被锁定！",
}


# ==================================================================
# 信号桥 - 跨线程通信
# ==================================================================
class OverlaySignals(QObject):
    """遮罩窗口信号（用于跨线程更新 UI）"""

    update_state = pyqtSignal(str, float, float, float)  # state, distance, moving_energy, static_energy
    show_overlay = pyqtSignal()
    hide_overlay = pyqtSignal()
    update_countdown = pyqtSignal(int)  # 倒计时秒数
    set_countdown_visible = pyqtSignal(bool)


# ==================================================================
# 遮罩窗口
# ==================================================================
class OverlayWindow(QWidget):
    """
    单个显示器上的全屏遮罩窗口。

    多显示器用法：为每个 QScreen 创建一个实例。
    """

    def __init__(
        self,
        screen_index: int = 0,
        opacity_levels: Optional[dict] = None,
        overlay_color: tuple = (0, 0, 0),
        warning_color: tuple = (255, 50, 50),
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        参数:
            screen_index: 显示器索引（仅用于日志标注）
            opacity_levels: 各状态的透明度映射
            overlay_color: 遮罩颜色 (R, G, B)
            warning_color: 警告文字颜色 (R, G, B)
            parent: 父窗口
        """
        super().__init__(parent)
        self._screen_index = screen_index
        self._opacity_levels = opacity_levels or {}
        self._overlay_color = overlay_color
        self._warning_color = warning_color

        # 状态
        self._current_state: str = "NORMAL"
        self._distance: float = 0.0
        self._moving_energy: float = 0.0
        self._static_energy: float = 0.0
        self._countdown_sec: int = 0
        self._show_countdown: bool = False

        # 信号
        self.signals = OverlaySignals()
        self.signals.update_state.connect(self._on_update_state)
        self.signals.show_overlay.connect(self._show)
        self.signals.hide_overlay.connect(self._hide)
        self.signals.update_countdown.connect(self._on_countdown)
        self.signals.set_countdown_visible.connect(self._set_countdown_visible)

        # 倒计时定时器
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._tick_countdown)
        self._countdown_remaining: int = 0

        # 构建 UI
        self._build_ui()

        # 窗口属性
        self.setWindowTitle(f"PeepPrevention-{screen_index}")
        # 窗口标记：无边框、置顶、全屏
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        logger.info(f"OverlayWindow-{screen_index} 初始化完成")

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """构建遮罩 UI"""
        # 主布局
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(40, 40, 40, 40)
        self._main_layout.setSpacing(20)
        self._main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- 状态图标 ---
        self._icon_label = QLabel("🛡️", self)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_font = QFont("Segoe UI Emoji", 72)
        self._icon_label.setFont(icon_font)
        self._main_layout.addWidget(self._icon_label)

        # --- 状态名称 ---
        self._state_label = QLabel("隐私保护中", self)
        self._state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        state_font = QFont("Microsoft YaHei", 36, QFont.Weight.Bold)
        self._state_label.setFont(state_font)
        self._state_label.setStyleSheet("color: white;")
        self._main_layout.addWidget(self._state_label)

        # --- 状态说明 ---
        self._message_label = QLabel("屏幕已遮挡，保护您的隐私", self)
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_font = QFont("Microsoft YaHei", 18)
        self._message_label.setFont(msg_font)
        self._message_label.setStyleSheet("color: #CCCCCC;")
        self._main_layout.addWidget(self._message_label)

        # --- 距离 & 能量信息 ---
        self._info_label = QLabel("", self)
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_font = QFont("Microsoft YaHei", 16)
        self._info_label.setFont(info_font)
        self._info_label.setStyleSheet("color: #AAAAAA;")
        self._main_layout.addWidget(self._info_label)

        # --- 倒计时进度条 ---
        self._progress_bar = QProgressBar(self)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFixedHeight(40)
        self._progress_bar.setFixedWidth(500)
        self._progress_bar.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self._progress_bar.setStyleSheet(
            """
            QProgressBar {
                border: 2px solid #FF3333;
                border-radius: 10px;
                background-color: rgba(0, 0, 0, 100);
                text-align: center;
                color: white;
                font-size: 16px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF4444, stop:1 #FF8800
                );
                border-radius: 8px;
            }
            """
        )
        # 居中：放在一个水平居中布局中
        progress_container = QHBoxLayout()
        progress_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_container.addWidget(self._progress_bar)
        self._main_layout.addLayout(progress_container)

        # --- 解锁按钮 ---
        self._unlock_btn = QPushButton("🔓 解锁屏幕", self)
        self._unlock_btn.setFixedSize(280, 64)
        self._unlock_btn.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        self._unlock_btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 40);
                color: white;
                border: 2px solid rgba(255, 255, 255, 100);
                border-radius: 32px;
                padding: 8px 24px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 80);
                border: 2px solid rgba(255, 255, 255, 180);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 120);
            }
            """
        )
        self._unlock_btn.clicked.connect(self._on_unlock_clicked)
        # 按钮也居中
        btn_container = QHBoxLayout()
        btn_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_container.addWidget(self._unlock_btn)
        self._main_layout.addLayout(btn_container)

        # 默认隐藏
        self._progress_bar.hide()
        self._unlock_btn.hide()

    # ------------------------------------------------------------------
    # 显示 / 隐藏 / 更新
    # ------------------------------------------------------------------

    def show_on_screen(self, screen_geometry) -> None:
        """
        在指定屏幕上全屏显示。

        参数:
            screen_geometry: QRect(x, y, width, height)
        """
        self.setGeometry(screen_geometry)
        self.show()

    def _show(self) -> None:
        """显示遮罩"""
        self.show()
        self.raise_()
        self.activateWindow()

    def _hide(self) -> None:
        """隐藏遮罩"""
        self.hide()
        self._countdown_timer.stop()

    def update_state(
        self,
        state: str,
        distance: float,
        moving_energy: float,
        static_energy: float,
    ) -> None:
        """通过信号更新状态（线程安全）"""
        self.signals.update_state.emit(state, distance, moving_energy, static_energy)

    def _on_update_state(
        self,
        state: str,
        distance: float,
        moving_energy: float,
        static_energy: float,
    ) -> None:
        """收到状态更新"""
        self._current_state = state
        self._distance = distance
        self._moving_energy = moving_energy
        self._static_energy = static_energy

        # 更新 UI
        self._update_overlay()

    def _update_overlay(self) -> None:
        """根据当前状态更新遮罩 UI"""
        state = self._current_state

        # 更新图标
        icon = STATE_ICONS.get(state, "🛡️")
        self._icon_label.setText(icon)

        # 更新状态名称
        name = STATE_NAMES_CN.get(state, state)
        self._state_label.setText(name)

        # 更新提示信息
        msg = STATE_MESSAGES.get(state, "")
        self._message_label.setText(msg)

        # 更新距离/能量信息
        info_parts = []
        if self._distance > 0:
            info_parts.append(f"距离: {self._distance:.0f} cm")
        if self._moving_energy > 0:
            info_parts.append(f"运动能量: {self._moving_energy:.0f}")
        if self._static_energy > 0:
            info_parts.append(f"静止能量: {self._static_energy:.0f}")
        self._info_label.setText(" | ".join(info_parts))

        # 更新透明度
        alpha = self._opacity_levels.get(state, 0)
        self.setWindowOpacity(max(0.0, min(1.0, alpha / 255.0)))

        # 根据状态显示/隐藏 UI 元素
        need_warning = state in ("SUSPECTED_PEEPING", "PRIVACY_PROTECT", "ALARM")
        self._progress_bar.setVisible(need_warning and self._show_countdown)
        self._unlock_btn.setVisible(need_warning)

        logger.debug(f"遮罩更新: state={state}, alpha={alpha}")

    def start_countdown(self, seconds: int) -> None:
        """启动锁屏倒计时"""
        self._countdown_remaining = seconds
        self._show_countdown = True
        self.signals.set_countdown_visible.emit(True)
        self.signals.update_countdown.emit(seconds)
        self._countdown_timer.start(1000)  # 每秒更新

    def stop_countdown(self) -> None:
        """停止倒计时"""
        self._show_countdown = False
        self._countdown_timer.stop()
        self.signals.set_countdown_visible.emit(False)

    def _tick_countdown(self) -> None:
        """倒计时 tick"""
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._countdown_timer.stop()
        self.signals.update_countdown.emit(max(0, self._countdown_remaining))

    def _on_countdown(self, remaining: int) -> None:
        """更新倒计时 UI"""
        total = self._opacity_levels.get("_countdown_total", 15)
        if total <= 0:
            total = 15
        progress = int((remaining / total) * 100)
        self._progress_bar.setValue(progress)
        self._progress_bar.setFormat(f"自动锁屏: {remaining}s")

    def _set_countdown_visible(self, visible: bool) -> None:
        """设置倒计时可见性"""
        self._show_countdown = visible
        self._progress_bar.setVisible(visible)

    def _on_unlock_clicked(self) -> None:
        """解锁按钮点击处理"""
        logger.info(f"用户点击解锁 (Screen-{self._screen_index})")
        self.stop_countdown()
        # 隐藏遮罩，重置为 NORMAL
        self._on_update_state("NORMAL", 0, 0, 0)
        self._hide()
        # 发射解锁信号（在外层连接）
        if hasattr(self, "unlock_requested"):
            self.unlock_requested.emit()  # type: ignore

    def closeEvent(self, event) -> None:
        """重写关闭事件 - 确保清理"""
        self._countdown_timer.stop()
        super().closeEvent(event)

    def __repr__(self) -> str:
        return f"OverlayWindow(screen={self._screen_index}, state={self._current_state})"
