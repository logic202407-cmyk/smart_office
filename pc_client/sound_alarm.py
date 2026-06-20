"""
sound_alarm.py - 报警声音播放模块
====================================
功能：
  1. 播放报警音频文件（WAV/MP3）
  2. 循环播放 / 停止
  3. 音量控制
  4. 异步播放（不阻塞主线程）
  5. fallback: 使用 QBeep() 或系统蜂鸣

使用策略：
  - 首选 pygame.mixer（跨平台，wav/mp3 支持好）
  - 回退到 winsound（Windows）或 system beep（macOS/Linux）
"""

import os
import sys
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class SoundAlarm:
    """报警声音播放器"""

    def __init__(self) -> None:
        self._player: Optional["_PygamePlayer"] = None
        self._fallback: Optional["_FallbackPlayer"] = None
        self._lock = threading.Lock()
        self._is_playing = False
        self._initialized = False

    def initialize(self, sound_file: str, volume: float = 0.7) -> bool:
        """
        初始化音频设备并加载声音文件。

        参数:
            sound_file: 音频文件路径
            volume: 音量 0.0-1.0

        返回:
            True 表示初始化成功
        """
        self.stop()

        # 尝试 pygame
        try:
            self._player = _PygamePlayer()
            success = self._player.initialize(sound_file, volume)
            if success:
                self._initialized = True
                logger.info(f"音频初始化成功 (pygame): {sound_file}")
                return True
        except Exception as e:
            logger.warning(f"pygame 初始化失败: {e}")
            self._player = None

        # fallback
        logger.info("使用 fallback 音频播放器")
        self._fallback = _FallbackPlayer()

        # 检查文件是否存在
        if sound_file and os.path.exists(sound_file):
            self._fallback.set_file(sound_file)
        self._initialized = True
        return True

    def play(self, loop: bool = True) -> None:
        """开始播放报警声音"""
        if not self._initialized:
            logger.warning("播放器未初始化")
            return

        with self._lock:
            self._is_playing = True

        if self._player:
            self._player.play(loop)
        elif self._fallback:
            self._fallback.play(loop)

        logger.info(f"报警声音开始播放 (loop={loop})")

    def stop(self) -> None:
        """停止播放报警声音"""
        with self._lock:
            self._is_playing = False

        if self._player:
            self._player.stop()
        if self._fallback:
            self._fallback.stop()

        logger.info("报警声音已停止")

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def cleanup(self) -> None:
        """释放资源"""
        self.stop()
        if self._player:
            self._player.cleanup()
        logger.info("音频资源已释放")


# ==================================================================
# pygame 播放器
# ==================================================================
class _PygamePlayer:
    def __init__(self) -> None:
        self._sound_file: Optional[str] = None
        self._sound = None

    def initialize(self, sound_file: str, volume: float) -> bool:
        import pygame

        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        if not os.path.exists(sound_file):
            logger.warning(f"声音文件不存在: {sound_file}")
            return False
        self._sound_file = sound_file
        self._sound = pygame.mixer.Sound(sound_file)
        self._sound.set_volume(max(0.0, min(1.0, volume)))
        return True

    def play(self, loop: bool) -> None:
        if self._sound:
            # pygame: loops=-1 无限循环, loops=0 播放一次
            loops = -1 if loop else 0
            self._sound.play(loops=loops)

    def stop(self) -> None:
        if self._sound:
            self._sound.stop()

    def cleanup(self) -> None:
        import pygame

        self.stop()
        if self._sound:
            self._sound = None
        try:
            pygame.mixer.quit()
        except Exception:
            pass


# ==================================================================
# Fallback 播放器（Windows: winsound / 其他: print beep）
# ==================================================================
class _FallbackPlayer:
    def __init__(self) -> None:
        self._sound_file: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def set_file(self, path: str) -> None:
        self._sound_file = path

    def play(self, loop: bool) -> None:
        self._stop_event.clear()
        if sys.platform == "win32":
            self._thread = threading.Thread(
                target=self._beep_windows, daemon=True
            )
        else:
            self._thread = threading.Thread(
                target=self._beep_console, daemon=True
            )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _beep_windows(self) -> None:
        """Windows 使用 winsound 蜂鸣"""
        import winsound

        # 播放系统默认提示音
        while not self._stop_event.is_set():
            try:
                winsound.MessageBeep(winsound.MB_ICONHAND)
            except Exception:
                # fallback
                winsound.Beep(880, 300)
            self._stop_event.wait(0.8)

    def _beep_console(self) -> None:
        """Linux/macOS 使用终端 bell 字符"""
        while not self._stop_event.is_set():
            sys.stdout.write("\a")
            sys.stdout.flush()
            self._stop_event.wait(0.8)
