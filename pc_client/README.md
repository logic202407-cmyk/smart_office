# SmartOffice PeepPrevention - PC端隐私保护程序

基于 **PyQt6 + pyserial** 的跨平台桌面隐私保护程序。与 ESP32 毫米波雷达传感器配合，实时检测屏幕周围的窥视行为，自动遮挡屏幕、报警、锁屏。

## 功能特性

| 功能 | 说明 |
|------|------|
| 🛡️ 全屏遮罩 | PyQt6 无边框置顶窗口，6 级透明度（NORMAL→ALARM） |
| 👁️ 状态感知 | 串口接收 ESP32 传感器数据，自动识别 6 种安全状态 |
| 🔄 自动重连 | 串口断线后指数退避自动重连 |
| 🖥️ 多显示器 | 每个显示器独立遮罩窗口 |
| 🔔 声音报警 | 报警音频播放 + 系统蜂鸣 fallback |
| 🔒 自动锁屏 | 跨平台锁屏（Windows / macOS / Linux） |
| ⏱️ 倒计时锁屏 | PRIVACY_PROTECT 状态启动倒计时进度条 |
| 🔑 解锁按钮 | 遮罩上提供"解锁屏幕"按钮 |
| 🎯 系统托盘 | 托盘运行，图标根据状态变色，右键菜单 |
| ⚡ 开机自启 | 支持 Windows/macOS/Linux 开机自启 |
| 🐶 看门狗 | 数据超时自动恢复，防止假死 |
| ⚙️ 可配置 | YAML 配置文件，所有参数可调 |

## 系统要求

- **Python**: 3.9+
- **操作系统**: Windows 10+ / macOS 11+ / Linux (X11/Wayland)
- **硬件**: ESP32 + 毫米波雷达传感器（HLK-LD2410 等）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行程序

```bash
python main.py
```

首次运行会自动生成默认配置文件 `config.yaml`。

### 3. 命令行参数

```bash
# 使用自定义配置文件
python main.py -c my_config.yaml

# 启用 DEBUG 日志
python main.py -d

# 查看帮助
python main.py -h
```

## 通信协议

ESP32 → PC 通过串口发送 JSON 行：

```json
{"state":"SUSPECTED_PEEPING","target_state":2,"distance_cm":95,
 "moving_energy":12,"static_energy":58,"detect_distance_cm":300,
 "timestamp_ms":123456}
```

### 状态映射

| ESP32 状态 | PC 响应 |
|---|---|
| `NORMAL` | 关闭遮罩 / 恢复桌面 |
| `HUMAN_DETECTED` | 托盘图标变色（黄色） |
| `APPROACHING` | 半透明遮罩 ~40% + 文字提示 |
| `SUSPECTED_PEEPING` | 半透明遮罩 ~60% + 弹窗警告 |
| `PRIVACY_PROTECT` | 全屏遮罩 ~80% + 警告文字 + 倒计时锁屏 |
| `ALARM` | 全屏遮罩 ~90% + 声音报警 + 立即锁屏 |

## 配置文件

编辑 `config.yaml` 配置所有参数：

```yaml
serial:
  port: "COM3"              # 串口端口（留空自动检测）
  baudrate: 115200          # 波特率

overlay:
  opacity_levels:
    NORMAL: 0               # 0% 透明度
    APPROACHING: 102        # ~40%
    SUSPECTED_PEEPING: 153  # ~60%
    PRIVACY_PROTECT: 204    # ~80%
    ALARM: 230              # ~90%

thresholds:
  lock_screen_delay_sec: 15 # 自动锁屏倒计时（秒）
```

## 项目结构

```
pc_client/
├── main.py              # 程序入口，整合所有模块
├── config_manager.py    # 配置读取/管理
├── serial_reader.py     # 串口线程读取 + JSON 解析 + 重连
├── overlay_window.py    # 全屏遮罩窗口（PyQt6）
├── tray_app.py          # 系统托盘 + 右键菜单
├── sound_alarm.py       # 报警声音播放
├── lock_screen.py       # 跨平台锁屏模块
├── config.yaml          # 默认配置文件
├── requirements.txt     # Python 依赖
└── README.md            # 本文件
```

## 跨平台支持

| 功能 | Windows | macOS | Linux |
|------|---------|-------|-------|
| 全屏遮罩 | ✅ | ✅ | ✅ |
| 系统托盘 | ✅ | ✅ | ✅ |
| 声音报警 | ✅ (pygame/winsound) | ✅ (pygame/beep) | ✅ (pygame/beep) |
| 锁屏 | ✅ LockWorkStation | ✅ osascript | ✅ loginctl |
| 开机自启 | ✅ 注册表 | ✅ LaunchAgents | ✅ autostart |

## 锁屏机制

- **Windows**: 直接调用 `user32.LockWorkStation()`
- **macOS**: 通过 `osascript` 触发登录窗口
- **Linux**: 依次尝试 `loginctl` → `gnome-screensaver-command` → `xdg-screensaver`

## 故障排除

### 串口连接失败
1. 确认 ESP32 已连接并上电
2. 检查设备管理器/`ls /dev/tty*` 确认串口号
3. 在 `config.yaml` 中手动指定 `serial.port`

### 声音不工作
1. 安装依赖: `pip install pygame`
2. 确认 `alarm.wav` 文件存在（或修改配置中的路径）
3. 无声音文件时自动使用系统蜂鸣

### Linux 托盘图标不显示
- 安装 qt6 托盘支持: `sudo apt install libqt6gui6`
- 某些桌面环境需要 `libayatana-appindicator3-1`

## 许可证

MIT License

## Web Dashboard

For demos, `web_dashboard.py` provides a lightweight browser dashboard. It reads
pure JSON lines from the ESP32 serial port and shows the current privacy state,
distance curve, trend, hold timers, and recent raw serial lines.

Run it with:

```bash
python web_dashboard.py --serial COM5
```

Or with the PlatformIO Python runtime:

```bash
C:\.platformio\penv\Scripts\python.exe web_dashboard.py --serial COM5
```

Then open:

```text
http://127.0.0.1:8765/
```

Useful options:

```bash
python web_dashboard.py --serial COM5 --http-port 8765
python web_dashboard.py --serial COM5 --open
python web_dashboard.py --baud 115200
```

The dashboard ignores non-JSON debug logs such as `[PRIVACY_TEST] ...`, so the
firmware can keep human-readable logs while the PC UI consumes structured data.
