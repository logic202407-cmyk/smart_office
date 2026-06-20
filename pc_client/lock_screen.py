"""
lock_screen.py - 跨平台锁屏模块
==================================
功能：
  1. Windows: 调用 LockWorkStation()
  2. macOS:   使用 osascript 命令
  3. Linux:   使用 loginctl 或 gnome-screensaver-command

所有平台均返回 (success: bool, message: str)
"""

import sys
import logging
import subprocess
from typing import Tuple

logger = logging.getLogger(__name__)


def lock_screen() -> Tuple[bool, str]:
    """
    锁屏（跨平台实现）。

    返回:
        (True, "成功信息") 或 (False, "错误信息")
    """
    platform = sys.platform
    logger.info(f"尝试锁屏 (平台: {platform})")

    if platform == "win32":
        return _lock_windows()
    elif platform == "darwin":
        return _lock_macos()
    else:
        return _lock_linux()


# ------------------------------------------------------------------
# Windows 锁屏
# ------------------------------------------------------------------
def _lock_windows() -> Tuple[bool, str]:
    """Windows 锁屏 - 直接调用 user32.LockWorkStation()"""
    try:
        import ctypes

        ctypes.windll.user32.LockWorkStation()
        logger.info("Windows 锁屏成功")
        return (True, "锁屏已触发")
    except Exception as e:
        logger.error(f"Windows 锁屏失败: {e}")
        return (False, f"锁屏失败: {e}")


# ------------------------------------------------------------------
# macOS 锁屏
# ------------------------------------------------------------------
def _lock_macos() -> Tuple[bool, str]:
    """macOS 锁屏 - 使用 osascript 调用快速用户切换"""
    try:
        # 方法1: 通过登录窗口锁屏
        cmd = [
            "osascript",
            "-e",
            'tell application "System Events" to keystroke "q" using {command down, control down}',
        ]
        # 方法2: 直接启动屏幕保护（密码保护开启时等同于锁屏）
        # cmd = ["open", "-a", "ScreenSaverEngine"]
        subprocess.run(cmd, timeout=5, check=False)
        logger.info("macOS 锁屏命令已执行")
        return (True, "锁屏已触发")
    except Exception as e:
        logger.error(f"macOS 锁屏失败: {e}")
        return (False, f"锁屏失败: {e}")


# ------------------------------------------------------------------
# Linux 锁屏
# ------------------------------------------------------------------
def _lock_linux() -> Tuple[bool, str]:
    """Linux 锁屏 - 尝试多种方式"""
    methods = [
        # 方法1: loginctl (systemd)
        (["loginctl", "lock-session"], "loginctl"),
        # 方法2: gnome-screensaver
        (["gnome-screensaver-command", "-l"], "gnome-screensaver"),
        # 方法3: xdg-screensaver
        (["xdg-screensaver", "lock"], "xdg-screensaver"),
        # 方法4: light-locker-command
        (["light-locker-command", "-l"], "light-locker"),
    ]

    for cmd, name in methods:
        try:
            result = subprocess.run(
                cmd,
                timeout=5,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                logger.info(f"Linux 锁屏成功 (方法: {name})")
                return (True, f"锁屏已触发 ({name})")
            logger.debug(f"锁屏方法 {name} 失败 (code={result.returncode}): {result.stderr.strip()}")
        except FileNotFoundError:
            logger.debug(f"锁屏方法 {name} 不可用 (未找到命令)")
            continue
        except Exception as e:
            logger.debug(f"锁屏方法 {name} 异常: {e}")
            continue

    logger.error("所有 Linux 锁屏方法均失败")
    return (False, "未找到可用的锁屏命令，请安装 loginctl / gnome-screensaver-command / xdg-screensaver")
