"""
config_manager.py - 配置读取/管理模块
========================================
功能：
  1. 读取 YAML 配置文件
  2. 首次运行时自动生成默认配置
  3. 提供类型安全的配置访问接口
  4. 实时重新加载支持

依赖：PyYAML
"""

import os
import yaml
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 默认配置（与 config.yaml 内容一致，当 config.yaml 缺失时使用）
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    "serial": {
        "port": "",
        "baudrate": 115200,
        "timeout": 0.5,
        "reconnect_delay_min": 1.0,
        "reconnect_delay_max": 60.0,
        "reconnect_backoff": 2.0,
    },
    "overlay": {
        "opacity_levels": {
            "NORMAL": 0,
            "HUMAN_DETECTED": 0,
            "APPROACHING": 102,
            "SUSPECTED_PEEPING": 153,
            "PRIVACY_PROTECT": 204,
            "ALARM": 230,
        },
        "color": [0, 0, 0],
        "warning_color": [255, 50, 50],
    },
    "thresholds": {
        "approaching_cm": 200,
        "suspected_cm": 120,
        "alarm_cm": 60,
        "lock_screen_delay_sec": 15,
        "static_energy_warning": 40,
    },
    "alarm": {
        "sound_file": "alarm.wav",
        "sound_loop": True,
        "sound_volume": 0.7,
    },
    "tray": {
        "enable_minimize_to_tray": True,
        "show_toast_on_state": True,
    },
    "logging": {
        "level": "INFO",
        "file": "peep_prevention.log",
        "max_size_mb": 10,
        "backup_count": 3,
    },
}


class ConfigManager:
    """配置管理器 - 负责读取、验证、生成默认配置"""

    def __init__(self, config_path: str) -> None:
        """
        参数:
            config_path: YAML 配置文件路径
        """
        self.config_path: str = config_path
        self._config: Dict[str, Any] = {}
        self._ensure_config_exists()
        self.reload()

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """重新加载配置文件"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
            logger.info(f"配置已加载: {self.config_path}")
        except Exception as e:
            logger.warning(f"加载配置文件失败 ({e}), 使用默认配置")
            self._config = DEFAULT_CONFIG.copy()

        # 确保所有键都存在
        self._merge_defaults(self._config, DEFAULT_CONFIG)

    def get(self, *keys: str, default: Any = None) -> Any:
        """
        安全地获取嵌套配置值。

        用法:
            cfg.get("serial", "port")
            cfg.get("overlay", "opacity_levels", "ALARM")

        参数:
            keys: 键路径
            default: 键不存在时的默认值
        """
        value: Any = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def get_serial_port(self) -> str:
        """获取串口端口"""
        return str(self.get("serial", "port", default=""))

    def get_serial_baudrate(self) -> int:
        """获取波特率"""
        return int(self.get("serial", "baudrate", default=115200))

    def get_serial_timeout(self) -> float:
        """获取串口超时"""
        return float(self.get("serial", "timeout", default=0.5))

    def get_opacity(self, state_name: str) -> int:
        """获取指定状态的遮罩透明度 (0-255)"""
        return int(self.get("overlay", "opacity_levels", state_name, default=0))

    def get_overlay_color(self) -> tuple:
        """获取遮罩颜色 (R, G, B)"""
        c = self.get("overlay", "color", default=[0, 0, 0])
        return (int(c[0]), int(c[1]), int(c[2]))

    def get_warning_color(self) -> tuple:
        """获取警告文字颜色 (R, G, B)"""
        c = self.get("overlay", "warning_color", default=[255, 50, 50])
        return (int(c[0]), int(c[1]), int(c[2]))

    def get_lock_screen_delay(self) -> int:
        """获取自动锁屏延迟秒数"""
        return int(self.get("thresholds", "lock_screen_delay_sec", default=15))

    def get_thresholds(self) -> Dict[str, Any]:
        """获取所有阈值"""
        return self.get("thresholds", default={})

    def get_alarm_config(self) -> Dict[str, Any]:
        """获取报警配置"""
        return self.get("alarm", default={})

    def get_reconnect_params(self) -> Dict[str, float]:
        """获取重连参数"""
        return {
            "min_delay": float(self.get("serial", "reconnect_delay_min", default=1.0)),
            "max_delay": float(self.get("serial", "reconnect_delay_max", default=60.0)),
            "backoff": float(self.get("serial", "reconnect_backoff", default=2.0)),
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _ensure_config_exists(self) -> None:
        """如果配置文件不存在，创建默认配置"""
        if not os.path.exists(self.config_path):
            config_dir = os.path.dirname(self.config_path)
            if config_dir:
                os.makedirs(config_dir, exist_ok=True)
            try:
                with open(self.config_path, "w", encoding="utf-8") as f:
                    f.write("# SmartOffice PeepPrevention - 配置文件\n")
                    f.write("# 本文件由程序首次运行时自动生成\n\n")
                    yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, allow_unicode=True)
                logger.info(f"已创建默认配置文件: {self.config_path}")
            except Exception as e:
                logger.error(f"创建配置文件失败: {e}")

    @staticmethod
    def _merge_defaults(target: Dict, defaults: Dict) -> None:
        """递归合并默认值，确保 target 包含所有 default 的键"""
        for key, value in defaults.items():
            if key not in target:
                target[key] = value
            elif isinstance(value, dict) and isinstance(target.get(key), dict):
                ConfigManager._merge_defaults(target[key], value)
