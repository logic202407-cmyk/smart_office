# 系统架构设计文档

> **项目名称**：SmartOffice 防偷窥隐私保护系统  
> **文档版本**：v1.0  
> **编写人**：系统架构 Agent  
> **日期**：2026-05-08  
> **状态**：初稿 / 待评审

---

## 目录

1. [系统概述与整体架构](#1-系统概述与整体架构)
2. [硬件架构与引脚分配](#2-硬件架构与引脚分配)
3. [软件模块划分与接口定义](#3-软件模块划分与接口定义)
4. [ESP32 ↔ PC 通信协议](#4-esp32--pc-通信协议)
5. [数据流设计](#5-数据流设计)
6. [推荐文件结构](#6-推荐文件结构)
7. [状态机整体设计](#7-状态机整体设计)
8. [技术选型：Arduino-ESP32 vs ESP-IDF](#8-技术选型arduino-esp32-vs-esp-idf)
9. [模块依赖关系](#9-模块依赖关系)
10. [开发路线图（6阶段）](#10-开发路线图6阶段)
11. [风险评估与备选方案](#11-风险评估与备选方案)

---

## 1. 系统概述与整体架构

### 1.1 系统定位

SmartOffice 防偷窥隐私保护系统是一套基于 **LD2410B 毫米波雷达传感器** 和 **ESP32-S3** 微控制器的智能隐私检测系统。系统通过实时监测人体距离与运动状态，判断是否存在偷窥行为，并通过手势识别实现交互控制，最终在 OLED 屏幕上提供可视化状态反馈，同时通过 USB CDC 串口与 PC 端上位机通信。

### 1.2 整体架构（分层视图）

```
┌────────────────────────────────────────────────────────────────────┐
│                      【应用层】                                      │
│  防偷窥状态机  │  手势交互逻辑  │  OLED UI 渲染  │  PC 通信服务    │
├────────────────────────────────────────────────────────────────────┤
│                      【服务层】                                      │
│  状态管理      │  事件分发      │  LED/蜂鸣器控制 │ 数据缓存与日志  │
├────────────────────────────────────────────────────────────────────┤
│                      【驱动/协议层】                                  │
│  LD2410B UART  │  PAJ7620U2 I2C │  SSD1306 I2C  │  USB CDC （PC） │
│  协议解析引擎  │  手势识别驱动  │  OLED 驱动    │  串口协议封装    │
├────────────────────────────────────────────────────────────────────┤
│                      【硬件层】                                      │
│  ESP32-S3      │  LD2410B 雷达  │  PAJ7620U2    │  SSD1306 OLED   │
│  (双核240MHz)  │  (24GHz毫米波) │  (手势传感器)  │  (128×64 I2C)   │
│  + AMS1117-3.3 │  UART 256000   │  I2C 400kHz   │  I2C 400kHz     │
└────────────────────────────────────────────────────────────────────┘
```

### 1.3 系统边界

| 边界 | 输入 | 输出 |
|------|------|------|
| 雷达 → ESP32 | LD2410B UART 目标数据帧 | 经解析的 target_state、distance、energy 等字段 |
| 手势 → ESP32 | PAJ7620U2 I2C 手势编号 | 手势事件（LEFT/RIGHT/UP/DOWN/CLOCKWISE 等） |
| ESP32 → OLED | 屏幕缓冲区内容 | 128×64 像素图形/文字显示 |
| ESP32 → PC | USB CDC 串口 JSON 数据 | 状态上报、事件通知（上行） |
| PC → ESP32 | USB CDC 串口 JSON 命令 | 配置下发、阈值调整、固件更新指令（下行） |
| ESP32 → 用户 | LED/蜂鸣器 | 状态指示、告警信号 |

---

## 2. 硬件架构与引脚分配

### 2.1 核心器件与连接

| 器件 | 接口 | ESP32-S3 引脚 | 网络标号 | 备注 |
|------|------|---------------|----------|------|
| LD2410B | UART TX（雷达→ESP32） | **GPIO44** (TODO) | TX_RADAR | U1.10 → ESP32 RX |
| LD2410B | UART RX（ESP32→雷达） | **GPIO43** (TODO) | RX_RADAR | U1.11 → ESP32 TX |
| LD2410B | OUT（目标检测指示） | **GPIO21** (TODO) | - | U1.23 — 低电平有目标 |
| OLED SSD1306 | SCL | **GPIO18** (TODO) | SCL | U1.5 — I2C 时钟 |
| OLED SSD1306 | SDA | **GPIO8** (TODO) | SDA | U1.4 — I2C 数据 |
| PAJ7620U2 | SCL | **GPIO18** (TODO) | SCL | 共用 I2C 总线 |
| PAJ7620U2 | SDA | **GPIO8** (TODO) | SDA | 共用 I2C 总线 |
| PAJ7620U2 | INT | **GPIO17** (TODO) | IO8 | U6.3 / U1.12 — 中断输出 |
| USB Type-C | D+/D- | 原生 USB 引脚 | - | ESP32-S3 原生 CDC |
| IO0 按键 | GPIO0 | **GPIO0** | - | U1.27 — 下载/启动模式 |
| EN 按键 | EN/RST | **EN** | - | 复位按键 |

> ⚠️ **TODO / 待确认**：以上 GPIO 编号基于 ESP32-S3-WROOM-1-N8R2 的常见封装推测得出，**需要用户根据实际原理图符号确认**。以下是推测依据：
> - **U1.10 / U1.11**：ESP32-S3 中 UART0（默认）通常对应 GPIO43 (TX) / GPIO44 (RX) — 若用于 LD2410B，需确认是否使用 UART1（如 GPIO17/18）避免与调试串口冲突。
> - **U1.5 / U1.4**：常见 I2C 引脚为 GPIO18 (SCL) / GPIO8 (SDA) — 或 GPIO9/10，需核对原理图。
> - **U1.12 (IO8)**：PAJ7620U2 中断 — 可能为 GPIO17 或 GPIO21。
> - **U1.23 (OUT)**：LD2410B OUT 引脚 — 可能为 GPIO21 或 GPIO47，需核对。

### 2.2 供电设计

```
USB 5V ──► AMS1117-3.3 ──► 3.3V 总线
                │
                ├── ESP32-S3 (峰值 ~500mA)
                ├── LD2410B (峰值 ~90mA)
                ├── PAJ7620U2 (峰值 ~10mA)
                └── OLED SSD1306 (峰值 ~20mA)
```

> ⚠️ **风险提示**：AMS1117-3.3 为线性稳压器，输入 5V、输出 3.3V、压差 1.7V。在总负载 ~400mA 时，功耗约 0.68W（无散热），温升可能超过 50°C。建议评估是否需改用 DC-DC 或增加散热焊盘。

---

## 3. 软件模块划分与接口定义

### 3.1 模块总览

```
┌──────────────────────────────────────────────────────────┐
│                      main.cpp                           │
│           初始化、主循环、事件分发、看门狗                   │
├──────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │radar_    │  │gesture_  │  │oled_     │  │pc_comm_  │ │
│  │driver    │  │driver    │  │driver    │  │handler   │ │
│  ├──────────┤  ├──────────┤  ├──────────┤  ├──────────┤ │
│  │LD2410B   │  │PAJ7620U2 │  │SSD1306   │  │USB CDC   │ │
│  │UART协议  │  │I2C驱动   │  │I2C驱动   │  │JSON序列化│ │
│  │解析      │  │& 手势映射│  │& UI渲染  │  │& 反序列化│ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
├──────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────┐  │
│  │               state_machine.cpp                    │  │
│  │  防偷窥主状态机 + 手势交互器 + 告警控制器           │  │
│  │  (状态转换 / 定时器 / 事件队列 / LED/蜂鸣器输出)   │  │
│  └────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────────────────┐  │
│  │  config.h         │  │  types.h / protocol.h       │  │
│  │  全局配置/阈值    │  │  数据结构/协议定义           │  │
│  └──────────────────┘  └──────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### 3.2 模块详细接口定义

#### 3.2.1 radar_driver 模块

**职责**：通过 UART 与 LD2410B 通信，解析目标上报帧。

```cpp
// radar_driver.h
class RadarDriver {
public:
    // === 初始化与配置 ===
    bool begin(HardwareSerial* serial, int rx_pin, int tx_pin);
    bool configure(uint32_t baud = 256000, uint8_t config = SERIAL_8N1);
    
    // === 配置命令（通过配置帧 FDFCFBFA...） ===
    bool set_distance_threshold(uint16_t near_cm, uint16_t very_near_cm);
    bool set_sensitivity(uint8_t moving_gate, uint8_t static_gate);
    bool set_baudrate(uint32_t baud);
    bool enter_config_mode();
    bool exit_config_mode();
    bool factory_reset();
    bool read_firmware_version(char* buf, size_t len);
    
    // === 数据获取 ===
    RadarData get_latest_data();            // 获取最新解析结果
    bool is_target_present();               // OUT 引脚电平判断
    
    // === 数据回调（推荐使用） ===
    void on_data_received(std::function<void(const RadarData&)> cb);
    
    // === 主循环调用 ===
    void update();                          // 轮询 UART 缓冲区并解析
    
private:
    // 帧解析器
    bool parse_frame(uint8_t* buf, size_t len, RadarData& out);
    bool validate_checksum(uint8_t* buf, size_t len);
};

// 雷达数据结构
struct RadarData {
    uint8_t  target_state;      // 0x00=无目标 0x01=运动 0x02=静止 
                                // 0x03=运动+静止 0x04=底噪检测
    uint16_t moving_distance_cm;// 运动目标距离 (cm)
    uint8_t  moving_energy;     // 运动目标能量 (0-100)
    uint16_t static_distance_cm; // 静止目标距离 (cm)
    uint8_t  static_energy;     // 静止目标能量 (0-100)
    uint16_t detect_distance_cm; // 感应距离 (cm)
    uint64_t timestamp_ms;      // 数据时间戳
    bool     valid;             // 数据是否有效
};
```

#### 3.2.2 gesture_driver 模块

**职责**：通过 I2C 驱动 PAJ7620U2 手势传感器，检测手势事件。

```cpp
// gesture_driver.h
class GestureDriver {
public:
    bool begin(TwoWire* wire, int int_pin);
    void set_gesture_callback(std::function<void(GestureType)> cb);
    void update();              // 轮询中断状态并读取手势
    
    // 配置
    bool enable_gesture(GestureType type);
    bool set_sensitivity(uint8_t level);
    uint8_t get_gesture_count();
    
private:
    int int_pin;                // 中断引脚
    TwoWire* i2c_bus;
    bool read_register(uint8_t reg, uint8_t* data, size_t len);
    bool write_register(uint8_t reg, uint8_t data);
};

enum GestureType : uint8_t {
    GESTURE_NONE        = 0x00,
    GESTURE_UP          = 0x01,
    GESTURE_DOWN        = 0x02,
    GESTURE_LEFT        = 0x03,
    GESTURE_RIGHT       = 0x04,
    GESTURE_CLOCKWISE   = 0x05,
    GESTURE_COUNTER_CLOCKWISE = 0x06,
    GESTURE_FORWARD     = 0x07,
    GESTURE_BACKWARD    = 0x08,
};
```

#### 3.2.3 oled_driver 模块

**职责**：驱动 SSD1306 OLED 屏幕，渲染 UI 界面。

```cpp
// oled_driver.h
class OledDriver {
public:
    bool begin(TwoWire* wire, uint8_t addr = 0x3C);
    
    // 页面渲染
    void show_splash();                 // 启动画面
    void show_normal();                 // 正常模式
    void show_human_detected();         // 检测到人
    void show_approaching();            // 正在接近
    void show_suspected_peeping();      // 疑似偷窥
    void show_alarm();                  // 告警画面
    void show_privacy_protected();      // 隐私保护中
    void show_distance(uint16_t cm);    // 显示距离
    void show_status_string(const char* text); // 自定义文字
    
    void update();                      // 刷新显示（按需或定时）
    void set_brightness(uint8_t level); // 0-255
    
private:
    SSD1306 display;                    // 使用 Adafruit/u8g2 库
    void draw_distance_bar(uint16_t cm); // 距离柱状条
    void draw_state_icon(uint8_t state); // 状态图标
};
```

#### 3.2.4 pc_comm_handler 模块

**职责**：通过 USB CDC 与 PC 端通信，上行上报、下行接收配置。

```cpp
// pc_comm_handler.h
class PcCommHandler {
public:
    bool begin(HardwareSerial* serial);  // USB CDC 通常为 Serial
    
    // === 上行：ESP32 → PC ===
    void send_state_report(const SystemState& state);
    // JSON: {"state":"APPROACHING","target_state":2,"distance_cm":95,
    //        "moving_energy":12,"static_energy":58}
    
    void send_event(const char* event_type, const char* detail);
    void send_log(const char* level, const char* message);
    void send_heartbeat();              // 心跳包
    
    // === 下行：PC → ESP32 ===
    void on_command_received(std::function<void(const PcCommand&)> cb);
    // JSON: {"cmd":"set_threshold","params":{"near_dist":150,"very_near":80}}
    
    // === 主循环调用 ===
    void update();                      // 处理接收缓冲区
    
private:
    void parse_command(const char* json_str);
    void send_json(const char* json_str);
    bool validate_json(const char* json_str);
};

// PC 命令结构
struct PcCommand {
    String cmd;                         // 命令类型
    JsonDocument params;                // 参数（使用 ArduinoJson）
};

// 系统状态（用于上行）
struct SystemState {
    String  state;                      // NORMAL/HUMAN_DETECTED/APPROACHING/...
    uint8_t target_state;              // LD2410B 原始目标状态
    uint16_t distance_cm;              // 最近目标距离
    uint8_t  moving_energy;
    uint8_t  static_energy;
    uint16_t detect_distance;
    uint32_t uptime_ms;                // 系统运行时间
};
```

#### 3.2.5 state_machine 模块（核心）

**职责**：防偷窥状态机 + 手势交互 + 告警控制。

```cpp
// state_machine.h
// === 状态枚举 ===
enum class PrivacyState : uint8_t {
    NORMAL              = 0,   // 正常/无人
    HUMAN_DETECTED      = 1,   // 检测到人
    APPROACHING         = 2,   // 正在接近
    SUSPECTED_PEEPING   = 3,   // 疑似偷窥行为
    PRIVACY_PROTECT     = 4,   // 隐私保护已触发
    ALARM               = 5    // 告警
};

// === 事件枚举 ===
enum class StateEvent : uint8_t {
    NO_EVENT,
    TARGET_ENTERED,             // 目标进入检测范围
    TARGET_EXITED,              // 目标离开
    APPROACHING_NEAR,           // 接近（距离 < NEAR_DIST）
    APPROACHING_VERY_NEAR,      // 很近（距离 < VERY_NEAR_DIST）
    SUSPECT_TIMEOUT,            // 疑似偷窥时间到
    CLEAR_SUSPECT,              // 疑似解除
    ALARM_TIMEOUT,              // 告警时间到
    RESET,                      // 手动复位
    GESTURE_UP,                 // 手势：向上
    GESTURE_DOWN,               // 手势：向下
    GESTURE_LEFT,               // 手势：向左
    GESTURE_RIGHT,              // 手势：向右
    // ... 更多
};

class StateMachine {
public:
    void begin();
    void update();              // 主循环调用：检查事件并执行状态转换
    PrivacyState get_current_state();
    
    // 注册各模块回调
    void set_oled(OledDriver* oled);
    void set_pc_comm(PcCommHandler* pc);
    void set_led_pin(int pin);
    void set_buzzer_pin(int pin);
    
    // 事件注入
    void inject_radar_data(const RadarData& data);
    void inject_gesture(GestureType gesture);
    void inject_pc_command(const PcCommand& cmd);
    
    // 阈值配置
    void set_thresholds(uint16_t near_cm, uint16_t very_near_cm,
                        uint32_t suspect_ms, uint32_t alarm_ms);
    
private:
    void transition_to(PrivacyState new_state);
    StateEvent evaluate_state_change(const RadarData& data);
    StateEvent evaluate_gesture(const GestureType& gesture);
    void execute_entry_action(PrivacyState state);
    void execute_exit_action(PrivacyState state);
    void execute_state_action(PrivacyState state);
    
    // 定时器管理
    uint64_t state_entry_time;
    uint64_t suspect_timer_start;
    uint64_t alarm_timer_start;
};
```

#### 3.2.6 config.h 模块

**职责**：全局配置参数。

```cpp
// config.h
#pragma once

// === 引脚配置（待确认） ===
#define PIN_RADAR_RX        44  // U1.10 (TODO: 确认原理图)
#define PIN_RADAR_TX        43  // U1.11 (TODO: 确认原理图)
#define PIN_RADAR_OUT       21  // U1.23 (TODO: 确认原理图)
#define PIN_I2C_SCL         18  // U1.5  (TODO: 确认原理图)
#define PIN_I2C_SDA         8   // U1.4  (TODO: 确认原理图)
#define PIN_GESTURE_INT     17  // U6.3 / U1.12 (TODO: 确认原理图)
#define PIN_LED             2   // 板载 LED (GPIO2)
#define PIN_BUZZER          5   // 蜂鸣器 (GPIO5)

// === 雷达阈值 ===
#define RADAR_NEAR_DIST_CM      150     // "接近"距离阈值
#define RADAR_VERY_NEAR_DIST_CM 80      // "很近"距离阈值
#define RADAR_BAUDRATE          256000  // LD2410B 默认波特率

// === 防偷窥计时 ===
#define SUSPECT_TIME_MS         3000    // 疑似判定时间 (3s)
#define ALARM_TIME_MS           8000    // 告警持续时间 (8s)
#define PRIVACY_COOLDOWN_MS     60000   // 隐私保护冷却 (60s)

// === OLED ===
#define OLED_I2C_ADDR          0x3C
#define OLED_WIDTH              128
#define OLED_HEIGHT             64

// === PC 通信 ===
#define PC_BAUDRATE             115200  // USB CDC 波特率
#define HEARTBEAT_INTERVAL_MS   5000    // 心跳间隔
```

---

## 4. ESP32 ↔ PC 通信协议

### 4.1 协议总览

- **物理层**：USB CDC（虚拟串口）
- **波特率**：115200（USB CDC 实际由 USB 速率决定，波特率仅用于兼容）
- **编码**：UTF-8 JSON
- **分隔符**：`\n`（换行符，即每条消息一行）
- **方向**：全双工

### 4.2 上行协议（ESP32 → PC）

#### 4.2.1 状态上报

```json
{
  "type": "state_report",
  "timestamp_ms": 1234567,
  "data": {
    "state": "APPROACHING",
    "target_state": 2,
    "distance_cm": 95,
    "moving_energy": 12,
    "static_energy": 58,
    "detect_distance_cm": 600,
    "uptime_ms": 1234567
  }
}
```

**state 枚举值**：
| 值 | 含义 |
|----|------|
| `NORMAL` | 正常/无人 |
| `HUMAN_DETECTED` | 检测到人 |
| `APPROACHING` | 正在接近 |
| `SUSPECTED_PEEPING` | 疑似偷窥 |
| `PRIVACY_PROTECT` | 隐私保护中 |
| `ALARM` | 告警中 |

#### 4.2.2 事件通知

```json
{
  "type": "event",
  "timestamp_ms": 1234567,
  "data": {
    "event": "gesture_detected",
    "detail": "UP"
  }
}
```

**event 类型**：
- `gesture_detected` — 手势事件
- `radar_target_in` — 目标进入
- `radar_target_out` — 目标离开
- `state_transition` — 状态转换
- `alarm_triggered` — 告警触发
- `error` — 错误

#### 4.2.3 日志

```json
{
  "type": "log",
  "timestamp_ms": 1234567,
  "data": {
    "level": "INFO",
    "message": "Radar initialized OK, baud=256000"
  }
}
```

**level**：`DEBUG` / `INFO` / `WARN` / `ERROR`

#### 4.2.4 心跳

```json
{
  "type": "heartbeat",
  "timestamp_ms": 1234567,
  "data": {
    "uptime_ms": 1234567,
    "state": "NORMAL"
  }
}
```

### 4.3 下行协议（PC → ESP32）

#### 4.3.1 配置阈值

```json
{
  "type": "command",
  "id": 1,
  "data": {
    "cmd": "set_threshold",
    "params": {
      "near_dist_cm": 150,
      "very_near_dist_cm": 80,
      "suspect_time_ms": 3000,
      "alarm_time_ms": 8000
    }
  }
}
```

#### 4.3.2 状态控制

```json
{
  "type": "command",
  "id": 2,
  "data": {
    "cmd": "set_state",
    "params": {
      "state": "NORMAL"
    }
  }
}
```

#### 4.3.3 雷达配置

```json
{
  "type": "command",
  "id": 3,
  "data": {
    "cmd": "radar_config",
    "params": {
      "baudrate": 256000,
      "moving_gate": 3,
      "static_gate": 3
    }
  }
}
```

#### 4.3.4 查询状态

```json
{
  "type": "command",
  "id": 4,
  "data": {
    "cmd": "get_status",
    "params": {}
  }
}
```

#### 4.3.5 固件复位

```json
{
  "type": "command",
  "id": 5,
  "data": {
    "cmd": "reset",
    "params": {}
  }
}
```

### 4.4 应答协议

对于每条下行命令，ESP32 应回复确认：

```json
{
  "type": "response",
  "id": 1,
  "data": {
    "status": "ok",
    "message": "Threshold updated"
  }
}
```

错误应答：

```json
{
  "type": "response",
  "id": 1,
  "data": {
    "status": "error",
    "code": 4001,
    "message": "Invalid parameter: near_dist_cm out of range"
  }
}
```

### 4.5 协议扩展性

- 所有字段使用 `snake_case`
- `type` 字段用于消息路由，未来可扩展新的消息类型
- `data` 字段保持灵活性，可在不破坏协议的情况下添加新字段
- 未知字段应被忽略（向前兼容）

---

## 5. 数据流设计

### 5.1 主数据流：雷达检测 → 用户反馈

```
  LD2410B                    ESP32-S3                         OLED / PC
 ┌────────┐   UART 256000   ┌─────────────────┐   I2C       ┌─────────┐
 │        │ ◄─────────────► │ RadarDriver      │  ────────► │ OLED    │
 │ Radar  │   上报帧         │   ├─ 解析帧      │  JSON      │ SSD1306 │
 │ 模块   │   F4F3F2F1...   │   ├─ 更新 RadarData │ ◄───────  │ 图标/文字│
 │        │   F8F7F6F5      │   └─ callback ──┐ │   USB CDC  └─────────┘
 └────────┘                 │                │ │             ┌─────────┐
                             │                ▼ │  ────────► │ PC 端   │
      PAJ7620U2              │          ┌──────────┐│  JSON     │ 上位机  │
 ┌────────┐   I2C 400kHz    │          │ State    ││ ◄───────  │ 监控/   │
 │ Gesture│ ◄─────────────► │  Gesture  │ Machine  ││  JSON     │ 日志    │
 │ Sensor │   INT 中断      │  Driver   │          ││           └─────────┘
 └────────┘                 │   ├─ 手势回调──► │          ││
                             │   └──────────► │ 事件注入  ││
                             │                └──────────┘│
                             │                     │       │
                             │                     ▼       │
                             │              ┌──────────┐  │
                             │              │ LED      │  │
                             │              │ 蜂鸣器   │  │
                             │              └──────────┘  │
                             └─────────────────────────────┘
```

### 5.2 数据流路径详细描述

#### 路径 A：正常检测（周期性，~100ms）

```
[LD2410B] --UART上报帧--> [RadarDriver.parse_frame()]
  → [RadarData {target_state, distance, energy, ...}]
  → [StateMachine.inject_radar_data()]
  → [StateMachine.evaluate_state_change()]
  → [状态转换决策]
    → [OledDriver.show_*()]          -- 更新屏幕
    → [PcCommHandler.send_state_report()] -- 上报 PC
    → [LED 状态更新]
```

#### 路径 B：手势交互（事件驱动）

```
[PAJ7620U2] --I2C--> [GestureDriver 读取手势寄存器]
  → [GestureType 枚举值]
  → [StateMachine.inject_gesture()]
  → [手势动作判断]
    → 向上/下：OLED 亮度调节
    → 向左/右：切换显示模式
    → 顺时针：隐私保护手动触发
    → 逆时针：复位告警
  → [PcCommHandler.send_event("gesture_detected", "UP")]
```

#### 路径 C：PC 下发命令（事件驱动）

```
[PC] --USB CDC--> [PcCommHandler 接收 JSON]
  → [ArduinoJson 解析]
  → [PcCommand {cmd, params}]
  → [StateMachine.inject_pc_command()]
    → set_threshold：更新 config 参数
    → set_state：强制状态转换
    → radar_config：通过 RadarDriver 配置雷达
    → reset：系统复位
  → [PcCommHandler 发送 response]
```

### 5.3 数据流时序要求

| 数据流 | 更新频率 | 最大延迟 | 备注 |
|--------|---------|---------|------|
| 雷达数据解析 | ~10Hz | 100ms | LD2410B 默认上报周期 ~100ms |
| OLED 显示更新 | ~10Hz | 200ms | 无需过快刷新 |
| PC 状态上报 | ~5Hz | 200ms | 状态变化时立即上报 |
| 手势检测 | 事件驱动 | 50ms | 中断触发后立即处理 |
| PC 命令响应 | 事件驱动 | 100ms | 需及时回复 |
| 心跳 | 0.2Hz (5s) | — | 周期性 |

### 5.4 数据缓存策略

- 雷达数据：仅保存最新一份（覆盖式），无需历史
- OLED 缓冲区：SSD1306 内置 ~1KB，无需外部缓存
- PC 上行：无缓存，实时发送。若 PC 未连接，静默丢弃
- PC 下行：命令无缓存，逐条处理

---

## 6. 推荐文件结构

```
SmartOffice_PeepPrevention/
├── firmware/                          # ESP32-S3 固件（Arduino-ESP32）
│   ├── SmartOffice_PeepPrevention.ino # 主入口
│   ├── config.h                       # 全局配置/引脚/阈值
│   ├── types.h                        # 公共数据结构
│   ├── protocol.h                     # 通信协议定义（JSON 字段常量）
│   │
│   ├── radar_driver/                  # LD2410B 驱动
│   │   ├── radar_driver.h
│   │   └── radar_driver.cpp
│   │
│   ├── gesture_driver/                # PAJ7620U2 手势驱动
│   │   ├── gesture_driver.h
│   │   ├── gesture_driver.cpp
│   │   └── paj7620_registers.h        # PAJ7620U2 寄存器定义
│   │
│   ├── oled_driver/                   # SSD1306 OLED 驱动与 UI
│   │   ├── oled_driver.h
│   │   ├── oled_driver.cpp
│   │   └── bitmaps/                   # 图标/字库位图
│   │       ├── icon_normal.h
│   │       ├── icon_alarm.h
│   │       └── icon_privacy.h
│   │
│   ├── state_machine/                 # 核心状态机
│   │   ├── state_machine.h
│   │   └── state_machine.cpp
│   │
│   ├── pc_comm/                       # PC 通信
│   │   ├── pc_comm_handler.h
│   │   └── pc_comm_handler.cpp
│   │
│   ├── utils/                         # 工具模块
│   │   ├── watchdog.cpp / .h         # 看门狗管理
│   │   ├── logger.cpp / .h            # 日志系统（支持串口+PC）
│   │   └── timer_manager.cpp / .h     # 软件定时器管理
│   │
│   ├── lib/                           # 第三方库（或 platformio.ini 管理）
│   │   └── (通过 PlatformIO 自动拉取)
│   │
│   ├── platformio.ini                 # PlatformIO 项目配置
│   └── README.md                      # 固件编译/烧录说明
│
├── pc_client/                         # PC 端上位机
│   ├── main.py                        # 入口/主循环
│   ├── config.py                      # PC 端配置
│   ├── serial_comm.py                 # 串口通信模块
│   ├── protocol.py                    # 协议解析/序列化
│   ├── state_monitor.py               # 状态监控逻辑
│   ├── ui/                            # GUI 界面
│   │   ├── main_window.py
│   │   ├── radar_panel.py             # 雷达数据面板
│   │   ├── state_diagram.py           # 状态机可视化
│   │   └── log_viewer.py              # 日志查看器
│   ├── requirements.txt               # Python 依赖
│   └── README.md
│
├── documents/                         # 项目文档
│   ├── 01-system-architecture.md      # 本文档：系统架构设计
│   ├── 02-hardware-design.md          # 硬件设计文档
│   ├── 03-ld2410b-protocol.md         # LD2410B 协议详细说明
│   ├── 04-state-machine-spec.md       # 状态机详细规格
│   ├── 05-pc-comm-protocol.md         # PC 通信协议详细说明
│   └── 06-test-plan.md                # 测试计划
│
├── tests/                             # 测试
│   ├── firmware/                      # 固件单元测试
│   │   ├── test_radar_parser.cpp
│   │   ├── test_state_machine.cpp
│   │   └── test_protocol.cpp
│   └── pc_client/                     # PC 端测试
│       ├── test_serial_comm.py
│       └── test_protocol.py
│
├── tools/                             # 工具脚本
│   ├── radar_config_tool.py           # 雷达配置 CLI 工具
│   ├── protocol_simulator.py          # 协议模拟器（模拟 ESP32）
│   └── oled_font_converter.py         # 字库转换工具
│
└── README.md                          # 项目总 README
```

---

## 7. 状态机整体设计

### 7.1 防偷窥主状态机

```
                          ┌──────────────────────┐
                          │       NORMAL         │ ◄────── 无人/初始状态
                          │  (无人 / 距离>阈值)  │
                          └──────┬───────────────┘
                                 │ TARGET_ENTERED
                                 │ (target_state!=0 && dist>NEAR)
                                 ▼
                  ┌──────────────────────────────┐
         ┌──────► │      HUMAN_DETECTED          │ ◄────── 检测到人但距离尚远
         │        │  (有人但距离>NEAR_DIST)      │
         │        └──────┬───────────────────────┘
         │               │ APPROACHING_NEAR
         │               │ (距离 < NEAR_DIST)
         │               ▼
         │        ┌──────────────────────────────┐
         │        │       APPROACHING            │ ◄────── 有人接近中
         │        │  (人逐渐靠近, NEAR>dist>VERY)│
         │        └──────┬───────────────────────┘
         │               │ APPROACHING_VERY_NEAR
         │               │ (距离 < VERY_NEAR_DIST)
         │               │ && 持续 SUSPECT_TIME
         │               ▼
         │        ┌──────────────────────────────┐
         │        │    SUSPECTED_PEEPING         │ ◄────── 疑似偷窥
         │        │  (很近+持续3s)               │
         │        └──────┬───────────────────────┘
         │               │ 继续很近 持续 ALARM_TIME
         │               │ OR 手势确认
         │               ▼
         │        ┌──────────────────────────────┐
         │        │      PRIVACY_PROTECT         │ ◄────── 隐私保护触发
         │        │  (屏幕/数据保护中)           │
         │        └──────┬───────────────────────┘
         │               │ 告警定时到 或 手动确认
         │               ▼
         │        ┌──────────────────────────────┐
         │        │         ALARM                │ ◄────── 告警状态
         │        │  (蜂鸣器/LED闪烁/PC上报)     │
         │        └──────┬───────────────────────┘
         │               │ TARGET_EXITED
         │               │ OR RESET 或 冷却时间到
         │               ▼
         └────────── [返回 NORMAL]
```

### 7.2 状态转换表

| 当前状态 | 事件 | 下一状态 | 动作 |
|---------|------|---------|------|
| NORMAL | TARGET_ENTERED (有人) | HUMAN_DETECTED | 显示人脸图标，上报 PC |
| NORMAL | GESTURE_* | NORMAL | 处理手势（亮度/音量等） |
| HUMAN_DETECTED | 距离 < NEAR_DIST | APPROACHING | 显示"接近"警告，上报 PC |
| HUMAN_DETECTED | TARGET_EXITED (无人) | NORMAL | 恢复显示 |
| APPROACHING | 距离 < VERY_NEAR_DIST 持续 SUSPECT_TIME | SUSPECTED_PEEPING | 开始计时，OLED 闪烁 |
| APPROACHING | 距离 > NEAR_DIST | HUMAN_DETECTED | 状态回退 |
| APPROACHING | TARGET_EXITED | NORMAL | 直接回退 |
| SUSPECTED_PEEPING | 距离 < VERY_NEAR_DIST 持续 ALARM_TIME | PRIVACY_PROTECT | 隐私保护动作 |
| SUSPECTED_PEEPING | 距离 > VERY_NEAR_DIST | APPROACHING | 嫌疑人退后 |
| SUSPECTED_PEEPING | TARGET_EXITED | NORMAL | 离开则解除 |
| SUSPECTED_PEEPING | GESTURE_CLOCKWISE | PRIVACY_PROTECT | 手动确认触发保护 |
| PRIVACY_PROTECT | 冷却时间到 (60s) | NORMAL | 自动恢复 |
| PRIVACY_PROTECT | GESTURE_COUNTER_CLOCKWISE | NORMAL | 手动解除 |
| PRIVACY_PROTECT | 距离持续 < VERY_NEAR | ALARM | 升级为告警 |
| ALARM | 告警时间到 (8s) | NORMAL | 蜂鸣器停止，系统恢复 |
| ALARM | GESTURE_COUNTER_CLOCKWISE | NORMAL | 手动停止告警 |
| ALARM | TARGET_EXITED | NORMAL | 离开自动解除 |
| 任何状态 | PC 命令 set_state=xx | 指定状态 | 强制跳转 |

### 7.3 手势交互逻辑

手势在特定状态下触发不同动作：

| 手势 | 状态限定 | 动作 |
|------|---------|------|
| UP | NORMAL / HUMAN_DETECTED | OLED 亮度 +1 |
| DOWN | NORMAL / HUMAN_DETECTED | OLED 亮度 -1 |
| LEFT | NORMAL / HUMAN_DETECTED | 切换显示模式（距离/能量/状态） |
| RIGHT | NORMAL / HUMAN_DETECTED | 切换显示模式（反之） |
| CLOCKWISE | SUSPECTED_PEEPING / APPROACHING | 确认启用隐私保护 |
| COUNTER_CLOCKWISE | PRIVACY_PROTECT / ALARM | 解除告警 / 恢复 |
| FORWARD | 任何 | 开启/关闭 PC 端摄像头遮挡（额外功能） |
| BACKWARD | 任何 | 静音模式切换 |

### 7.4 OLED 显示状态映射

| 系统状态 | OLED 显示内容 | 图标 | 颜色/效果 |
|---------|--------------|------|----------|
| NORMAL | "✓ 安全 · 无人" + 时钟 | 绿色盾牌 | 正常 |
| HUMAN_DETECTED | "⚠ 检测到人 Nm" + 距离 | 黄色人形 | 常亮 |
| APPROACHING | "⚠ 有人接近 Nm" + 距离柱 | 橙色感叹号 | 慢闪 |
| SUSPECTED_PEEPING | "⚠ 疑似偷窥！" | 红色眼睛 | 快闪 |
| PRIVACY_PROTECT | "🔒 隐私保护中" | 锁定图标 | 常亮 |
| ALARM | "🚨 告警！" + 距离 | 红色警铃 | 超快闪 |

---

## 8. 技术选型：Arduino-ESP32 vs ESP-IDF

### 8.1 对比分析

| 维度 | Arduino-ESP32 | ESP-IDF |
|------|--------------|---------|
| **开发难度** | ★☆☆ 低，Arduino 语法，上手快 | ★★★ 高，FreeRTOS + CMake |
| **库生态** | ★★★ 丰富 (Adafruit/U8g2/LiquidCrystal) | ★★☆ 核心库完善但第三方少 |
| **调试能力** | ★★☆ Serial.print + 串口监视器 | ★★★ GDB + JTAG + 日志分级 |
| **实时性** | ★★☆ 受 Arduino loop() 限制 | ★★★ FreeRTOS 任务/中断/队列 |
| **功耗管理** | ★☆☆ 需手动实现 | ★★★ 深度睡眠/ULP 协处理器 |
| **双核利用** | ★★☆ 可用但非原生 | ★★★ SMP FreeRTOS，原生支持 |
| **内存管理** | ★☆☆ 弱，无保护 | ★★★ heap 分配/保护/调试 |
| **协议栈** | ★★☆ 封装好但灵活性差 | ★★★ 完整 WiFi/BLE/ESP-NOW |
| **OTA** | ★☆☆ 需第三方库 | ★★★ 原生支持，HTTPS OTA |
| **多线程** | ★☆☆ 需要 ESP32Task 封装 | ★★★ 原生 FreeRTOS |
| **编译速度** | ★★★ 快 | ★★☆ 较慢（完整 SDK） |
| **二进制大小** | ★★★ 小 | ★★☆ 较大（完整组件） |
| **社区支持** | ★★★ 极活跃 | ★★☆ 官方 + 工业级 |
| **Studio/IDE** | Arduino IDE / PlatformIO | Eclipse / VS Code + 插件 |

### 8.2 本项目推荐：Arduino-ESP32 + PlatformIO

**理由**：

1. **项目复杂度适中**：本项目不涉及 WiFi/BLE、OTA、深度睡眠等高级功能，核心需求是 UART + I2C + USB CDC，Arduino-ESP32 完全胜任。

2. **库依赖**：
   - `U8g2` 或 `Adafruit_SSD1306` — OLED 驱动
   - `ArduinoJson` — JSON 序列化
   - `PAJ7620` 手势传感器库 — 社区已有
   - LD2410B 协议解析 — 纯 UART，自行实现

3. **开发效率**：Arduino 语法 + PlatformIO 项目管理 = 快速迭代。团队成员如果主要是嵌入式初学者/中级开发者，Arduino 门槛低。

4. **USB CDC 支持**：Arduino-ESP32 原生支持 `Serial` 作为 USB CDC 接口，无需额外配置。

### 8.3 何时考虑 ESP-IDF

- 需要 **多任务高实时性**（例如雷达 + 手势 + OLED + WiFi 同时运行且有严格时序要求）
- 需要 **低功耗**（电池供电 + 深度睡眠 + ULP 协处理器）
- 需要 **产品化认证**（工业级可靠性要求）
- 需要 **OTA 远程固件升级**（后续扩展）
- 当前固件性能测试中发现 **loop() 延迟 > 50ms** 导致数据丢失

### 8.4 折中方案

如果后续性能不满足，可采取 **混合方案**：

- 主体使用 **Arduino-ESP32** 框架
- 关键时序逻辑使用 **ESP-IDF 组件**（通过 `esp_custom_partition` 或 `esp_event_loop`）
- PlatformIO 支持 `build_flags` 混编部分 ESP-IDF 组件

---

## 9. 模块依赖关系

### 9.1 依赖关系图

```
                    ┌──────────┐
                    │  types.h  │ (数据结构定义)
                    └────┬─────┘
                         │ 被引用
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
  ┌──────────┐   ┌──────────┐   ┌──────────────┐
  │config.h  │   │protocol.h│   │  utils/      │
  │(引脚/阈值)│   │(协议常量) │   │(watchdog/    │
  └────┬─────┘   └────┬─────┘   │ logger/timer)│
       │              │         └──────┬───────┘
       │              │                │
       ▼              ▼                ▼
  ┌────────────────────────────────────────┐
  │          radar_driver                   │
  │  ─ 依赖: HardwareSerial, config.h,      │
  │          types.h, utils/logger          │
  └─────────────────┬──────────────────────┘
                    │
                    ▼
  ┌────────────────────────────────────────┐
  │          gesture_driver                 │
  │  ─ 依赖: TwoWire, config.h, types.h    │
  └─────────────────┬──────────────────────┘
                    │
                    ▼
  ┌────────────────────────────────────────┐
  │          oled_driver                    │
  │  ─ 依赖: TwoWire, U8g2/Adafruit,       │
  │          config.h, types.h              │
  └─────────────────┬──────────────────────┘
                    │
                    ▼
  ┌────────────────────────────────────────┐
  │       pc_comm_handler                   │
  │  ─ 依赖: HardwareSerial, ArduinoJson,  │
  │          protocol.h, types.h            │
  └─────────────────┬──────────────────────┘
                    │
                    ▼
  ┌─────────────────────────────────────────┐
  │         state_machine (核心)            │
  │  ─ 依赖: radar_driver, gesture_driver,  │
  │          oled_driver, pc_comm_handler,  │
  │          config.h, types.h, utils/*     │
  │  ─ 控制: LED pin, Buzzer pin           │
  └──────────────────┬─────────────────────┘
                     │
                     ▼
  ┌─────────────────────────────────────────┐
  │          main.cpp / main.ino            │
  │  ─ 初始化和连接所有模块                 │
  └─────────────────────────────────────────┘
```

### 9.2 依赖关系矩阵

| 模块 | 硬件依赖 | 软件依赖 | 对外提供 |
|------|---------|---------|---------|
| `radar_driver` | UART (GPIO43/44), OUT (GPIO21) | `config.h`, `types.h` | `RadarData`, `on_data_received()` |
| `gesture_driver` | I2C (GPIO8/18), INT (GPIO17) | `config.h`, `types.h` | `GestureType`, `on_gesture()` |
| `oled_driver` | I2C (GPIO8/18) | `config.h`, U8g2库 | `show_*()` 渲染方法 |
| `pc_comm_handler` | USB CDC | `config.h`, `ArduinoJson` | `send_*()`, `on_command()` |
| `state_machine` | LED (GPIO2), 蜂鸣器 (GPIO5) | 以上所有模块 + `utils/*` | 状态管理、事件分发 |
| `main.cpp` | — | 所有模块 | 初始化、主循环调度 |
| `utils/logger` | 串口 | — | 日志输出 |
| `utils/watchdog` | — | ESP32 内置 WDT | 系统稳定性保障 |

### 9.3 关键依赖注意事项

1. **I2C 总线共享**：OLED 和 PAJ7620U2 共用同一 I2C 总线（GPIO8/18），需确保地址不冲突。SSD1306 默认地址 `0x3C`，PAJ7620U2 默认地址 `0x73`（或可配置），地址不冲突。

2. **UART 冲突风险**：LD2410B 使用 UART 接口，需注意不与调试串口（Serial）冲突。推荐使用 `Serial1`（硬件 UART1），配置 GPIO43/44 或根据原理图自定义。

3. **USB CDC 优先级**：`Serial` 在 Arduino-ESP32 上默认映射到 USB CDC。PC 通信和调试日志共用此接口，需设计协议区分。

4. **中断优先级**：手势传感器中断（INT）使用 GPIO 中断，Isr 应尽量短（仅置标志位），在主循环中处理 I2C 读取。

---

## 10. 开发路线图（6阶段）

### 阶段 1：基础硬件验证（第1周）

**目标**：确认硬件连接正确，各模块独立工作。

| 任务 | 输出 | 验证标准 |
|------|------|---------|
| 1.1 搭建开发环境（PlatformIO + Arduino-ESP32） | 可编译的空项目 | `Hello World` 串口输出 |
| 1.2 验证电源供电（AMS1117-3.3 输出 3.3V） | 万用表测量 | 3.3V ± 5% |
| 1.3 LD2410B UART 通信验证 | 裸串口读取雷达数据帧 | 收到 F4F3F2F1...F8F7F6F5 |
| 1.4 OLED I2C 通信验证 | I2C 扫描 + 显示"Hello" | 地址 0x3C 可应答 |
| 1.5 PAJ7620U2 I2C 通信验证 | I2C 扫描 + 读取 ID | 地址 0x73 可应答 |
| 1.6 USB CDC 通信验证 | PC 端串口助手收发数据 | 双向通信正常 |

**里程碑**：硬件平台验证通过 ✅

### 阶段 2：驱动开发（第2-3周）

**目标**：各模块驱动独立开发与单元测试。

| 任务 | 输出 | 验证标准 |
|------|------|---------|
| 2.1 `radar_driver` 开发 | 雷达帧解析、数据回调、OUT 引脚读取 | 正确解析 target_state/dist/energy |
| 2.2 `gesture_driver` 开发 | PAJ7620U2 初始化+手势检测回调 | 检测 8 种手势，串口打印 |
| 2.3 `oled_driver` 开发 | SSD1306 显示 + 基本 UI 渲染 | 显示文字/图标/柱状图 |
| 2.4 `pc_comm_handler` 开发 | JSON 序列化/反序列化 + USB CDC | 收发 JSON 消息 |
| 2.5 雷达配置命令实现 | LD2410B 配置帧发送 | 成功修改阈值/灵敏度 |

**里程碑**：各模块独立通过测试 ✅

### 阶段 3：状态机实现与集成（第4周）

**目标**：实现防偷窥状态机，集成所有模块。

| 任务 | 输出 | 验证标准 |
|------|------|---------|
| 3.1 状态机 `state_machine` 核心实现 | 6 状态 + 状态转换 | 单元测试覆盖所有转换路径 |
| 3.2 集成雷达 → 状态机 | 真实雷达数据驱动状态机 | 手动测试 N→H→A→S→P→A 路径 |
| 3.3 集成手势 → 状态机 | 手势触发状态转换 | 顺时针确认/逆时针解除 |
| 3.4 集成 OLED → 状态机 | 状态变化自动更新屏幕 | 6 种状态显示正确 |
| 3.5 集成 PC 通信 → 状态机 | 状态上报 + 命令接收 | PC 端收到正确 JSON |
| 3.6 LED/蜂鸣器控制 | GPIO 输出控制 | 状态对应灯色/声音 |

**里程碑**：系统闭环运行 ✅

### 阶段 4：PC 端上位机开发（第5周）

**目标**：开发 PC 端监控上位机。

| 任务 | 输出 | 验证标准 |
|------|------|---------|
| 4.1 PC 端串口通信模块 | `serial_comm.py` | 稳定收发 JSON |
| 4.2 状态监控与可视化 | GUI 显示当前状态/距离/能量 | 实时更新 |
| 4.3 日志记录 | 日志文件记录 JSON 流 | 检索/过滤 |
| 4.4 配置下发界面 | 阈值/灵敏度设置界面 | 参数持久化 |
| 4.5 状态机可视化 | 图形化显示状态转换 | 可视化动效 |

**里程碑**：PC 端可完整监控和控制 ✅

### 阶段 5：系统测试与优化（第6周）

**目标**：系统级测试，性能调优，BUG 修复。

| 任务 | 输出 | 验证标准 |
|------|------|---------|
| 5.1 功能测试 | 测试用例执行报告 | 所有功能用例通过 |
| 5.2 性能测试 | 帧率/延迟/CPU 占用 | loop() 周期 < 50ms |
| 5.3 稳定性测试 | 72 小时连续运行 | 无死机/重启/数据丢失 |
| 5.4 边界测试 | 极端距离/能量/手势 | 系统不崩溃 |
| 5.5 抗干扰测试 | 多人/多方向/遮挡 | 误报率 < 5% |
| 5.6 散热测试 | AMS1117 温度监测 | 温升 < 40°C |

**里程碑**：系统稳定可靠 ✅

### 阶段 6：文档完善与交付（第7周）

**目标**：项目文档完善，交付。

| 任务 | 输出 |
|------|------|
| 6.1 硬件设计文档 | `02-hardware-design.md` |
| 6.2 LD2410B 协议说明 | `03-ld2410b-protocol.md` |
| 6.3 状态机详细规格 | `04-state-machine-spec.md` |
| 6.4 PC 通信协议文档 | `05-pc-comm-protocol.md` |
| 6.5 测试报告 | `06-test-plan.md` + 测试日志 |
| 6.6 用户手册 | `README.md` + 使用说明 |

**里程碑**：项目交付 ✅

---

## 11. 风险评估与备选方案

### 11.1 风险矩阵

| 风险编号 | 风险描述 | 概率 | 影响 | 等级 | 缓解措施 |
|---------|---------|------|------|------|---------|
| R1 | **AMS1117-3.3 过热**：线性稳压在 5V→3.3V/400mA 下功耗 0.68W，可能 >85°C | 中 | 高 | ① 增加散热焊盘/铜箔 ② 加装小型散热片 ③ 评估换 DC-DC（如 TPS63060） |
| R2 | **引脚分配错误**：原理图符号与 GPIO 编号不对应 | 高 | 高 | ① 开发前确认原理图 ② 使用 `#error` 宏让确认前无法编译 ③ 备选 2-3 组引脚映射 |
| R3 | **UART 波特率不匹配**：LD2410B 默认 256000，部分模块波特率漂移 | 低 | 中 | ① 配置后回读验证 ② 实现自动波特率检测 ③ 备选 115200 配置 |
| R4 | **雷达帧解析丢包**：UART 缓冲区溢出导致帧丢失 | 中 | 中 | ① 增大串口 RX 缓冲区 ② 帧同步机制 ③ DMA 接收 |
| R5 | **I2C 总线冲突**：OLED 与手势传感器同时访问 I2C 导致延迟 | 低 | 中 | ① 分时访问 ② 降低时钟至 100kHz ③ 使用 I2C 多路复用器 |
| R6 | **手势传感器误触发**：PAJ7620U2 在强光/快速移动时误报 | 中 | 低 | ① 增加去抖动 ② 连续检测确认 ③ 特定状态下才启用手势 |
| R7 | **JSON 解析内存不足**：ArduinoJson 在大 JSON 时堆溢出 | 中 | 高 | ① 限制 JSON 大小 ② 使用静态分配 ③ 流式解析 |
| R8 | **USB CDC 断开/重连**：PC 端串口断开后 ESP32 阻塞 | 中 | 中 | ① 实现非阻塞发送 ② 检测 CDC 连接状态 ③ 超时丢弃 |
| R9 | **电源纹波/噪声**：影响 LD2410B 测距精度 | 低 | 中 | ① 增加 π 型滤波 ② 雷达独立 LDO ③ 数字滤波算法 |
| R10 | **状态机死锁**：异常输入导致状态机进入未定义状态 | 低 | 高 | ① 看门狗 ② 状态超时自动复位 ③ 最大状态跳转次数 |

### 11.2 备选方案

#### 方案 A：传感器更换

| 需求 | 主选 | 备选 1 | 备选 2 |
|------|------|--------|--------|
| 人体存在检测 | LD2410B (24GHz 毫米波) | LD2410 (无蓝牙版) | RCWL-0516 (微波雷达, 无距离信息) |
| 手势识别 | PAJ7620U2 (I2C) | APDS-9960 (I2C, 色感+手势+接近) | 用双 LD2410B 三角测距实现 |
| OLED 显示 | SSD1306 128×64 I2C | SH1106 128×64 I2C | 无 OLED, 仅 PC 端显示 |

#### 方案 B：主控更换

| 主选 | 备选 | 理由 |
|------|------|------|
| ESP32-S3 | ESP32-C3 (单核 RISC-V) | 成本更低，但 GPIO 更少 |
| ESP32-S3 | ESP32-WROOM-32 (传统双核) | 库存更充足，但无原生 USB CDC |
| ESP32-S3 | RP2040 (Raspberry Pi Pico) | 成本低，但无原生 USB Host |

#### 方案 C：通信方式更换

| 主选 | 备选 | 理由 |
|------|------|------|
| USB CDC | UART via CP2102 | 若原生 USB 不稳定可用外部 USB-UART 桥 |
| USB CDC | WiFi (TCP/UDP) | 若需要远程监控，增加 WiFi 模块 |
| USB CDC | BLE | 若使用手机端作为上位机 |

#### 方案 D：供电方案更换

| 主选 | 备选 | 理由 |
|------|------|------|
| AMS1117-3.3 (线性) | TPS63060 (DC-DC buck-boost) | 效率 >90%，但成本高 3x、PCB 面积大 |
| AMS1117-3.3 | MP2315 (DC-DC buck) | 效率 >85%，成本适中，需额外电感 |
| AMS1117-3.3 | 保留 + 散热片 | 最简单，成本最低 |

### 11.3 应对策略优先级

```
高风险 | ┌───────────────────┐
高影响 | │ R2 (引脚错误)    │ 立即确认原理图
       │ │ R7 (JSON OOM)   │ 限制 payload，预分配
       │ │ R10 (状态机死锁)│ 看门狗 + 超时复位
       ├───────────────────┤
       │ R1 (散热)          │ 实测后决定是否更换方案
       │ R4 (UART 丢包)    │ 增大缓冲区 / DMA
       │ R8 (CDC 阻塞)     │ 非阻塞发送
低风险 | └───────────────────┘
       低影响 ──────────► 高影响
```

---

## 附录 A：术语表

| 术语 | 说明 |
|------|------|
| LD2410B | 24GHz 毫米波雷达模组，支持人体存在/运动/静止检测，UART 接口 |
| PAJ7620U2 | 手势识别传感器，支持 9 种手势，I2C 接口 |
| SSD1306 | OLED 驱动芯片，128×64 分辨率，I2C 接口 |
| AMS1117-3.3 | 3.3V 线性稳压器，最大输出 1A |
| USB CDC | USB Communication Device Class，虚拟串口 |
| ESP32-S3 | 乐鑫双核 Xtensa LX7 微控制器，集成 USB OTG |
| UART | 通用异步收发传输器 |
| I2C | 集成电路总线（Inter-Integrated Circuit） |
| JSON | JavaScript Object Notation，轻量级数据交换格式 |
| PlatformIO | 跨平台嵌入式开发工具链 |
| FreeRTOS | 实时操作系统，ESP-IDF 底层系统 |
| OTA | Over-The-Air，空中固件升级 |
| WDT | Watchdog Timer，看门狗定时器 |

---

## 附录 B：引脚确认清单

> 📋 **使用前必须逐项确认以下引脚**（参考原理图符号与 PCB 布局）：

| 网络标号 | ESP32 引脚号 (U1.xx) | 推测 GPIO | 实际 GPIO (待填写) | 确认人 | 确认日期 |
|---------|---------------------|-----------|-------------------|-------|---------|
| TX_RADAR | U1.10 | GPIO44 (?) | | | |
| RX_RADAR | U1.11 | GPIO43 (?) | | | |
| OUT | U1.23 | GPIO21 (?) | | | |
| SCL | U1.5 | GPIO18 (?) | | | |
| SDA | U1.4 | GPIO8 (?) | | | |
| IO8 | U1.12 / U6.3 | GPIO17 (?) | | | |
| IO0 | U1.27 | GPIO0 | — | — | — |
| EN | — | EN | — | — | — |

---

> **文档结束** — 本文档涵盖了 SmartOffice 防偷窥隐私保护系统的完整架构设计。请在确认硬件引脚后更新 config.h 中的引脚定义，并开始阶段 1 的开发工作。
