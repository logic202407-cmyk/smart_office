"""
tray_app.py - 系统托盘 + 右键菜单 + 状态图标
================================================
功能：
  1. 系统托盘运行（后台常驻）
  2. 右键菜单：显示/隐藏遮罩、锁屏、退出
  3. 图标根据状态动态变色（绿→黄→橙→红）
  4. 状态变更时气泡通知
  5. 开机自启选项

图标生成策略（不依赖外部图片文件）：
  - 使用 QPixmap + QPainter 绘制状态圆形图标
  - 颜色映射：NORMAL=绿色, HUMAN_DETECTED=黄色,
               APPROACHING=橙色, SUSPECTED_PEEPING=深橙,
               PRIVACY_PROTECT=红色, ALARM=深红闪烁
"""

import logging
import os
import sys
from typing import Callable, Optional

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QPainter,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QMessageBox

logger = logging.getLogger(__name__)


# ==================================================================
# 常量
# ==================================================================

# 状态→颜色映射 (R, G, B)
STATE_COLORS = {
    "NORMAL": (0, 200, 0),           # 绿色
    "HUMAN_DETECTED": (200, 200, 0), # 黄色
    "APPROACHING": (255, 140, 0),    # 橙色
    "SUSPECTED_PEEPING": (230, 80, 0),  # 深橙
    "PRIVACY_PROTECT": (220, 30, 30),   # 红色
    "ALARM": (255, 0, 0),            # 亮红
}

# 托盘图标尺寸
ICON_SIZE = 32


# ==================================================================
# 托盘应用
# ==================================================================
class TrayApp:
    """
    系统托盘应用程序。

    用法:
        app = QApplication(sys.argv)
        tray = TrayApp(app)
        tray.set_state("APPROACHING")
        tray.show_message("警告", "有人靠近")
        sys.exit(app.exec())
    """

    def __init__(
        self,
        app: QApplication,
        on_show_overlay: Optional[Callable] = None,
        on_hide_overlay: Optional[Callable] = None,
        on_lock_screen: Optional[Callable] = None,
        on_quit: Optional[Callable] = None,
        show_toast: bool = True,
    ) -> None:
        """
        参数:
            app: QApplication 实例
            on_show_overlay: 显示遮罩回调
            on_hide_overlay: 隐藏遮罩回调
            on_lock_screen: 锁屏回调
            on_quit: 退出程序回调
            show_toast: 状态变化时是否显示气泡通知
        """
        self._app = app
        self._on_show_overlay = on_show_overlay
        self._on_hide_overlay = on_hide_overlay
        self._on_lock_screen = on_lock_screen
        self._on_quit = on_quit
        self._show_toast = show_toast

        # 当前状态
        self._current_state: str = "NORMAL"
        self._flip_flop: bool = False  # 报警闪烁用

        # 创建托盘图标
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("系统托盘不可用")
            return

        self._tray_icon = QSystemTrayIcon()
        self._tray_icon.setToolTip("隐私保护程序 - 运行中")

        # 生成默认图标（绿色）
        self._update_icon("NORMAL")

        # 构建右键菜单
        self._build_menu()

        # 托盘图标显示
        self._tray_icon.show()

        # 双击恢复主窗口
        self._tray_icon.activated.connect(self._on_activated)

        # 报警闪烁定时器（ALARM 状态时闪烁图标）
        self._blink_timer = QTimer()
        self._blink_timer.timeout.connect(self._blink)

        logger.info("系统托盘已创建")

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        """
        更新托盘图标状态。

        参数:
            state: 状态名称 (NORMAL / HUMAN_DETECTED / APPROACHING / ...)
        """
        if state == self._current_state and state != "ALARM":
            return

        old_state = self._current_state
        self._current_state = state

        # 更新图标
        self._update_icon(state)

        # 报警状态：启动闪烁；其他状态：停止闪烁
        if state == "ALARM":
            self._blink_timer.start(500)  # 500ms 闪烁
        else:
            self._blink_timer.stop()

        # 气泡通知
        if self._show_toast and state != old_state:
            if state == "SUSPECTED_PEEPING":
                self.show_message("⚠️ 疑似窥视", "检测到有人正在窥视您的屏幕！", QSystemTrayIcon.MessageIcon.Warning)
            elif state == "ALARM":
                self.show_message("🚨 报警中", "屏幕即将锁定！", QSystemTrayIcon.MessageIcon.Critical)
            elif state == "NORMAL" and old_state != "NORMAL":
                self.show_message("✅ 已恢复", "隐私保护已解除", QSystemTrayIcon.MessageIcon.Information)

    def show_message(self, title: str, message: str, icon=QSystemTrayIcon.MessageIcon.Information) -> None:
        """显示托盘气泡通知"""
        if self._tray_icon and self._tray_icon.supportsMessages():
            self._tray_icon.showMessage(title, message, icon, 3000)

    def set_tooltip(self, text: str) -> None:
        """设置托盘图标悬浮提示"""
        if self._tray_icon:
            self._tray_icon.setToolTip(text)

    # ------------------------------------------------------------------
    # 内部方法 - 图标生成
    # ------------------------------------------------------------------

    def _update_icon(self, state: str) -> None:
        """根据状态生成并设置托盘图标"""
        color = STATE_COLORS.get(state, (100, 100, 100))
        pixmap = self._generate_icon(color)
        if pixmap:
            self._tray_icon.setIcon(QIcon(pixmap))

    def _generate_icon(self, color_rgb: tuple) -> QPixmap:
        """
        生成圆形状态图标。

        参数:
            color_rgb: (R, G, B) 颜色值

        返回:
            QPixmap 图标
        """
        pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r, g, b = color_rgb
        # 绘制外圈
        painter.setBrush(QBrush(QColor(r, g, b, 200)))
        painter.setPen(QPen(QColor(r, g, b, 255), 2))
        painter.drawEllipse(2, 2, ICON_SIZE - 4, ICON_SIZE - 4)

        # 绘制内圈高光
        painter.setBrush(QBrush(QColor(min(255, r + 60), min(255, g + 60), min(255, b + 60), 100)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(6, 6, ICON_SIZE - 12, ICON_SIZE - 12)

        painter.end()
        return pixmap

    # ------------------------------------------------------------------
    # 内部方法 - 右键菜单
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        """构建右键菜单"""
        menu = QMenu()

        # 状态显示（不可点击）
        self._status_action = QAction("● 状态: 正常")
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)

        menu.addSeparator()

        # 显示遮罩
        show_action = QAction("🛡️ 显示遮罩")
        show_action.triggered.connect(lambda: self._call(self._on_show_overlay))
        menu.addAction(show_action)

        # 隐藏遮罩
        hide_action = QAction("✅ 隐藏遮罩")
        hide_action.triggered.connect(lambda: self._call(self._on_hide_overlay))
        menu.addAction(hide_action)

        menu.addSeparator()

        # 立即锁屏
        lock_action = QAction("🔒 立即锁屏")
        lock_action.triggered.connect(lambda: self._call(self._on_lock_screen))
        menu.addAction(lock_action)

        menu.addSeparator()

        # 开机自启（toggle）
        self._auto_start_action = QAction("☀️ 开机自启")
        self._auto_start_action.setCheckable(True)
        self._auto_start_action.setChecked(self._is_auto_start_enabled())
        self._auto_start_action.triggered.connect(self._toggle_auto_start)
        menu.addAction(self._auto_start_action)

        menu.addSeparator()

        # 退出
        quit_action = QAction("🚪 退出程序")
        quit_action.triggered.connect(self._on_quit_action)
        menu.addAction(quit_action)

        if self._tray_icon:
            self._tray_icon.setContextMenu(menu)

    def _update_menu_status(self, state: str) -> None:
        """更新菜单中的状态显示"""
        if hasattr(self, "_status_action"):
            name_map = {
                "NORMAL": "正常",
                "HUMAN_DETECTED": "检测到人体",
                "APPROACHING": "正在接近",
                "SUSPECTED_PEEPING": "疑似窥视",
                "PRIVACY_PROTECT": "隐私保护中",
                "ALARM": "报警中",
            }
            name = name_map.get(state, state)
            self._status_action.setText(f"● 状态: {name}")

    # ------------------------------------------------------------------
    # 内部方法 - 事件处理
    # ------------------------------------------------------------------

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """托盘图标被激活（点击）"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # 双击：切换遮罩
            if self._current_state in ("NORMAL", "HUMAN_DETECTED"):
                self._call(self._on_show_overlay)
            else:
                self._call(self._on_hide_overlay)

    def _blink(self) -> None:
        """报警闪烁"""
        self._flip_flop = not self._flip_flop
        if self._flip_flop:
            color = (255, 255, 255)  # 白色闪烁
        else:
            color = STATE_COLORS.get(self._current_state, (255, 0, 0))
        pixmap = self._generate_icon(color)
        if self._tray_icon:
            self._tray_icon.setIcon(QIcon(pixmap))

    def _on_quit_action(self) -> None:
        """退出菜单项点击"""
        # 确认对话框
        reply = QMessageBox.question(
            None,
            "确认退出",
            "确定要退出隐私保护程序吗？\n退出后屏幕将不再受到保护。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._call(self._on_quit)
        else:
            logger.info("用户取消退出")

    # ------------------------------------------------------------------
    # 开机自启
    # ------------------------------------------------------------------

    @staticmethod
    def _is_auto_start_enabled() -> bool:
        """检查是否已启用开机自启"""
        if sys.platform == "win32":
            import winreg

            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0,
                    winreg.KEY_READ,
                )
                winreg.QueryValueEx(key, "PeepPrevention")
                winreg.CloseKey(key)
                return True
            except (FileNotFoundError, OSError):
                return False
        elif sys.platform == "darwin":
            # macOS: 检查 ~/Library/LaunchAgents
            plist_path = os.path.expanduser("~/Library/LaunchAgents/com.nous.peep-prevention.plist")
            return os.path.exists(plist_path)
        else:
            # Linux: 检查 autostart
            desktop_path = os.path.expanduser("~/.config/autostart/peep-prevention.desktop")
            return os.path.exists(desktop_path)

    def _toggle_auto_start(self, enabled: bool) -> None:
        """切换开机自启"""
        try:
            self._set_auto_start(enabled)
            logger.info(f"开机自启: {'已启用' if enabled else '已禁用'}")
            if self._tray_icon:
                self._tray_icon.showMessage(
                    "开机自启",
                    f"已{'启用' if enabled else '禁用'}开机自启",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
        except Exception as e:
            logger.error(f"设置开机自启失败: {e}")
            self._auto_start_action.setChecked(not enabled)

    @staticmethod
    def _set_auto_start(enabled: bool) -> None:
        """设置开机自启（跨平台）"""
        if sys.platform == "win32":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            if enabled:
                exe_path = sys.executable
                script_path = os.path.abspath(sys.argv[0])
                winreg.SetValueEx(key, "PeepPrevention", 0, winreg.REG_SZ,
                                  f'"{exe_path}" "{script_path}"')
            else:
                try:
                    winreg.DeleteValue(key, "PeepPrevention")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        elif sys.platform == "darwin":
            plist_dir = os.path.expanduser("~/Library/LaunchAgents")
            plist_path = os.path.join(plist_dir, "com.nous.peep-prevention.plist")
            if enabled:
                os.makedirs(plist_dir, exist_ok=True)
                plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nous.peep-prevention</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{os.path.abspath(sys.argv[0])}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>"""
                with open(plist_path, "w") as f:
                    f.write(plist_content)
            else:
                if os.path.exists(plist_path):
                    os.remove(plist_path)
        else:
            # Linux autostart .desktop
            autostart_dir = os.path.expanduser("~/.config/autostart")
            desktop_path = os.path.join(autostart_dir, "peep-prevention.desktop")
            if enabled:
                os.makedirs(autostart_dir, exist_ok=True)
                desktop_content = f"""[Desktop Entry]
Type=Application
Name=PeepPrevention
Exec={sys.executable} {os.path.abspath(sys.argv[0])}
Terminal=false
X-GNOME-Autostart-enabled=true
"""
                with open(desktop_path, "w") as f:
                    f.write(desktop_content)
                os.chmod(desktop_path, 0o755)
            else:
                if os.path.exists(desktop_path):
                    os.remove(desktop_path)

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _call(func: Optional[Callable]) -> None:
        """安全调用回调函数"""
        if func:
            try:
                func()
            except Exception as e:
                logger.error(f"回调执行失败: {e}")

    def cleanup(self) -> None:
        """清理资源"""
        self._blink_timer.stop()
        if self._tray_icon:
            self._tray_icon.hide()
        logger.info("托盘已清理")
