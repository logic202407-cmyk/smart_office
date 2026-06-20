# ESP32 固件开发计划

> 项目：SmartOffice PeepPrevention — 办公防偷窥雷达系统
> 芯片：ESP32-S3-WROOM-1-N8R2
> 框架：PlatformIO + Arduino-ESP32
> 生成日期：2026-05-08

---

## 目录

1. [Arduino-ESP32 vs ESP-IDF 选型推荐](#1-arduino-esp32-vs-esp-idf-选型推荐)
2. [UART 驱动设计（LD2410B 256000 波特率）](#2-uart-驱动设计ld2410b-256000-波特率)
3. [防偷窥状态机 C 语言实现方案](#3-防偷窥状态机-c-语言实现方案)
4. [OLED 显示驱动（I2C SSD1306）](#4-oled-显示驱动i2c-ssd1306)
5. [PAJ7620U2 手势驱动接口预留](#5-paj7620u2-手势驱动接口预留)
6. [USB CDC 通信实现](#6-usb-cdc-通信实现)
7. [config.h 引脚宏定义方案](#7-configh-引脚宏定义方案)
8. [需用户确认的引脚标注（TODO）](#8-需用户确认的引脚标注todo)
9. [每阶段可独立测试的构建方案](#9-每阶段可独立测试的构建方案)
10. [PlatformIO 工程配置建议](#10-platformio-工程配置建议)

---

## 1. Arduino-ESP32 vs ESP-IDF 选型推荐

### 结论：推荐 Arduino-ESP32 框架（通过 PlatformIO 使用）

| 维度 | Arduino-ESP32 | ESP-IDF |
|------|---------------|---------|
| **底层关系** | 基于 ESP-IDF 封装（v3.x 对应 IDF 5.x） | 原生 SDK |
| **学习曲线** | 低，Arduino API 通用性强 | 高，需理解 FreeRTOS + 组件体系 |
| **SSD1306 OLED 库** | Adafruit SSD1306 / U8g2 开箱即用 | 需自行移植或使用 IDF 组件管理器 |
| **PAJ7620U2 库** | 社区有成熟 Arduino 库 | 无现成，需从寄存器层开发 |
| **USB CDC** | `Serial` 自动可用（S3 原生 USB） | 需手动配置 TinyUSB 栈 |
| **UART 高速 (256000)** | `HardwareSerial` 可用，但高负载下可能丢包 | `uart_driver_install()` 支持 DMA，可靠性更高 |
| **调试友好度** | `Serial.print()` 即用 | 需配置 esp_log 或自定义输出 |
| **生产稳定性** | 足够（底层仍是 IDF） | 原生，极致可靠 |

### 推荐理由

1. **生态成熟度**：OLED（SSD1306）和 PAJ7620U2 手势传感器在 Arduino 生态中有经过验证的库，ESP-IDF 下需大量自研。
2. **开发效率**：项目需快速迭代验证，Arduino 框架让原型—产品转化路径最短。
3. **混合能力**：PlatformIO 下可在 Arduino 主框架中直接调用 **ESP-IDF 原生 API**（`uart_driver_install`、`gpio_config` 等），既享受库生态又保留底层控制。
4. **USB CDC 零配置**：ESP32-S3 的 `Serial` 对象在 Arduino 框架下自动切换为 USB CDC（当 `USB_CDC` 启用时），无需手动处理 TinyUSB。

### 关键取舍：UART 部分使用 IDF 原生驱动

对于 LD2410B 的 **256000 波特率 + 状态机帧解析**，建议在 Arduino 工程中**单独调用 ESP-IDF 的 UART 驱动**（`driver/uart.h`）：
- 启用 UART DMA 环形缓冲区，防止 RX 溢出
- 保证 256000 波特率下无丢失字节
- Arduino 的 `HardwareSerial` 用于调试输出（UART0/USB）

> **架构模式**：Arduino `setup()`/`loop()` 做顶层编排，底层 UART 驱动调用 IDF API。

---

## 2. UART 驱动设计（LD2410B 256000 波特率）

### 2.1 硬件连接

| 信号 | 雷达端 | 网络标号 | ESP32 端 | 猜测 GPIO |
|------|--------|----------|----------|-----------|
| OUT  | U2.1   | IO21     | U1.23    | GPIO17（TODO 确认）|
| TX   | U2.2   | TX_RADAR | U1.10    | GPIO11（TODO 确认）|
| RX   | U2.3   | RX_RADAR | U1.11    | GPIO12（TODO 确认）|

> **OUT 引脚**：雷达模块的人体存在指示 GPIO，高电平=有人，低电平=无人。可作为状态机的辅助唤醒信号。

### 2.2 UART 参数

| 参数 | 值 |
|------|-----|
| 波特率 | **256000** |
| 数据位 | 8 |
| 校验位 | 无 (N) |
| 停止位 | 1 |
| 硬件流控 | 无 |
| 驱动方式 | ESP-IDF UART DMA |

### 2.3 驱动初始化（IDF 原生 API 方式）

```c
// uart_driver.h — 在 Arduino 工程中直接调用
#include "driver/uart.h"
#include "driver/gpio.h"

#define RADAR_UART_PORT     UART_NUM_1  // 使用 UART1，UART0 给调试串口
#define RADAR_UART_TX       GPIO_NUM_12 // GPIO12 — TODO 需确认
#define RADAR_UART_RX       GPIO_NUM_11 // GPIO11 — TODO 需确认
#define RADAR_UART_BUF_SIZE (1024)      // DMA 环形缓冲区
#define RADAR_UART_QUEUE_LEN (20)

static QueueHandle_t uart_event_queue;

void radar_uart_init(void) {
    /* 配置 UART 参数 */
    uart_config_t uart_config = {
        .baud_rate = 256000,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    uart_param_config(RADAR_UART_PORT, &uart_config);

    /* 设置引脚 */
    uart_set_pin(RADAR_UART_PORT, RADAR_UART_TX, RADAR_UART_RX,
                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);

    /* 安装驱动（DMA 模式） */
    uart_driver_install(RADAR_UART_PORT, RADAR_UART_BUF_SIZE,
                        RADAR_UART_BUF_SIZE, RADAR_UART_QUEUE_LEN,
                        &uart_event_queue, 0);  // 0 = 不使用中断, 用队列
}
```

### 2.4 帧协议格式（LD2410B）

#### 上报帧（雷达→MCU，主动推送）

```
Byte0~3:  F4 F3 F2 F1        — 帧头
Byte4~5:  Length (LE)        — 后续数据长度（不含帧头长度和校验）
Byte6:    Type               — 0x02 = 基本信息上报
Byte7:    AA                 — 固定值
Byte8:    target_state       — 0x00=无人, 0x01=有人
Byte9~10: moving_dist (LE)   — 运动目标距离 (cm)
Byte11:   moving_energy      — 运动目标能量
Byte12~13: static_dist (LE)  — 静态目标距离 (cm)
Byte14:   static_energy      — 静态目标能量
Byte15~16: detect_dist (LE)  — 检测距离 (cm)
Byte17:   55                 — 分隔
Byte18:   Check              — 校验和
Byte19~22: F8 F7 F6 F5       — 帧尾
```

**校验和算法**：从 F4 到 55（含）的所有字节累加，取低 8 位，然后 `Check = 0x100 - (sum & 0xFF)`，若 sum=0 则 Check=0。

#### 配置帧（MCU→雷达）

```
Byte0~3:  FD FC FB FA        — 配置帧头
Byte4~5:  Length (LE)        — 后续长度
Byte6~7:  Cmd (LE)           — 命令字
Byte8~N:  Value              — 命令参数
Byte(N+1~N+4): 04 03 02 01  — 配置帧尾
```

#### ACK 帧（雷达→MCU，响应配置）

```
Byte0~3:  FD FC FB FA        — 帧头
Byte4~5:  Length (LE)
Byte6~7:  Cmd | 0x0100       — 命令应答
Byte8:    ReturnValue        — 0=成功
Byte(N+1~N+4): 04 03 02 01
```

### 2.5 状态机帧解析器

```c
typedef enum {
    FRAME_IDLE,
    FRAME_HEADER1,  // F4
    FRAME_HEADER2,  // F3
    FRAME_HEADER3,  // F2
    FRAME_HEADER4,  // F1
    FRAME_LENGTH_L,
    FRAME_LENGTH_H,
    FRAME_DATA,
    FRAME_SEP_55,   // 分隔符
    FRAME_CHECK,
    FRAME_FOOTER1,  // F8
    FRAME_FOOTER2,  // F7
    FRAME_FOOTER3,  // F6
    FRAME_FOOTER4,  // F5
    FRAME_DONE
} radar_frame_state_t;

typedef struct {
    uint8_t  raw[64];           // 最大帧长度
    uint16_t raw_len;           // 已接收长度
    uint16_t data_len;          // 从帧头解析的 Length 字段
    uint16_t data_index;        // 当前 data 写入位置

    uint8_t  target_state;      // 解析结果：目标状态
    uint16_t moving_dist;
    uint8_t  moving_energy;
    uint16_t static_dist;
    uint8_t  static_energy;
    uint16_t detect_dist;
    bool     frame_ready;       // 帧解析完成标志

    radar_frame_state_t state;
} radar_parser_t;

void radar_parser_feed(radar_parser_t *p, uint8_t byte) {
    if (p->frame_ready) return;  // 等待消费

    p->raw[p->raw_len++] = byte;

    switch (p->state) {
        case FRAME_IDLE:
            p->raw_len = 0;
            if (byte == 0xF4) p->state = FRAME_HEADER1;
            break;
        case FRAME_HEADER1:
            p->state = (byte == 0xF3) ? FRAME_HEADER2 : FRAME_IDLE;
            break;
        case FRAME_HEADER2:
            p->state = (byte == 0xF2) ? FRAME_HEADER3 : FRAME_IDLE;
            break;
        case FRAME_HEADER3:
            p->state = (byte == 0xF1) ? FRAME_LENGTH_L : FRAME_IDLE;
            break;
        case FRAME_LENGTH_L:
            p->data_len = byte;
            p->data_index = 0;
            p->state = FRAME_LENGTH_H;
            break;
        case FRAME_LENGTH_H:
            p->data_len |= (uint16_t)(byte << 8);
            if (p->data_len > 0 && p->data_len <= 20) {
                p->state = FRAME_DATA;
            } else {
                p->state = FRAME_IDLE;  // 非法长度
            }
            break;
        case FRAME_DATA:
            // 按字段偏移存储解析结果（参考协议）
            if (p->data_index == 1) p->target_state  = byte;  // 偏移1: AA之后
            if (p->data_index == 2) p->moving_dist   = byte;  // 目标距离L
            // ... 完整解析详见源文件
            p->data_index++;
            if (p->data_index >= p->data_len) p->state = FRAME_SEP_55;
            break;
        case FRAME_SEP_55:
            p->state = (byte == 0x55) ? FRAME_CHECK : FRAME_IDLE;
            break;
        case FRAME_CHECK: {
            uint8_t calc = radar_checksum(p->raw, p->raw_len);
            if (calc == byte) {
                p->state = FRAME_FOOTER1;
            } else {
                p->state = FRAME_IDLE;  // 校验失败
            }
            break;
        }
        case FRAME_FOOTER1: p->state = (byte == 0xF8) ? FRAME_FOOTER2 : FRAME_IDLE; break;
        case FRAME_FOOTER2: p->state = (byte == 0xF7) ? FRAME_FOOTER3 : FRAME_IDLE; break;
        case FRAME_FOOTER3: p->state = (byte == 0xF6) ? FRAME_FOOTER4 : FRAME_IDLE; break;
        case FRAME_FOOTER4:
            if (byte == 0xF5) {
                p->frame_ready = true;
                // 完整解析 raw 中的数据字段
                radar_parse_fields(p);
            }
            p->state = FRAME_IDLE;
            break;
    }
}
```

### 2.6 粘包与半包处理策略

| 场景 | 处理方式 |
|------|---------|
| **粘包**（一次收到多帧） | 解析完一帧后 `frame_ready=true`，后续字节暂存，待上层 `radar_parser_consume()` 后继续解析下一帧 |
| **半包**（帧被截断） | 状态机停留在当前状态，等待后续字节填充。超时（50ms 无数据）自动复位到 `FRAME_IDLE` |
| **错误字节** | 任何状态匹配失败均回退 `FRAME_IDLE`，丢弃已累积字节 |
| **DMA 溢出** | 设置足够大的环形缓冲区（1024 字节），256000bps 下约 32ms 填满 |

```c
// 半包超时看门狗 — 在主循环或定时器中调用
void radar_parser_timeout_check(radar_parser_t *p, uint32_t now_ms) {
    static uint32_t last_byte_time = 0;
    if (p->state != FRAME_IDLE && (now_ms - last_byte_time > 50)) {
        p->state = FRAME_IDLE;  // 超时复位
        p->raw_len = 0;
    }
    if (/* 有新字节 */) last_byte_time = now_ms;
}
```

### 2.7 DMA 读取任务

```c
void radar_uart_task(void *arg) {
    uart_event_t event;
    uint8_t buffer[256];

    while (1) {
        if (xQueueReceive(uart_event_queue, &event, portMAX_DELAY)) {
            switch (event.type) {
                case UART_DATA:
                    uart_read_bytes(RADAR_UART_PORT, buffer, event.size, 0);
                    for (int i = 0; i < event.size; i++) {
                        radar_parser_feed(&g_radar_parser, buffer[i]);
                    }
                    break;
                case UART_FIFO_OVF:
                case UART_BUFFER_FULL:
                    uart_flush_input(RADAR_UART_PORT);
                    break;
                default:
                    break;
            }
        }
    }
}
```

---

## 3. 防偷窥状态机 C 语言实现方案

### 3.1 状态定义

```c
typedef enum {
    STATE_NORMAL,              // 无人/正常 — 空闲状态
    STATE_HUMAN_DETECTED,      // 有人进入检测区（>150cm 或刚进入）
    STATE_APPROACHING,         // 接近中（80~150cm）
    STATE_SUSPECTED_PEEPING,   // 疑似偷窥（<80cm，持续 SUSPECT_TIME）
    STATE_PRIVACY_PROTECT,     // 隐私保护触发（屏幕模糊/息屏）
    STATE_ALARM,               // 告警（持续 ALARM_TIME 后恢复）
} peep_state_t;
```

### 3.2 参数阈值

| 参数 | 值 | 说明 |
|------|----|------|
| `NEAR_DIST` | 150 cm | 进入"接近"状态的阈值 |
| `VERY_NEAR` | 80 cm | 进入"疑似偷窥"状态的阈值 |
| `SUSPECT_TIME` | 3 s | 在 VERY_NEAR 区域停留超时进入隐私保护 |
| `ALARM_TIME` | 8 s | 告警持续时间 |
| `NO_TARGET_TIMEOUT` | 2 s | 雷达无目标后回到 NORMAL |

### 3.3 状态转移图

```
                     ┌─────────────────────────────────────────────┐
                     │                                             │
                     v                                             │
  ┌──────────┐  有人  ┌────────────┐  <150cm  ┌──────────────┐    │
  │  NORMAL  │───────>│  HUMAN     │─────────>│ APPROACHING  │    │
  │ (空闲)   │<───────│  DETECTED  │<─────────│ (接近中)      │    │
  └──────────┘ 超时2s └────────────┘  >150cm  └──────┬───────┘    │
       ^                                                |          │
       |                                            <80cm          │
       |                                                v          │
       |                                         ┌──────────────┐  │
       |              ┌──────────┐ 超时3s       │  SUSPECTED   │  │
       |              │  ALARM   │<─────────────│  PEEPING     │  │
       |              │ (告警8s) │              │ (疑似偷窥)    │  │
       |              └────┬─────┘              └──────────────┘  │
       |                   |                            |         │
       |                   | 超时8s                  触发         │
       |                   v                            v         │
       |              ┌──────────────┐         ┌────────────────┐ │
       └──────────────│ PRIVACY      │<────────│  触发隐私保护   │ │
                      │ PROTECT      │         └────────────────┘ │
                      └──────────────┘                            │
                           |  退出告警后                              │
                           └──────────────────────────────────────┘┘
```

### 3.4 状态机核心实现

```c
#include <stdint.h>
#include <stdbool.h>

/* ========== 配置（从 config.h 引入） ========== */
#define NEAR_DIST         150   // cm
#define VERY_NEAR         80    // cm
#define SUSPECT_TIME_MS   3000  // ms
#define ALARM_TIME_MS     8000  // ms
#define NO_TARGET_TIMEOUT_MS 2000 // ms

/* ========== 状态枚举 ========== */
typedef enum {
    STATE_NORMAL,
    STATE_HUMAN_DETECTED,
    STATE_APPROACHING,
    STATE_SUSPECTED_PEEPING,
    STATE_PRIVACY_PROTECT,
    STATE_ALARM,
} peep_state_t;

/* ========== 状态机上下文 ========== */
typedef struct {
    peep_state_t current_state;
    uint32_t     state_enter_time;  // ms, 进入当前状态的时间戳
    uint32_t     last_target_time;  // ms, 最后一次检测到目标的时间
    bool         target_present;    // 雷达当前是否检测到目标

    /* 雷达最新数据快照 */
    uint16_t     moving_dist;
    uint8_t      moving_energy;
    uint16_t     static_dist;
    uint8_t      static_energy;
    uint16_t     detect_dist;

    /* 回调函数指针 */
    void (*on_state_change)(peep_state_t new_state);
    void (*on_privacy_protect)(bool enable);
    void (*on_alarm)(void);
} peep_state_machine_t;

/* ========== 全局实例 ========== */
static peep_state_machine_t g_peep_sm;

/* ========== 状态机初始化 ========== */
void peep_sm_init(peep_state_machine_t *sm) {
    sm->current_state     = STATE_NORMAL;
    sm->state_enter_time  = 0;
    sm->last_target_time  = 0;
    sm->target_present    = false;
}

/* ========== 辅助：获取目标距离（运动中取小值，更保守） ========== */
static uint16_t peep_get_target_distance(const peep_state_machine_t *sm) {
    if (sm->moving_dist > 0 && sm->static_dist > 0) {
        return (sm->moving_dist < sm->static_dist) ? sm->moving_dist : sm->static_dist;
    }
    if (sm->moving_dist > 0) return sm->moving_dist;
    return sm->static_dist;
}

/* ========== 核心：状态转移逻辑（每秒调用一次或在雷达帧到达时调用） ========== */
void peep_sm_tick(peep_state_machine_t *sm, uint32_t now_ms) {
    uint16_t dist = peep_get_target_distance(sm);
    bool     has_target = sm->target_present;
    uint32_t elapsed_in_state = now_ms - sm->state_enter_time;

    switch (sm->current_state) {
        /* ---- NORMAL ---- */
        case STATE_NORMAL:
            if (has_target) {
                if (dist < VERY_NEAR) {
                    peep_sm_transition(sm, STATE_SUSPECTED_PEEPING, now_ms);
                } else if (dist < NEAR_DIST) {
                    peep_sm_transition(sm, STATE_APPROACHING, now_ms);
                } else {
                    peep_sm_transition(sm, STATE_HUMAN_DETECTED, now_ms);
                }
            }
            break;

        /* ---- HUMAN_DETECTED ---- */
        case STATE_HUMAN_DETECTED:
            if (!has_target && elapsed_in_state > NO_TARGET_TIMEOUT_MS) {
                peep_sm_transition(sm, STATE_NORMAL, now_ms);
            } else if (has_target) {
                if (dist < VERY_NEAR) {
                    peep_sm_transition(sm, STATE_SUSPECTED_PEEPING, now_ms);
                } else if (dist < NEAR_DIST) {
                    peep_sm_transition(sm, STATE_APPROACHING, now_ms);
                }
            }
            break;

        /* ---- APPROACHING ---- */
        case STATE_APPROACHING:
            if (!has_target && elapsed_in_state > NO_TARGET_TIMEOUT_MS) {
                peep_sm_transition(sm, STATE_NORMAL, now_ms);
            } else if (has_target) {
                if (dist >= NEAR_DIST) {
                    peep_sm_transition(sm, STATE_HUMAN_DETECTED, now_ms);
                } else if (dist < VERY_NEAR) {
                    peep_sm_transition(sm, STATE_SUSPECTED_PEEPING, now_ms);
                }
            }
            break;

        /* ---- SUSPECTED_PEEPING ---- */
        case STATE_SUSPECTED_PEEPING:
            if (!has_target) {
                peep_sm_transition(sm, STATE_NORMAL, now_ms);
            } else if (dist >= NEAR_DIST) {
                peep_sm_transition(sm, STATE_HUMAN_DETECTED, now_ms);
            } else if (dist >= VERY_NEAR) {
                peep_sm_transition(sm, STATE_APPROACHING, now_ms);
            } else if (elapsed_in_state >= SUSPECT_TIME_MS) {
                // 停留超过 SUSPECT_TIME → 触发隐私保护
                peep_sm_transition(sm, STATE_PRIVACY_PROTECT, now_ms);
                if (sm->on_privacy_protect) sm->on_privacy_protect(true);
            }
            break;

        /* ---- PRIVACY_PROTECT ---- */
        case STATE_PRIVACY_PROTECT:
            if (!has_target) {
                peep_sm_transition(sm, STATE_NORMAL, now_ms);
                if (sm->on_privacy_protect) sm->on_privacy_protect(false);
            } else if (dist >= VERY_NEAR) {
                // 退回到 APPROACHING — 恢复显示，进入告警
                peep_sm_transition(sm, STATE_APPROACHING, now_ms);
                if (sm->on_privacy_protect) sm->on_privacy_protect(false);
            } else if (elapsed_in_state >= ALARM_TIME_MS) {
                // 持续告警后回到 NORMAL
                peep_sm_transition(sm, STATE_ALARM, now_ms);
                if (sm->on_alarm) sm->on_alarm();
            }
            break;

        /* ---- ALARM ---- */
        case STATE_ALARM:
            if (!has_target || elapsed_in_state >= ALARM_TIME_MS) {
                peep_sm_transition(sm, STATE_NORMAL, now_ms);
                if (sm->on_privacy_protect) sm->on_privacy_protect(false);
            }
            break;
    }
}

/* ========== 状态切换工具函数 ========== */
static void peep_sm_transition(peep_state_machine_t *sm,
                                peep_state_t new_state,
                                uint32_t now_ms) {
    if (sm->current_state == new_state) return;
    sm->current_state    = new_state;
    sm->state_enter_time = now_ms;
    if (sm->on_state_change) {
        sm->on_state_change(new_state);
    }
}

/* ========== 雷达数据更新接口（由 UART 任务调用） ========== */
void peep_sm_update_radar(peep_state_machine_t *sm,
                          bool target_present,
                          uint16_t moving_dist,
                          uint16_t static_dist,
                          uint16_t detect_dist,
                          uint8_t moving_energy,
                          uint8_t static_energy) {
    sm->target_present = target_present;
    sm->moving_dist    = moving_dist;
    sm->static_dist    = static_dist;
    sm->detect_dist    = detect_dist;
    sm->moving_energy  = moving_energy;
    sm->static_energy  = static_energy;
    if (target_present) {
        sm->last_target_time = millis();
    }
}
```

### 3.5 状态与 UI/行为映射

| 状态 | OLED 显示 | 屏幕控制 | 串口输出 |
|------|-----------|----------|---------|
| NORMAL | 显示时间/安全图标 | 正常 | `[NORMAL] 安全` |
| HUMAN_DETECTED | 显示距离 + 人物图标 | 正常 | `[HUMAN] 检测到人，距离=%d cm` |
| APPROACHING | 距离 + 警告图标 | 正常 | `[APPROACH] 接近中，距离=%d cm` |
| SUSPECTED_PEEPING | 倒计时 + 红色警告 | 正常 | `[SUSPECT] 疑似偷窥，倒计时%d s` |
| PRIVACY_PROTECT | 隐私图标/模糊提示 | **触发隐私动作** | `[PRIVACY] 隐私保护已触发` |
| ALARM | 红色闪烁 + 报警 | 保持模糊 | `[ALARM] 告警中` |

---

## 4. OLED 显示驱动（I2C SSD1306）

### 4.1 硬件连接

| OLED 引脚 | 网络 | ESP32 引脚 | 猜测 GPIO |
|-----------|------|-----------|-----------|
| U4.3 SCL | SCL | U1.5 | GPIO9（TODO 确认）|
| U4.4 SDA | SDA | U1.4 | GPIO8（TODO 确认）|

### 4.2 库选型：U8g2（推荐）

| 库 | 优点 | 缺点 |
|----|------|------|
| **U8g2** | 中文显示、多字体、非阻塞刷新、低内存占用 | API 稍复杂 |
| Adafruit SSD1306 | 简单易用、示例丰富 | 无中文支持、需额外 GFX 库 |

**选择 U8g2** 原因为项目需显示中文（"安全"、"警告"、"隐私保护"等）。

### 4.3 初始化代码

```c
#include <U8g2lib.h>
#include <Wire.h>

#define OLED_SDA    GPIO_NUM_8   // TODO 需确认
#define OLED_SCL    GPIO_NUM_9   // TODO 需确认
#define OLED_ADDR   0x3C         // SSD1306 默认 I2C 地址
#define OLED_WIDTH  128
#define OLED_HEIGHT 64

U8G2_SSD1306_128X64_NONAME_1_HW_I2C u8g2(
    U8G2_R0,          // 旋转方向
    /* reset= */ U8X8_PIN_NONE,
    /* clock= */ OLED_SCL,
    /* data= */  OLED_SDA
);

void oled_init(void) {
    Wire.begin(OLED_SDA, OLED_SCL, 400000UL);  // 400kHz I2C
    u8g2.begin();
    u8g2.enableUTF8Print();  // 启用 UTF-8 中文支持
    u8g2.setFont(u8g2_font_wqy12_t_gb2312);  // 文泉驿 12px 中文字体
    u8g2.firstPage();
    do {
        u8g2.setCursor(0, 14);
        u8g2.print("系统启动中...");
    } while (u8g2.nextPage());
}
```

> **注意**：U8g2 的中文字体 `wqy12_t_gb2312` 和 `wqy16_t_gb2312` 需在 PlatformIO 的 `platformio.ini` 中启用字体编译：
> ```
> build_flags = -DU8G2_USE_LARGEST_FONT
> ```
> 或在使用前用 `U8g2lib.h` 中的字体声明宏。

### 4.4 显示内容层级

```
┌──────────────────────────┐
│  09:45:25        [安全]  │  ← 顶部栏：时间 + 状态
│                          │
│  距离: 052 cm            │  ← 雷达数据
│  状态: 接近中            │
│                          │
│  ████████░░░░  68%       │  ← 进度/能量条（可选）
│                          │
│  [系统正常]              │  ← 底部提示
└──────────────────────────┘
```

### 4.5 非阻塞刷新

```c
void oled_update(peep_state_machine_t *sm) {
    static uint32_t last_refresh = 0;
    uint32_t now = millis();
    if (now - last_refresh < 100) return;  // 最高 10fps
    last_refresh = now;

    u8g2.firstPage();
    do {
        // 根据 sm->current_state 渲染不同界面
        oled_render_status_bar(&u8g2, sm);
        oled_render_body(&u8g2, sm);
    } while (u8g2.nextPage());
}
```

---

## 5. PAJ7620U2 手势驱动接口预留

### 5.1 硬件连接

| PAJ7620U2 引脚 | 网络 | ESP32 引脚 | 猜测 GPIO |
|----------------|------|-----------|-----------|
| U6.5 SCL       | SCL  | U1.5      | GPIO9（与 OLED 共用 I2C 总线）|
| U6.2 SDA       | SDA  | U1.4      | GPIO8（与 OLED 共用 I2C 总线）|
| U6.3 INT       | IO8  | U1.12     | GPIO13（TODO 确认）|

> **I2C 地址**：PAJ7620U2 默认地址为 `0x73`，与 SSD1306（`0x3C`）不冲突，可共用同一 I2C 总线。

### 5.2 接口预留代码

```c
// ====== paj7620_driver.h (接口预留) ======

#ifndef PAJ7620_DRIVER_H
#define PAJ7620_DRIVER_H

#include <stdint.h>
#include <stdbool.h>

/* 手势枚举 —— 预留 */
typedef enum {
    GESTURE_NONE       = 0,
    GESTURE_UP         = 1,
    GESTURE_DOWN       = 2,
    GESTURE_LEFT       = 3,
    GESTURE_RIGHT      = 4,
    GESTURE_FORWARD    = 5,
    GESTURE_BACKWARD   = 6,
    GESTURE_CLOCKWISE  = 7,
    GESTURE_COUNT      = 8,
} gesture_type_t;

/* 手势回调函数类型 */
typedef void (*gesture_callback_t)(gesture_type_t gesture);

/* ====== API 声明 ====== */

/**
 * @brief 初始化 PAJ7620U2 传感器
 * @param sda_pin  I2C SDA 引脚
 * @param scl_pin  I2C SCL 引脚
 * @param int_pin  中断引脚（GPIO13，TODO 确认）
 * @return true 初始化成功
 */
bool paj7620_init(int sda_pin, int scl_pin, int int_pin);

/**
 * @brief 注册手势检测回调
 * @param cb 回调函数，在手势事件发生时被调用
 */
void paj7620_register_callback(gesture_callback_t cb);

/**
 * @brief 主循环中调用，轮询/检查中断，触发回调
 * @param now_ms 当前系统时间 (ms)
 */
void paj7620_task(uint32_t now_ms);

/**
 * @brief 设置手势检测灵敏度（预留）
 * @param sensitivity 0~100
 */
void paj7620_set_sensitivity(uint8_t sensitivity);

/**
 * @brief 进入/退出低功耗模式（预留）
 * @param enable true=低功耗
 */
void paj7620_set_low_power(bool enable);

#endif // PAJ7620_DRIVER_H
```

### 5.3 集成到主循环

```c
void setup() {
    oled_init();
    radar_uart_init();
    peep_sm_init(&g_peep_sm);

    // PAJ7620U2 —— 预留，暂不启用
    // if (paj7620_init(OLED_SDA, OLED_SCL, GPIO_PAJ7620_INT)) {
    //     paj7620_register_callback(on_gesture_event);
    // }
}

void loop() {
    uint32_t now = millis();

    // 阶段1: 雷达数据处理（通过事件队列，在 UART 任务中处理）
    // 阶段2: 状态机更新（10Hz）
    static uint32_t last_sm_tick = 0;
    if (now - last_sm_tick >= 100) {
        peep_sm_tick(&g_peep_sm, now);
        last_sm_tick = now;
    }

    // 阶段3: OLED 刷新（10Hz，非阻塞）
    oled_update(&g_peep_sm);

    // 阶段4: 手势检测 —— 预留
    // paj7620_task(now);

    // 阶段5: USB CDC 通信
    cdc_handle_commands();
}
```

### 5.4 预留的手势→状态机映射方案

| 手势 | 预期行为 |
|------|---------|
| 上滑 (UP) | 临时解除隐私保护（进入 OVERRIDE 5 分钟） |
| 下滑 (DOWN) | 强制进入隐私保护 |
| 左滑 (LEFT) | 切换 OLED 显示页面 |
| 右滑 (RIGHT) | 切换 OLED 显示页面 |
| 向前 (FORWARD) | 确认/进入菜单 |
| 向后 (BACKWARD) | 返回/退出 |

---

## 6. USB CDC 通信实现

### 6.1 硬件连接

| USB 信号 | ESP32-S3 引脚 |
|----------|--------------|
| D+       | GPIO20 (USB_D+) |
| D-       | GPIO19 (USB_D-) |

> ESP32-S3 内置 **原生 USB Serial/JTAG 控制器**，无需外部 USB-UART 桥接芯片。Arduino 框架下只需启用 `USB_CDC` 即可。

### 6.2 PlatformIO 配置

```ini
[env:esp32-s3-dev]
platform = espressif32
board = esp32-s3-devkitc-1
framework = arduino
board_build.mcu = esp32s3
board_build.f_cpu = 240000000L

; === 启用 USB CDC ===
board_build.arduino.usb_cdc = true
board_build.arduino.usb_serial = true

; === USB 设备描述 ===
build_flags =
    -DARDUINO_USB_CDC_ON_BOOT=1
    -DARDUINO_USB_MODE=1
    -DARDUINO_RUNNING_CORE=1
    -DUSB_VID=0x303A
    -DUSB_PID=0x1001
    -DUSB_MANUFACTURER="SmartOffice"
    -DUSB_PRODUCT="PeepPrevention"
```

### 6.3 通信协议（简单文本行协议，便于调试）

```
格式: $CMD[,param1,param2,...]\n

命令表（预留）：

| 命令           | 方向        | 说明                     |
|----------------|-------------|--------------------------|
| $INFO\n        | PC→ESP      | 请求设备信息             |
| $STATE\n       | PC→ESP      | 请求当前状态机状态       |
| $RADAR\n       | PC→ESP      | 请求雷达原始数据         |
| $OLED,msg\n    | PC→ESP      | 临时在 OLED 上显示消息   |
| $RESET\n       | PC→ESP      | 软件复位                  |
| $CALIB\n       | PC→ESP      | 触发传感器校准            |
| > OK\n         | ESP→PC      | 命令成功                 |
| > ERROR,msg\n  | ESP→PC      | 命令错误                 |
| > STATE,NORMAL\n | ESP→PC    | 状态推送                 |
| > RADAR,dist,energy\n | ESP→PC | 雷达数据推送              |

数据推送（ESP→PC，自动发送，1Hz）：
> STATE,APPROACHING,dist=120,energy=45
```

### 6.4 CDC 接收处理

```c
#define CDC_CMD_BUFFER_SIZE  64

static char cdc_cmd_buffer[CDC_CMD_BUFFER_SIZE];
static uint8_t cdc_cmd_index = 0;

void cdc_handle_commands(void) {
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (cdc_cmd_index > 0) {
                cdc_cmd_buffer[cdc_cmd_index] = '\0';
                cdc_process_line(cdc_cmd_buffer);
                cdc_cmd_index = 0;
            }
        } else if (cdc_cmd_index < CDC_CMD_BUFFER_SIZE - 1) {
            cdc_cmd_buffer[cdc_cmd_index++] = c;
        }
    }
}

void cdc_process_line(const char *line) {
    if (strncmp(line, "$INFO", 5) == 0) {
        Serial.println("> OK,SmartOffice PeepPrevention v0.1");
    } else if (strncmp(line, "$STATE", 6) == 0) {
        peep_state_t s = g_peep_sm.current_state;
        Serial.printf("> STATE,%d\n", s);
    } else {
        Serial.printf("> ERROR,unknown command: %s\n", line);
    }
}
```

### 6.5 调试三通道方案

| 通道 | 用途 | 方式 |
|------|------|------|
| **USB CDC (Serial)** | 命令交互 + 数据推送 | 通过 USB Type-C |
| **UART0 (GPIO43/44)** | 调试日志（可选） | 物理串口线 |
| **OLED** | 本地状态显示 | I2C |

> 开发阶段可同时使用 USB CDC 和 UART0 串口输出日志；量产版本仅保留 USB CDC。

---

## 7. config.h 引脚宏定义方案

### 7.1 文件位置

```
firmware/
├── include/
│   ├── config.h              ← 引脚定义 + 编译配置
│   ├── radar_parser.h
│   ├── peep_state_machine.h
│   ├── oled_driver.h
│   ├── paj7620_driver.h
│   └── cdc_handler.h
├── src/
│   ├── main.cpp
│   ├── radar_parser.cpp
│   ├── peep_state_machine.cpp
│   ├── oled_driver.cpp
│   ├── paj7620_driver.cpp
│   └── cdc_handler.cpp
├── platformio.ini
└── ...
```

### 7.2 config.h 完整定义

```c
#ifndef CONFIG_H
#define CONFIG_H

#include <stdint.h>

/* ==================================================================
 *  引脚映射 —— GPIO 编号（TODO：所有值需用户根据实际原理图确认）
 *
 *  当前映射基于 ESP32-S3-WROOM-1-N8R2 常见原理图符号推测：
 *    U1.4  → GPIO8   (SDA)
 *    U1.5  → GPIO9   (SCL)
 *    U1.10 → GPIO11  (UART RX — 雷达TX)
 *    U1.11 → GPIO12  (UART TX — 雷达RX)
 *    U1.12 → GPIO13  (IO8 — PAJ7620 INT)
 *    U1.23 → GPIO17  (IO21 — 雷达OUT)
 *    U1.27 → GPIO20  (IO0 — BOOT按键)
 *
 *  请核对硬件原理图，确认以下 GPIO 编号与 PCB 走线一致。
 * ================================================================== */

// ======================== I2C 总线 ========================
/** @brief I2C 数据线 (SDA) — 对应原理图 U1.4 网络 SDA */
#define PIN_I2C_SDA             GPIO_NUM_8    // TODO: 请确认 GPIO8 = U1.4
/** @brief I2C 时钟线 (SCL) — 对应原理图 U1.5 网络 SCL */
#define PIN_I2C_SCL             GPIO_NUM_9    // TODO: 请确认 GPIO9 = U1.5

// ======================== OLED SSD1306 ========================
/** @brief OLED I2C 地址 (SSD1306 默认 0x3C) */
#define OLED_I2C_ADDR           (0x3C)
/** @brief OLED 屏幕宽度 (像素) */
#define OLED_WIDTH              128
/** @brief OLED 屏幕高度 (像素) */
#define OLED_HEIGHT             64

// ======================== 雷达 LD2410B (UART1) ========================
/** @brief 雷达 UART 端口 (使用 UART1, UART0 保留给调试) */
#define RADAR_UART_PORT         UART_NUM_1
/** @brief 雷达 TX → ESP32 RX 引脚 — 对应 U2.2→U1.10 网络TX_RADAR */
#define PIN_RADAR_RX            GPIO_NUM_11   // TODO: 请确认 GPIO11 = U1.10
/** @brief 雷达 RX ← ESP32 TX 引脚 — 对应 U2.3←U1.11 网络RX_RADAR */
#define PIN_RADAR_TX            GPIO_NUM_12   // TODO: 请确认 GPIO12 = U1.11
/** @brief 雷达 OUT 引脚 (人体存在指示) — 对应 U2.1→U1.23 网络IO21 */
#define PIN_RADAR_OUT           GPIO_NUM_17   // TODO: 请确认 GPIO17 = U1.23
/** @brief UART 波特率 */
#define RADAR_BAUD_RATE         256000
/** @brief UART DMA 环形缓冲区大小 */
#define RADAR_UART_BUF_SIZE     1024

// ======================== PAJ7620U2 手势传感器 ========================
/** @brief PAJ7620U2 I2C 地址 (默认 0x73) */
#define PAJ7620_I2C_ADDR        (0x73)
/** @brief PAJ7620U2 中断引脚 — 对应 U6.3→U1.12 网络IO8 */
#define PIN_PAJ7620_INT         GPIO_NUM_13   // TODO: 请确认 GPIO13 = U1.12
/** @brief 是否启用手势传感器 (预留) */
#define ENABLE_GESTURE_SENSOR   0  // 0=关闭, 1=启用

// ======================== 按键 ========================
/** @brief BOOT 按键 (IO0) — 对应 U1.27 网络IO0, 10kΩ上拉+开关到GND */
#define PIN_BOOT_BUTTON         GPIO_NUM_20   // TODO: 请确认 GPIO20 = U1.27

// ======================== 状态机参数 ========================
/** @brief "接近"距离阈值 (cm) */
#define NEAR_DIST               150
/** @brief "疑似偷窥"距离阈值 (cm) */
#define VERY_NEAR               80
/** @brief 疑似偷窥判定超时 (ms) */
#define SUSPECT_TIME_MS         3000
/** @brief 告警持续时间 (ms) */
#define ALARM_TIME_MS           8000
/** @brief 无目标超时回到 NORMAL (ms) */
#define NO_TARGET_TIMEOUT_MS    2000

// ======================== 系统配置 ========================
/** @brief 状态机更新频率 (Hz) */
#define SM_TICK_INTERVAL_MS     100    // 10Hz
/** @brief OLED 刷新频率 (Hz) */
#define OLED_REFRESH_INTERVAL_MS 100   // 10Hz
/** @brief USB CDC 命令缓冲区大小 */
#define CDC_CMD_BUF_SIZE        64

#endif // CONFIG_H
```

---

## 8. 需用户确认的引脚标注（TODO）

### 8.1 引脚映射总表

| 网络标号 | 原理图引脚 | 猜测 GPIO | 功能 | 需确认？ | 风险等级 |
|---------|-----------|-----------|------|---------|---------|
| **SDA** | U1.4 | **GPIO8** | OLED + PAJ7620 I2C 数据 | **⚠️ 必须** | **高** — I2C 不通则所有显示/手势失效 |
| **SCL** | U1.5 | **GPIO9** | OLED + PAJ7620 I2C 时钟 | **⚠️ 必须** | **高** |
| **TX_RADAR** | U1.10 | **GPIO11** | ESP32 UART RX（收雷达数据） | **⚠️ 必须** | **高** — 雷达数据收不到 |
| **RX_RADAR** | U1.11 | **GPIO12** | ESP32 UART TX（发雷达配置） | **⚠️ 必须** | **中** — 配置发不出，仅影响配置功能 |
| **IO8** | U1.12 | **GPIO13** | PAJ7620 中断输入 | **✔ 确认** | **低** — 手势功能，初始禁用 |
| **IO21** | U1.23 | **GPIO17** | 雷达 OUT 输入（人体存在） | **⚠️ 必须** | **中** — 辅助唤醒信号 |
| **IO0** | U1.27 | **GPIO20** | BOOT 按键 | **✔ 建议** | **低** — 主要用于烧录和调试 |
| **EN** | U1.3 | — | 复位（10kΩ上拉+开关到GND） | — | 硬件直连，固件不涉及 |
| **USB_D+** | — | GPIO20 | USB CDC D+ | — | ESP32-S3 固定引脚 |
| **USB_D-** | — | GPIO19 | USB CDC D- | — | ESP32-S3 固定引脚 |

### 8.2 验证方法（给硬件工程师的确认清单）

| 确认方法 | 说明 |
|---------|------|
| **原理图反查** | 打开原理图，找到 U1 (ESP32-S3)，确认每个网络对应的 **GPIO 编号** 而非 U1 引脚号 |
| **万用表通断测试** | 从 ESP32-S3 的对应 GPIO 焊盘到目标器件引脚打通断 |
| **烧录测试固件** | 使用 `examples/digital/Blink` 逐个点亮目标 GPIO，示波器/万用表确认 |
| **I2C 扫描** | 运行 I2C 扫描例程，确认 `0x3C`（OLED）和 `0x73`（PAJ7620）出现 |

### 8.3 如果映射错误的应对方案

```c
/* ===== config.h 中的容错注释 ===== */
// 如果 U1.10 不是 GPIO11，请参考 ESP32-S3 数据手册确认映射关系：
//   ESP32-S3-WROOM-1-N8R2 的 IO 引脚编号 = 芯片 GPIO 号
//   检查原理图中 U1 的引脚编号是与芯片引脚一一对应，
//   还是与 WROOM 模块的 castellated 引脚对应
```

---

## 9. 每阶段可独立测试的构建方案

### 阶段划分总览

```
Phase 0: 工程脚手架 + LED Blink           ← 验证环境、烧录、USB CDC
Phase 1: I2C OLED "Hello World"            ← 验证 I2C 引脚、SSD1306 驱动
Phase 2: UART 雷达数据捕获                 ← 验证 UART 引脚、波特率、帧解析
Phase 3: 防偷窥状态机 + OLED 联动          ← 核心逻辑集成
Phase 4: USB CDC 命令交互                  ← PC 通信
Phase 5: PAJ7620 手势集成                  ← 可选扩展
Phase 6: 系统联调 + 压力测试               ← 稳定性和边界测试
```

### Phase 0 — 工程脚手架 + LED Blink

**目标**：验证 PlatformIO 环境、编译、烧录、USB CDC 通信

**测试方法**：
```cpp
// src/main.cpp — Phase 0
#include <Arduino.h>

void setup() {
    Serial.begin(115200);   // USB CDC
    pinMode(LED_BUILTIN, OUTPUT);  // GPIO48 (多数 S3 开发板)
}

void loop() {
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    Serial.printf("Blink! t=%lu\n", millis());
    delay(1000);
}
```

**验证标准**：
- ✅ 编译无错误
- ✅ 烧录成功
- ✅ LED 以 1Hz 闪烁
- ✅ USB CDC 串口正确输出 `Blink! t=...`

### Phase 1 — I2C OLED "Hello World"

**目标**：验证 I2C 引脚映射、SSD1306 驱动、U8g2 库

**测试方法**：
```cpp
// 仅初始化 OLED，显示 "Hello PeepPrevention"
// 关闭所有其他外设
```

**验证标准**：
- ✅ OLED 显示文字
- ✅ 中文显示正常
- ✅ U8g2 字体编译正确

### Phase 2 — UART 雷达数据捕获

**目标**：验证 UART 引脚、256000 波特率、帧解析状态机

**测试方法**：
```cpp
// 雷达数据 → 解析 → OLED 显示距离 + 能量
// 关闭状态机逻辑，仅做数据管道
```

**验证标准**：
- ✅ UART 无丢字节（连续 1000 帧校验和正确率 > 99.9%）
- ✅ 帧解析正确提取 `target_state`、`moving_dist`、`static_dist`
- ✅ 粘包场景正确处理
- ✅ OLED 实时显示雷达数据

**硬件辅助**：在雷达前方移动物体，观察距离数值变化

### Phase 3 — 防偷窥状态机 + OLED 联动

**目标**：核心业务逻辑验证

**测试方法**：
- 使用 Phase 2 的雷达数据驱动状态机
- OLED 根据状态切换显示内容
- 手动在雷达前模拟接近/远离/停留

**验证标准**：
- ✅ NORMAL → HUMAN_DETECTED → APPROACHING 距离阈值正确
- ✅ APPROACHING → SUSPECTED_PEEPING 超时触发正确
- ✅ SUSPECTED_PEEPING → PRIVACY_PROTECT 正确
- ✅ 离开后回到 NORMAL 超时正确
- ✅ OLED 显示随状态变化

### Phase 4 — USB CDC 命令交互

**目标**：PC → ESP32 命令控制

**测试方法**：
- 使用串口助手发送 `$STATE`、`$RADAR`、`$RESET`
- 观察响应和 OLED 变化

**验证标准**：
- ✅ 所有命令正确响应
- ✅ 异常命令返回 `> ERROR`
- ✅ 1Hz 数据推送不丢帧

### Phase 5 — PAJ7620 手势集成（可选）

**目标**：手势传感器驱动验证

**测试方法**：
- 启用 `ENABLE_GESTURE_SENSOR 1`
- 在传感器前做手势，观察串口输出和 OLED 图标

**验证标准**：
- ✅ 六种手势可识别
- ✅ 中断引脚电平正确
- ✅ OLED 显示手势图标

### Phase 6 — 系统联调 + 压力测试

**目标**：全功能运行 72 小时

| 测试项 | 方法 | 标准 |
|--------|------|------|
| 连续运行 | 72 小时不间断通电 | 无死机、无看门狗复位 |
| 频繁进出 | 每分钟快速进出检测区 | 状态机无卡死 |
| 边界距离 | 正好在 80cm/150cm 附近移动 | 无状态抖动（迟滞处理）|
| USB CDC 持续数据 | 1Hz 数据推送 72h | 无丢帧 |
| OLED 老化 | 连续显示同一画面 72h | 无烧屏残留 |
| 异常帧注入 | 串口助手发送乱码数据 | 帧解析器自动恢复 |

---

## 10. PlatformIO 工程配置建议

### 10.1 platformio.ini（完整版）

```ini
[platformio]
default_envs = esp32-s3-dev

; ======== 公共配置 ========
[common]
board_build.mcu = esp32s3
board_build.f_cpu = 240000000L
board_build.flash_mode = qio
board_build.f_flash = 80000000L

; ======== 开发环境（USB CDC + 调试输出） ========
[env:esp32-s3-dev]
platform = espressif32
board = esp32-s3-devkitc-1
framework = arduino
board_upload.max_upload_size = 8388608
monitor_speed = 115200
monitor_filters = esp32_exception_decoder, time

; === USB CDC 配置 ===
board_build.arduino.usb_cdc = true
board_build.arduino.usb_serial = true

; === 构建标志 ===
build_flags =
    ; ---- USB CDC ----
    -DARDUINO_USB_CDC_ON_BOOT=1
    -DARDUINO_USB_MODE=1
    -DARDUINO_RUNNING_CORE=1
    -DUSB_VID=0x303A
    -DUSB_PID=0x1001
    -DUSB_MANUFACTURER="SmartOffice"
    -DUSB_PRODUCT="PeepPrevention"

    ; ---- U8g2 字体 ----
    -DU8G2_USE_LARGEST_FONT
    -DU8G2_WITH_UTF8

    ; ---- FreeRTOS 配置 ----
    -DCONFIG_FREERTOS_HZ=1000

; === 库依赖 ===
lib_deps =
    ; OLED 显示驱动
    olikraus/U8g2@^2.35.4

    ; PAJ7620U2（预留，取消注释以启用）
    ; jarkko-hautakorpi/PAJ7620@^1.0.0

; === 编译优化 ===
build_unflags = -Os
board_build.optimize = -O2

; ======== 调试环境（额外串口日志） ========
[env:esp32-s3-debug]
extends = env:esp32-s3-dev
build_flags =
    ${env:esp32-s3-dev.build_flags}
    -DDEBUG_ENABLE
    -DCORE_DEBUG_LEVEL=5

; ======== 发布环境（最小体积 + 禁用调试） ========
[env:esp32-s3-release]
extends = env:esp32-s3-dev
build_flags =
    ${env:esp32-s3-dev.build_flags}
    -DNDEBUG
    -DCORE_DEBUG_LEVEL=0
board_build.optimize = -Os
```

### 10.2 工程目录结构

```
firmware/
├── platformio.ini              # PlatformIO 配置
├── include/
│   ├── config.h                # 引脚定义 + 编译配置
│   ├── radar_parser.h          # LD2410B 帧解析器
│   ├── peep_state_machine.h    # 防偷窥状态机
│   ├── oled_driver.h           # OLED 显示驱动
│   ├── paj7620_driver.h        # PAJ7620U2 接口预留
│   ├── cdc_handler.h           # USB CDC 协议
│   └── version.h               # 固件版本号
├── src/
│   ├── main.cpp                # 主入口 (setup + loop)
│   ├── radar_parser.cpp        # UART DMA + 帧解析实现
│   ├── peep_state_machine.cpp  # 状态机逻辑实现
│   ├── oled_driver.cpp         # SSD1306 显示实现
│   ├── paj7620_driver.cpp      # (留空/条件编译)
│   └── cdc_handler.cpp         # CDC 命令处理
├── lib/
│   └── README.md               # 自定义库目录说明
├── test/
│   ├── test_radar_parser.cpp   # 单元测试：帧解析
│   ├── test_state_machine.cpp  # 单元测试：状态机
│   └── test_checksum.cpp       # 单元测试：校验算法
└── README.md                   # 固件编译/烧录说明
```

### 10.3 关键配置说明

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `board` | `esp32-s3-devkitc-1` | 通用 S3 开发板，如果使用自研 PCB 需自定义 `boards/` |
| `board_build.f_cpu` | `240000000L` | S3 最大主频 240MHz |
| `board_build.f_flash` | `80000000L` | QIO 80MHz 闪存 |
| `monitor_speed` | `115200` | USB CDC 的 Serial 波特率（虚拟串口，实际任意）|
| `lib_deps` | `olikraus/U8g2` | 推荐使用 U8g2 库，支持中文 |
| `build_unflags` | `-Os` | 释放 -Os 默认，改用 -O2 优化性能 |
| `board_upload.max_upload_size` | `8388608` | N8R2 = 8MB Flash |

### 10.4 烧录说明

```bash
# 开发环境（默认）
pio run -e esp32-s3-dev -t upload

# 调试环境（含详细日志输出）
pio run -e esp32-s3-debug -t upload

# 发布环境（最小体积）
pio run -e esp32-s3-release -t upload

# 串口监视器
pio device monitor -e esp32-s3-dev

# 仅编译
pio run -e esp32-s3-dev

# 运行单元测试（主机端，需原生环境）
pio test -e native
```

### 10.5 自定义 S3 开发板（自研 PCB）

如果项目使用自研 PCB 而非标准开发板，需在 `boards/` 目录下创建自定义板定义：

```json
// boards/smartoffice_peep_s3.json
{
  "build": {
    "core": "esp32",
    "mcu": "esp32s3",
    "variant": "esp32s3",
    "arduino": {
      "pid": "0x1001",
      "vid": "0x303A",
      "board_name": "SmartOffice PeepPrevention S3"
    }
  },
  "upload": {
    "maximum_ram_size": 524288,
    "maximum_size": 8388608,
    "require_upload_port": true,
    "speed": 921600
  },
  "name": "SmartOffice PeepPrevention ESP32-S3"
}
```

---

## 附录

### A. 项目文件索引

| 文件 | 说明 |
|------|------|
| `firmware/include/config.h` | 引脚宏定义（所有 TODO 集中在此） |
| `firmware/platformio.ini` | PlatformIO 编译配置 |
| `firmware/src/main.cpp` | 主入口 |
| `firmware/src/radar_parser.cpp` | LD2410B UART 驱动 + 帧解析 |
| `firmware/src/peep_state_machine.cpp` | 防偷窥状态机 |
| `firmware/src/oled_driver.cpp` | SSD1306 OLED 显示驱动 |
| `firmware/src/paj7620_driver.cpp` | 手势传感器驱动（预留） |
| `firmware/src/cdc_handler.cpp` | USB CDC 通信协议 |

### B. 参考文档

- LD2410B 串口协议手册 V1.0
- SSD1306 数据手册
- PAJ7620U2 数据手册
- ESP32-S3-WROOM-1-N8R2 产品规格书
- ESP32-S3 技术参考手册（章节：UART、I2C、USB Serial/JTAG）
- U8g2 字体参考：https://github.com/olikraus/u8g2/wiki/fntlistall

### C. 固件版本号规范

```c
// version.h
#define FIRMWARE_VERSION_MAJOR 0
#define FIRMWARE_VERSION_MINOR 1
#define FIRMWARE_VERSION_PATCH 0
#define FIRMWARE_VERSION_STR   "0.1.0"
```
