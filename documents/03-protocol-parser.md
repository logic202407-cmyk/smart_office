# LD2410B 串口协议解析方案

> 文档版本：v1.0  
> 对应设备：LD2410B 24G 人体存在毫米波雷达模组  
> 适用范围：SmartOffice_PeepPrevention 项目

---

## 目录

1. [UART 通信参数](#1-uart-通信参数)
2. [帧结构详细分析](#2-帧结构详细分析)
3. [状态机 Parser 设计](#3-状态机-parser-设计)
4. [目标状态字段解码表](#4-目标状态字段解码表)
5. [运动/静止距离解析示例](#5-运动静止距离解析示例)
6. [能量值处理](#6-能量值处理)
7. [工程模式数据解析](#7-工程模式数据解析)
8. [常用配置命令封装 API 设计](#8-常用配置命令封装-api-设计)
9. [底噪检测命令和状态查询](#9-底噪检测命令和状态查询)
10. [波特率查询/设置](#10-波特率查询设置)
11. [固件版本读取](#11-固件版本读取)
12. [测试用例设计](#12-测试用例设计)

---

## 1. UART 通信参数

| 参数 | 值 |
|------|-----|
| 波特率 | 256000 bps |
| 数据位 | 8 bit |
| 校验位 | None |
| 停止位 | 1 bit |
| 字节序 | **Little-endian** (小端序) |
| 流控 | None |

> **注意**：LD2410B 默认波特率为 256000。模块支持通过配置命令切换为其他波特率（见 [第10章](#10-波特率查询设置)）。

---

## 2. 帧结构详细分析

LD2410B 协议包含两大类帧：**配置命令帧** 和 **上报数据帧**。两种帧的帧头、帧尾、校验机制完全不同，需要分别处理。

### 2.1 配置命令帧（Command Frame）

配置命令帧用于主机与模块之间的命令交互，采用 **请求-应答** 模式。

#### 2.1.1 命令发送帧

```
┌─────────┬──────────────┬──────────┬──────────┬─────────┐
│ 帧头     │ 数据长度      │ 命令字   │ 命令参数  │ 帧尾     │
│ 4 Byte   │ 2 Byte (LE)  │ 2 Byte   │ N Byte   │ 4 Byte   │
├─────────┼──────────────┼──────────┼──────────┼─────────┤
│ FC FB   │ Length        │ Cmd      │ Value    │ 04 03   │
│ FA FD   │               │          │          │ 02 01   │
└─────────┴──────────────┴──────────┴──────────┴─────────┘
```

**字段说明**：

| 偏移 | 大小 | 名称 | 说明 |
|------|------|------|------|
| [0-3] | 4 B | 帧头 | 固定 `FC FB FA FD`（注意：FE → FD 修正，实际为 FCFBFAFD） |
| [4-5] | 2 B | Length | 数据长度（小端序）= 后续所有字节数（从 Cmd 到帧尾之前）通常 = 4 (Cmd) + N (Value) |
| [6-7] | 2 B | Cmd | 命令字（小端序），详见命令清单 |
| [8+N] | N B | Value | 命令参数（可为空） |
| [末尾-3:末尾] | 4 B | 帧尾 | 固定 `04 03 02 01` |

**示例**：读取固件版本

```
FC FB FA FD  04 00  A0 00  04 03 02 01
│ 帧头      │长度│命令字│ 帧尾       │
            │4   │A000 │
```

#### 2.1.2 命令应答帧

```
┌─────────┬──────────────┬──────────┬──────────────┬─────────┐
│ 帧头     │ 数据长度      │ 命令字   │ 返回值        │ 帧尾     │
│ 4 Byte   │ 2 Byte (LE)  │ 2 Byte   │ N Byte       │ 4 Byte   │
├─────────┼──────────────┼──────────┼──────────────┼─────────┤
│ FC FB   │ Length        │ Cmd+0x0100│ ReturnValue  │ 04 03   │
│ FA FD   │               │          │              │ 02 01   │
└─────────┴──────────────┴──────────┴──────────────┴─────────┘
```

**关键区别**：
- 应答帧的 `Cmd = 请求命令字 | 0x0100`（高位加 1）
- 帧尾同样是 `04 03 02 01`
- Length 包含从命令字到帧尾前的所有字节

**应答码（ReturnValue 首字节）**：

| 值 | 含义 |
|----|------|
| 0x00 | 成功 |
| 0x01 | 命令错误 / 失败 |
| 其他 | 视具体命令而定 |

### 2.2 上报数据帧（Report Frame）

上报数据帧是模块在**非配置模式**下主动上报检测结果的帧。

```
┌─────────┬──────────────┬──────────┬──────┬──────────────┬──────┬──────────┬─────────┐
│ 帧头     │ 数据长度      │ 数据类型 │ 固定 │ 目标数据      │ 固定 │ 校验和   │ 帧尾     │
│ 4 Byte   │ 2 Byte (LE)  │ 1 Byte   │ 1 B  │ N Byte       │ 1 B  │ 1 Byte   │ 4 Byte   │
├─────────┼──────────────┼──────────┼──────┼──────────────┼──────┼──────────┼─────────┤
│ F4 F3   │ Length        │ DataType │ AA   │ TargetData   │ 55   │ Check    │ F8 F7   │
│ F2 F1   │               │          │      │              │      │          │ F6 F5   │
└─────────┴──────────────┴──────────┴──────┴──────────────┴──────┴──────────┴─────────┘
```

**字段说明**：

| 偏移 | 大小 | 名称 | 说明 |
|------|------|------|------|
| [0-3] | 4 B | 帧头 | 固定 `F4 F3 F2 F1` |
| [4-5] | 2 B | Length | 数据长度（小端序）= 从 DataType 到帧尾前的所有字节数 |
| [6] | 1 B | DataType | 数据类型 `0x01`=工程模式, `0x02`=基本信息 |
| [7] | 1 B | 固定 | 固定 `AA` |
| [8..] | N B | TargetData | 目标数据（根据 DataType 不同，结构不同） |
| [末尾-5] | 1 B | 固定 | 固定 `55` |
| [末尾-4] | 1 B | Check | 校验和（从帧头开始到 `55` 之前的累加和取低 8 位） |
| [末尾-3:末尾] | 4 B | 帧尾 | 固定 `F8 F7 F6 F5` |

---

## 3. 状态机 Parser 设计

### 3.1 总体架构

采用 **分层状态机** 设计，上层区分配置帧/上报帧类型，下层按字节级状态流转。

```
                  ┌─────────────────────┐
                  │   Serial Byte Stream │
                  └─────────┬───────────┘
                            │
                  ┌─────────▼───────────┐
                  │   Byte-Level FSM    │
                  │  (帧头/帧尾/逃逸)    │
                  └─────────┬───────────┘
                            │
                  ┌─────────▼───────────┐
                  │  Frame Type Switch   │
                  │  (FC FB FA FD ?      │
                  │   F4 F3 F2 F1 ?)     │
                  └──┬─────────────┬─────┘
                     │             │
            ┌────────▼───┐  ┌─────▼────────┐
            │ Cmd Frame  │  │ Report Frame │
            │ Parser     │  │ Parser       │
            └────────────┘  └──────────────┘
```

### 3.2 字节级状态机定义

```
enum ParserState {
    WAIT_HEAD_0,      // 等待帧头第1字节
    WAIT_HEAD_1,      // 等待帧头第2字节
    WAIT_HEAD_2,      // 等待帧头第3字节
    WAIT_HEAD_3,      // 等待帧头第4字节
    WAIT_LENGTH_L,    // 等待 Length 低字节
    WAIT_LENGTH_H,    // 等待 Length 高字节
    WAIT_PAYLOAD,     // 等待负载数据
    WAIT_TAIL_0,      // 等待帧尾第1字节 (配置帧: 04 / 上报帧: 55)
    WAIT_TAIL_1,      // 等待帧尾第2字节 (配置帧: 03 / 上报帧: F8)
    WAIT_TAIL_2,      // 等待帧尾第3字节 (配置帧: 02 / 上报帧: F7)
    WAIT_TAIL_3,      // 等待帧尾第4字节 (配置帧: 01 / 上报帧: F6)
    WAIT_TAIL_4,      // 仅上报帧: 等待 F5
    FRAME_COMPLETE,   // 帧完成
};
```

### 3.3 状态转移图

```
WAIT_HEAD_0 ──(0xFC)──→ WAIT_HEAD_1    (配置帧检测)
WAIT_HEAD_0 ──(0xF4)──→ WAIT_HEAD_1    (上报帧检测)
WAIT_HEAD_0 ──(other)──→ WAIT_HEAD_0   (丢弃，继续等待)

WAIT_HEAD_1 ──(0xFB)──→ WAIT_HEAD_2    (配置帧路径)
WAIT_HEAD_1 ──(0xF3)──→ WAIT_HEAD_2    (上报帧路径)
WAIT_HEAD_1 ──(other)──→ WAIT_HEAD_0   (复位)

WAIT_HEAD_2 ──(0xFA)──→ WAIT_HEAD_3    (配置帧路径)
WAIT_HEAD_2 ──(0xF2)──→ WAIT_HEAD_3    (上报帧路径)
WAIT_HEAD_2 ──(other)──→ WAIT_HEAD_0   (复位)

WAIT_HEAD_3 ──(0xFD)──→ WAIT_LENGTH_L  (配置帧路径, 记录 frame_type=CMD)
WAIT_HEAD_3 ──(0xF1)──→ WAIT_LENGTH_L  (上报帧路径, 记录 frame_type=REPORT)
WAIT_HEAD_3 ──(other)──→ WAIT_HEAD_0   (复位)

WAIT_LENGTH_L → WAIT_LENGTH_H          (保存 length_l)
WAIT_LENGTH_H → WAIT_PAYLOAD           (计算 total_length, 保存 length_h)
WAIT_PAYLOAD  → WAIT_TAIL_0            (收满 payload 字节)
WAIT_TAIL_0..3/4 → (匹配帧尾) → FRAME_COMPLETE
                  → (不匹配)   → WAIT_HEAD_0 (丢弃)
FRAME_COMPLETE → (回调处理) → WAIT_HEAD_0
```

### 3.4 粘包/半包/错帧处理策略

#### 3.4.1 粘包处理

连续快速上报时，多个帧可能连在一起。策略：

```
┌──────────┐┌──────────┐┌──────────┐
│  Frame 1 ││  Frame 2 ││  Frame 3 │
└──────────┘└──────────┘└──────────┘
```

- Parser 在 `FRAME_COMPLETE` 状态分发完成后，**不丢弃当前缓冲区**的剩余数据
- 状态机**自动复位到** `WAIT_HEAD_0`，继续处理后续字节
- 通过设置单次最大处理帧数（如 `MAX_FRAMES_PER_BATCH=16`）防止饥饿

#### 3.4.2 半包处理

数据不完整（如串口 buffer 只收到 3 个字节）：

```
收到: F4 F3 F2
期望: F4 F3 F2 F1 08 00 02 AA ...
```

- 状态机停留在当前等待状态，**不丢弃已接收的数据**
- 保存上下文（`frame_type`、已收字节数、期望总长度等）
- 等待下一批数据到达后继续消费

#### 3.4.3 错帧处理

当中间字节错误导致状态偏离：

```
正常: FC FB FA FD 04 00 A0 00 04 03 02 01
错帧: FC FB FA FD 04 00 A0 00 FF 03 02 01  ← 帧尾不符
```

- 在帧尾验证阶段发现不匹配时，**丢弃整个帧**，返回 `WAIT_HEAD_0`
- 为防止漏检，在 `WAIT_PAYLOAD` 阶段可设置 **超长保护**：如果实际收字节数超过 `MAX_FRAME_LENGTH`（建议 512 字节），强制复位
- 帧头误触发（如数据中恰好出现 `FC FB FA FD`）：通过帧尾验证 + 校验和（上报帧）双重校验保证准确性

#### 3.4.4 超时处理

- 设置 **帧间超时定时器**（建议 100ms，根据 256000bps 下最大帧长约 200μs * 10 = 2ms，留足余量）
- 如果在超时时间内未完成当前帧，认为发生了半包丢失，**复位状态机**
- 记录 `error_count` 统计丢帧率

### 3.5 Parser 核心数据结构

```c
typedef struct {
    uint8_t     frame_type;         // 0=CMD, 1=REPORT
    uint8_t     state;              // 当前状态
    uint8_t     buffer[512];        // 帧缓冲区
    uint16_t    buffer_index;       // 已收字节数
    uint16_t    expected_length;    // 期望总长度
    uint8_t     report_datatype;    // 上报数据类型 (仅 REPORT 帧)
    uint16_t    error_count;        // 错误计数
    uint8_t     current_head[4];    // 当前帧头
} ld2410b_parser_t;
```

### 3.6 Parser 处理流程伪代码

```c
void ld2410b_feed_byte(ld2410b_parser_t *parser, uint8_t byte) {
    switch (parser->state) {
    case WAIT_HEAD_0:
        if (byte == 0xFC || byte == 0xF4) {
            parser->buffer[0] = byte;
            parser->buffer_index = 1;
            parser->state = WAIT_HEAD_1;
        }
        // else: 丢弃
        break;

    case WAIT_HEAD_1:
        if ((parser->buffer[0] == 0xFC && byte == 0xFB) ||
            (parser->buffer[0] == 0xF4 && byte == 0xF3)) {
            parser->buffer[1] = byte;
            parser->buffer_index = 2;
            parser->state = WAIT_HEAD_2;
        } else {
            parser->state = WAIT_HEAD_0; // 复位
        }
        break;

    case WAIT_HEAD_2:
        if ((parser->buffer[0] == 0xFC && byte == 0xFA) ||
            (parser->buffer[0] == 0xF4 && byte == 0xF2)) {
            parser->buffer[2] = byte;
            parser->buffer_index = 3;
            parser->state = WAIT_HEAD_3;
        } else {
            parser->state = WAIT_HEAD_0;
        }
        break;

    case WAIT_HEAD_3:
        if ((parser->buffer[0] == 0xFC && byte == 0xFD) ||
            (parser->buffer[0] == 0xF4 && byte == 0xF1)) {
            parser->buffer[3] = byte;
            parser->buffer_index = 4;
            parser->frame_type = (parser->buffer[0] == 0xFC) ? CMD_FRAME : REPORT_FRAME;
            parser->state = WAIT_LENGTH_L;
        } else {
            parser->state = WAIT_HEAD_0;
        }
        break;

    case WAIT_LENGTH_L:
        parser->buffer[parser->buffer_index++] = byte;
        parser->state = WAIT_LENGTH_H;
        break;

    case WAIT_LENGTH_H:
        parser->buffer[parser->buffer_index++] = byte;
        parser->expected_length = parser->buffer[4] | (parser->buffer[5] << 8);
        // 长度保护
        if (parser->expected_length > 500) {
            parser->error_count++;
            parser->state = WAIT_HEAD_0;
            break;
        }
        if (parser->expected_length == 0) {
            // 无 payload，直接校验帧尾
            parser->state = WAIT_TAIL_0;
        } else {
            parser->state = WAIT_PAYLOAD;
        }
        break;

    case WAIT_PAYLOAD:
        parser->buffer[parser->buffer_index++] = byte;
        uint16_t payload_len = parser->buffer_index - 6; // 已收到6字节: 4帧头+2长度
        if (payload_len >= parser->expected_length) {
            parser->state = WAIT_TAIL_0;
        }
        break;

    case WAIT_TAIL_0:
        // 配置帧: 04, 上报帧: 55 (or F8 depending on interpretation)
        if (parser->frame_type == CMD_FRAME) {
            if (byte == 0x04) { parser->state = WAIT_TAIL_1; }
            else { /* 复位 */ parser->state = WAIT_HEAD_0; }
        } else {
            if (byte == 0x55) { parser->state = WAIT_TAIL_1; }
            else { parser->state = WAIT_HEAD_0; }
        }
        break;

    // ... 类似处理后续帧尾字节

    case FRAME_COMPLETE:
        ld2410b_dispatch(parser);   // 分发帧到上层回调
        parser->state = WAIT_HEAD_0; // 自动复位
        break;
    }
}
```

---

## 4. 目标状态字段解码表

### 4.1 状态枚举

上报数据帧 `TargetData` 区域中，偏移 8（相对帧头）的 **target_state** 字段：

| 字段值 | 枚举名 | 含义 | 图示 |
|--------|--------|------|------|
| `0x00` | `TARGET_NONE` | 无目标 | 空间无人 |
| `0x01` | `TARGET_MOVING` | 运动目标 | 有人移动 |
| `0x02` | `TARGET_STATIONARY` | 静止目标 | 有人静坐/睡眠 |
| `0x03` | `TARGET_BOTH` | 运动 + 静止 | 有人移动+静止共存 |
| `0x04` | `TARGET_NOISE_CALIB` | 底噪检测中 | 模块正在校准 |

### 4.2 状态关联的业务逻辑

```
状态解码映射 (C 宏/内联函数)：

#define TARGET_STATE_NONE       0x00
#define TARGET_STATE_MOVING     0x01
#define TARGET_STATE_STATIC     0x02
#define TARGET_STATE_BOTH       0x03
#define TARGET_STATE_NOISE      0x04

static inline const char* target_state_str(uint8_t state) {
    switch (state) {
        case 0x00: return "NO_TARGET";
        case 0x01: return "MOVING";
        case 0x02: return "STATIONARY";
        case 0x03: return "MOVING+STATIONARY";
        case 0x04: return "NOISE_CALIB";
        default:   return "UNKNOWN";
    }
}
```

---

## 5. 运动/静止距离解析示例

### 5.1 字段位置（基本信息模式，DataType=0x02）

```
帧头:      F4 F3 F2 F1       [0-3]
长度:      08 00             [4-5]  → Length=8
数据类型:  02                [6]    → 基本信息
固定:      AA                [7]
┌─ TargetData ───────────────────────────────────┐
│ [8]   target_state      (1B)                   │
│ [9-10] moving_distance_cm (2B LE)              │
│ [11]  moving_energy      (1B, 0~100)           │
│ [12-13] static_distance_cm  (2B LE)            │
│ [14]  static_energy      (1B, 0~100)           │
│ [15-16] detect_distance_cm (2B LE)             │
└────────────────────────────────────────────────┘
55 Check F8 F7 F6 F5       [17..22]
```

### 5.2 解析示例

假设收到以下原始字节：

```
F4 F3 F2 F1  08 00  02  AA  03  34 00  45  2C 01  32  E8 03  55  XX  F8 F7 F6 F5
```

逐字段解析：

| 字段 | 原始字节 | 解析值 | 说明 |
|------|---------|--------|------|
| 帧头 | `F4 F3 F2 F1` | — | 上报帧标识 |
| Length | `08 00` | 8 | 小端序 `0x0008` |
| DataType | `02` | 基本信息模式 | — |
| 固定 | `AA` | — | — |
| target_state | `03` | **运动+静止** | 有人处于移动+静止状态 |
| moving_distance | `34 00` | **52 cm** | 小端 `0x0034` = 52 |
| moving_energy | `45` | **69** | 运动能量值 (0-100) |
| static_distance | `2C 01` | **300 cm** | 小端 `0x012C` = 300 |
| static_energy | `32` | **50** | 静止能量值 (0-100) |
| detect_distance | `E8 03` | **1000 cm** | 小端 `0x03E8` = 1000 (10m 最大探测距离) |
| 固定 | `55` | — | — |
| Check | `XX` | 校验和 | 见下方计算 |
| 帧尾 | `F8 F7 F6 F5` | — | — |

**距离解析伪代码**：

```c
uint16_t moving_dist = parser->buffer[9] | (parser->buffer[10] << 8);   // LE
uint16_t static_dist = parser->buffer[12] | (parser->buffer[13] << 8);
uint16_t detect_dist = parser->buffer[15] | (parser->buffer[16] << 8);

// 单位: 厘米 (cm)
printf("运动距离: %u cm\n", moving_dist);
printf("静止距离: %u cm\n", static_dist);
printf("检测距离: %u cm\n", detect_dist);

// 距离有效范围: 0 ~ 1000 cm (10m)
```

### 5.3 特殊距离值说明

| 值 | 含义 |
|----|------|
| `0` | 无对应目标（如只有运动目标时，静止距离=0） |
| `1~1000` | 以 cm 为单位的实际距离 |
| `> 1000` | 保留值，视为无效 |

---

## 6. 能量值处理

### 6.1 能量字段说明

能量值是 LD2410B 检测到目标回波强度的量化指标，范围 **0~100**。

| 字段 | 位置 | 大小 | 范围 | 含义 |
|------|------|------|------|------|
| moving_energy | [11] | 1 B | 0-100 | 运动目标能量强度 |
| static_energy | [14] | 1 B | 0-100 | 静止目标能量强度 |

### 6.2 能量值物理意义

| 能量范围 | 参考解释 |
|----------|---------|
| 0 | 无检测目标或无有效回波 |
| 1-30 | 弱信号（微小扰动、远距离目标） |
| 31-60 | 中等信号（正常人体存在） |
| 61-80 | 强信号（近距离较大目标） |
| 81-100 | 极强信号（紧贴探头或干扰） |

> **注意**：能量值是相对值，受安装角度、环境反射、灵敏度设置等因素影响。**不建议**用绝对值做精确判断，建议结合变化趋势和距离信息综合评估。

### 6.3 能量值滤波建议

```c
// 一阶低通滤波 (IIR)
#define ENERGY_ALPHA 0.3f   // 滤波系数, 越小越平滑

uint8_t energy_filter(uint8_t raw_value, float *filtered) {
    *filtered = (*filtered) * (1.0f - ENERGY_ALPHA) + raw_value * ENERGY_ALPHA;
    return (uint8_t)(*filtered + 0.5f);
}

// 滑动窗口平均 (对能量抖动抑制更好)
#define WINDOW_SIZE 5
uint8_t energy_sma(uint8_t raw_value, uint8_t *window, uint8_t *index, uint32_t *sum) {
    *sum -= window[*index];
    window[*index] = raw_value;
    *sum += raw_value;
    *index = (*index + 1) % WINDOW_SIZE;
    return (uint8_t)(*sum / WINDOW_SIZE);
}
```

### 6.4 能量阈值配置

通过配置命令 `0x0064` 设置各距离门的灵敏度阈值（实际为能量阈值）：

```
命令: FC FB FA FD  08 00  64 00  [门号] [阈值]  04 03 02 01
应答: FC FB FA FD  06 00  64 01  [ret]  XXXX    04 03 02 01

参数:
- 门号 (1B): 0-8 (对应 0.75m 步进的距离门)
- 阈值 (1B): 0-100 (能量阈值)
```

---

## 7. 工程模式数据解析

### 7.1 工程模式启用

工程模式提供更详细的雷达回波信息，包含每个距离门的能量值和移动/静止状态。

**开启命令**：

```
FC FB FA FD  05 00  62 00  00  04 03 02 01
```

**关闭命令**：

```
FC FB FA FD  05 00  63 00  00  04 03 02 01
```

### 7.2 工程模式帧结构（DataType=0x01）

```
F4 F3 F2 F1  Length  01  AA  [EngineerData]  55  Check  F8 F7 F6 F5
```

EngineerData 结构（共约 14 字节 + 9×4=36 字节门数据）：

| 偏移 | 大小 | 字段 | 说明 |
|------|------|------|------|
| [8] | 1 B | target_state | 目标状态 (同基本信息) |
| [9-10] | 2 B | moving_distance_cm | 运动距离 |
| [11] | 1 B | moving_energy | 运动能量 |
| [12-13] | 2 B | static_distance_cm | 静止距离 |
| [14] | 1 B | static_energy | 静止能量 |
| [15-16] | 2 B | detect_distance_cm | 检测距离 |
| [17] | 1 B | max_gate | 最大距离门编号 (通常 8) |
| [18] | 1 B | current_gate | 当前门号 (循环上报用) |
| [19-20] | 2 B | light_sensor | 预留/光照 (部分固件) |
| [21..] | N B | gate_data | 每个门 4 字节, 结构见下 |

**每个距离门数据（4 字节）**：

| 偏移(门内) | 大小 | 字段 |
|------------|------|------|
| [0] | 1 B | moving_energy (该门) |
| [1] | 1 B | static_energy (该门) |
| [2] | 1 B | moving_threshold (该门运动阈值) |
| [3] | 1 B | static_threshold (该门静止阈值) |

### 7.3 工程模式解析示例

```
帧头:    F4 F3 F2 F1
长度:    30 00          → 48 字节 (0x0030)
类型:    01             → 工程模式
固定:    AA

基本信息段:
  target_state:      03          → 运动+静止
  moving_distance:   1E 00       → 30 cm
  moving_energy:     3C          → 60
  static_distance:   64 00       → 100 cm
  static_energy:     28          → 40
  detect_distance:   D0 07       → 2000 cm (20m, 工程模式延伸)
  max_gate:          08          → 9个门 (0-8)
  current_gate:      05          → 当前为第5门数据

距离门数据 (9个门 × 4B = 36B):
  Gate 0:  00 00 1E 1E   (mov=0, stc=0, mov_th=30, stc_th=30)
  Gate 1:  00 00 1E 1E
  Gate 2:  14 0A 1E 1E   (mov=20, stc=10)
  Gate 3:  28 1E 1E 1E   (mov=40, stc=30)
  Gate 4:  3C 28 1E 1E   (mov=60, stc=40)
  Gate 5:  28 32 1E 1E   (mov=40, stc=50)
  Gate 6:  14 1E 1E 1E   (mov=20, stc=30)
  Gate 7:  00 14 1E 1E   (mov=0, stc=20)
  Gate 8:  00 00 1E 1E   (mov=0, stc=0)

55 Check F8 F7 F6 F5
```

### 7.4 工程模式应用场景

- **调试阶段**：观察各距离门的能量分布，优化安装位置
- **阈值调优**：根据各门能量基线设置合理的灵敏度阈值
- **干扰诊断**：排除空调/窗帘等环境干扰源
- **多目标分析**：识别多个距离同时存在目标的情况

---

## 8. 常用配置命令封装 API 设计

### 8.1 通用命令发送接口

```c
/**
 * @brief 发送配置命令
 * @param cmd     命令字 (2字节, LE)
 * @param value   命令参数缓冲区
 * @param val_len 参数长度 (字节)
 * @return true=发送成功, false=失败
 */
bool ld2410b_send_cmd(uint16_t cmd, const uint8_t *value, uint8_t val_len);

/**
 * @brief 等待配置命令应答
 * @param cmd         期待应答的命令字 (原始命令字, 函数内自动加 0x0100)
 * @param out_value   输出缓冲区
 * @param out_len     输出长度
 * @param timeout_ms  超时 (ms)
 * @return true=收到正确应答, false=超时或错误
 */
bool ld2410b_wait_response(uint16_t cmd, uint8_t *out_value, uint8_t *out_len, uint32_t timeout_ms);

/**
 * @brief 发送并等待应答 (同步封装)
 */
bool ld2410b_cmd_sync(uint16_t cmd, const uint8_t *tx_val, uint8_t tx_len,
                      uint8_t *rx_val, uint8_t *rx_len, uint32_t timeout_ms);
```

### 8.2 命令序列化接口

```c
/**
 * @brief 序列化配置命令到 buffer
 * @param buf    输出缓冲区
 * @param cmd    命令字
 * @param value  参数数据
 * @param len    参数长度
 * @return 序列化后的总字节数
 */
uint16_t ld2410b_serialize_cmd(uint8_t *buf, uint16_t cmd,
                                const uint8_t *value, uint8_t len) {
    uint16_t idx = 0;
    // 帧头
    buf[idx++] = 0xFC; buf[idx++] = 0xFB;
    buf[idx++] = 0xFA; buf[idx++] = 0xFD;
    // Length = 命令字(2) + 参数长度
    uint16_t data_len = 2 + len;
    buf[idx++] = data_len & 0xFF;
    buf[idx++] = (data_len >> 8) & 0xFF;
    // 命令字 (LE)
    buf[idx++] = cmd & 0xFF;
    buf[idx++] = (cmd >> 8) & 0xFF;
    // 参数
    if (len > 0 && value != NULL) {
        memcpy(&buf[idx], value, len);
        idx += len;
    }
    // 帧尾
    buf[idx++] = 0x04; buf[idx++] = 0x03;
    buf[idx++] = 0x02; buf[idx++] = 0x01;
    return idx;
}
```

### 8.3 命令封装函数

```c
// ========== 配置模式控制 ==========

/** 使能配置 (进入配置模式) */
bool ld2410b_enable_config(void) {
    return ld2410b_cmd_sync(0x00FF, NULL, 0, NULL, NULL, 1000);
}

/** 结束配置 (退出配置模式) */
bool ld2410b_disable_config(void) {
    return ld2410b_cmd_sync(0x00FE, NULL, 0, NULL, NULL, 1000);
}

// ========== 参数读写 ==========

/** 读取雷达参数 (灵敏度等) */
typedef struct {
    uint8_t max_gate;          // 最大距离门
    uint8_t moving_threshold[9]; // 各门运动阈值
    uint8_t static_threshold[9]; // 各门静止阈值
    // 扩展: 各门灵敏度等
} ld2410b_param_t;

bool ld2410b_read_params(ld2410b_param_t *params);

/** 设置指定门的灵敏度阈值 */
bool ld2410b_set_sensitivity(uint8_t gate, uint8_t moving_th, uint8_t static_th) {
    uint8_t value[3] = {gate, moving_th, static_th};
    return ld2410b_cmd_sync(0x0064, value, 3, NULL, NULL, 1000);
}

// ========== 工程模式 ==========

bool ld2410b_enable_engineer_mode(void) {
    uint8_t val = 0x00;
    return ld2410b_cmd_sync(0x0062, &val, 1, NULL, NULL, 1000);
}

bool ld2410b_disable_engineer_mode(void) {
    uint8_t val = 0x00;
    return ld2410b_cmd_sync(0x0063, &val, 1, NULL, NULL, 1000);
}

// ========== 底噪检测 ==========

bool ld2410b_start_noise_calib(void) {
    uint8_t val = 0x00;
    return ld2410b_cmd_sync(0x000B, &val, 1, NULL, NULL, 5000); // 5s 超时
}

// ========== 波特率设置 ==========

typedef enum {
    BAUD_9600     = 0x00,
    BAUD_19200    = 0x01,
    BAUD_38400    = 0x02,
    BAUD_57600    = 0x03,
    BAUD_115200   = 0x04,
    BAUD_230400   = 0x05,
    BAUD_256000   = 0x06,  // 默认
    BAUD_460800   = 0x07,
    BAUD_921600   = 0x08,
} ld2410b_baud_t;

bool ld2410b_set_baudrate(ld2410b_baud_t baud);

// ========== 固件版本 ==========

typedef struct {
    uint8_t major;
    uint8_t minor;
    uint8_t patch;
    char     vendor[16];
} ld2410b_fw_version_t;

bool ld2410b_read_fw_version(ld2410b_fw_version_t *ver);

// ========== 复位/恢复 ==========

bool ld2410b_factory_reset(void);
bool ld2410b_reboot(void);
```

### 8.4 异步回调接口

上报数据帧通过异步回调分发，避免阻塞主循环：

```c
/** 上报数据回调类型 */
typedef void (*ld2410b_report_callback_t)(const ld2410b_report_t *report);

/** 配置应答回调类型 */
typedef void (*ld2410b_response_callback_t)(uint16_t cmd, uint8_t ret_code,
                                             const uint8_t *data, uint8_t len);

typedef struct {
    ld2410b_report_callback_t   on_report;
    ld2410b_response_callback_t on_response;
    void (*on_error)(uint16_t error_code);
} ld2410b_callbacks_t;

/** 注册回调 */
void ld2410b_set_callbacks(const ld2410b_callbacks_t *cbs);
```

---

## 9. 底噪检测命令和状态查询

### 9.1 开始底噪检测

**命令**：

```
FC FB FA FD  05 00  0B 00  00  04 03 02 01
```

**应答**：

```
FC FB FA FD  06 00  0B 01  [ret=0/1]  [status]  04 03 02 01
```

- `ret`：`0x00`=开始成功，`0x01`=失败
- `status`：当前底噪检测状态

> **注意**：底噪检测需要一定时间（约 3-5 秒），检测期间模块处于 `0x04 (NOISE_CALIB)` 状态，正常目标检测暂停。建议在系统初始化时执行，避免在运行时触发。

### 9.2 底噪检测状态查询

**命令**：

```
FC FB FA FD  04 00  1B 00  04 03 02 01
```

**应答**：

```
FC FB FA FD  08 00  1B 01  [ret]  [noise_status]  [reserved]  [reserved]  04 03 02 01
```

**noise_status 解码**：

| 值 | 含义 |
|----|------|
| `0x00` | 未开始底噪检测 |
| `0x01` | 底噪检测进行中 |
| `0x02` | 底噪检测完成 |
| `0xFF` | 底噪检测失败 |

### 9.3 底噪检测流程

```
┌────────────────┐
│ 上电初始化      │
└────────┬───────┘
         ▼
┌────────────────┐
│ 查询底噪状态    │──── 0x001B ────→
│ (0x1B 命令)    │←── [status=0x02?] ──→ 已完成则跳过
└────────┬───────┘
         ▼  (未完成/未开始)
┌────────────────┐
│ 开始底噪检测    │──── 0x000B ────→
│ (0x0B 命令)    │←── ACK
└────────┬───────┘
         ▼
┌────────────────┐
│ 轮询状态(100ms) │──── 0x001B ────→
│               │←── status=0x01 (进行中)
│               │←── status=0x02 (完成)
└────────┬───────┘
         ▼
┌────────────────┐
│ 正常检测模式    │
└────────────────┘
```

---

## 10. 波特率查询/设置

### 10.1 波特率编码表

| 编码 | 波特率 | 说明 |
|------|--------|------|
| `0x00` | 9600 | 低功耗/调试 |
| `0x01` | 19200 | — |
| `0x02` | 38400 | — |
| `0x03` | 57600 | — |
| `0x04` | 115200 | 常用 |
| `0x05` | 230400 | — |
| `0x06` | **256000** | **出厂默认** |
| `0x07` | 460800 | — |
| `0x08` | 921600 | 高速 |

### 10.2 读当前波特率

**命令** (0x00A1 with value=0x00):

```
FC FB FA FD  05 00  A1 00  00  04 03 02 01
```

**应答** (命令字 `0xA1`):

```
FC FB FA FD  06 00  A1 01  [ret]  [baud_code]  04 03 02 01
```

- `ret`：应答码
- `baud_code`：当前波特率编码（见上表）

### 10.3 设置波特率

**命令**:

```
FC FB FA FD  06 00  A1 00  [baud_code]  [保存标志]  04 03 02 01
```

- `baud_code`：目标波特率编码
- `保存标志`：
  - `0x00` = 临时切换（掉电恢复）
  - `0x01` = 写入 Flash（永久生效）

**示例**：永久设置为 115200

```
FC FB FA FD  06 00  A1 00  04  01  04 03 02 01
                ↑ cmd  ↑code ↑保存
```

> **关键注意事项**：
> 1. 设置波特率后，主机 UART 必须在 100ms 内切换到新波特率，否则通信中断
> 2. 应答帧仍以**旧波特率**发送
> 3. 如使用 `0x01` 保存标志，模块会写入 Flash，有写入寿命限制（约 10 万次）
> 4. 建议上层封装一个「切换波特率 + 等待应答 + 切换本地波特率 + 发送测试帧」的原子操作

### 10.4 安全切换流程

```c
bool ld2410b_set_baudrate_safe(ld2410b_baud_t baud) {
    uint8_t value[2] = {(uint8_t)baud, 0x01}; // 保存到 Flash
    // 1. 发送设置命令
    if (!ld2410b_send_cmd(0x00A1, value, 2)) return false;

    // 2. 等待应答 (仍在旧波特率)
    uint8_t resp[8];
    uint8_t resp_len;
    if (!ld2410b_wait_response(0x00A1, resp, &resp_len, 500)) return false;

    // 3. 切换主机 UART 到新波特率
    uart_set_baudrate(baud_rate_table[baud]);

    // 4. 发送测试命令确认 (如读取版本)
    //    如失败则回退旧波特率并报错
    osDelay(50);
    if (!ld2410b_read_fw_version_direct(&temp_ver)) {
        uart_set_baudrate(256000); // 回退
        return false;
    }
    return true;
}
```

---

## 11. 固件版本读取

### 11.1 读取命令

```
FC FB FA FD  04 00  A0 00  04 03 02 01
```

### 11.2 应答格式

```
FC FB FA FD  [len]  A0 01  [ret]  [ver_str...]  04 03 02 01
```

`ver_str` 为 ASCII 字符串，格式如：
- `LD2410B_V1.0.0_220906` 
- `V1.0.0.0` 
- `L24B1V100`

### 11.3 解析实现

```c
bool ld2410b_read_fw_version(ld2410b_fw_version_t *ver) {
    uint8_t resp[128];
    uint8_t resp_len = 0;

    if (!ld2410b_cmd_sync(0x00A0, NULL, 0, resp, &resp_len, 1000)) {
        return false;
    }

    // resp[0] = ret_code, resp[1..] = version string
    if (resp[0] != 0x00) return false;

    // 版本字符串在 resp[1..resp_len-1]
    const char *ver_str = (const char *)&resp[1];
    // 解析 "V1.2.3" 格式
    if (sscanf(ver_str, "V%d.%d.%d", &ver->major, &ver->minor, &ver->patch) >= 3) {
        return true;
    }
    // 备用解析逻辑: 逐字符提取数字
    return parse_version_fallback(ver_str, ver);
}
```

### 11.4 固件版本兼容性说明

| 版本特征 | 说明 |
|----------|------|
| V1.0.x | 基础版本，支持基本检测和配置 |
| V2.0.x | 引入工程模式优化 |
| 带 `_220906` 等后缀 | 编译日期，用于追溯 |

> 建议在初始化时读取固件版本并记录日志，以便后续问题定位。

---

## 12. 测试用例设计

### 12.1 测试框架定义

测试采用 BDD 风格，基于模拟串口数据流验证 Parser 行为。每个测试用例包含：

```c
typedef struct {
    const char *name;           // 测试名称
    const uint8_t *input;       // 模拟串口输入字节流
    uint16_t      input_len;    // 输入长度
    uint8_t       expected_frames;  // 期望解析出几帧
    uint16_t      expected_errors;  // 期望错误计数
    // 对每帧的期望校验
    struct {
        uint8_t   frame_type;   // CMD/REPORT
        uint16_t  cmd;          // 配置命令字 (CMD帧)
        uint8_t   state;        // 目标状态 (REPORT帧)
        uint16_t  moving_dist;  // 运动距离
        uint16_t  static_dist;  // 静止距离
    } expected[8];              // 最多 8 帧
} test_case_t;
```

### 12.2 正常帧测试

| 编号 | 名称 | 输入 | 预期 |
|------|------|------|------|
| TC01 | 基本信息上报帧 | 完整正确帧（无目标） | 解析出 1 帧, state=0x00 |
| TC02 | 基本信息上报帧（运动） | 完整正确帧（运动目标） | 1 帧, state=0x01, moving_dist=正确值 |
| TC03 | 基本信息上报帧（静止） | 完整正确帧（静止目标） | 1 帧, state=0x02, static_dist=正确值 |
| TC04 | 基本信息上报帧（复合） | 完整正确帧（运动+静止） | 1 帧, state=0x03, 两距离均有效 |
| TC05 | 配置帧 | 完整的读版本命令 | 1 帧 (CMD), cmd=0x00A0 |
| TC06 | 配置应答帧 | 完整的版本应答 | 1 帧 (CMD), cmd=0x00A1 |
| TC07 | 工程模式上报帧 | 完整工程模式帧 | 1 帧, DataType=0x01, 含 9 门数据 |

### 12.3 粘包测试

| 编号 | 名称 | 输入 | 预期 |
|------|------|------|------|
| TC08 | 两帧粘包 | 帧A + 帧B (中间无间隔) | 2 帧, 分别正确 |
| TC09 | 三帧粘包 | 帧A + 帧B + 帧C | 3 帧, 均正确 |
| TC10 | 配置帧+上报帧粘包 | CMD帧 + REPORT帧 | 2 帧, 类型分配合适 |
| TC11 | 上报帧+配置应答粘包 | REPORT + ACK | 2 帧, 均正确 |

### 12.4 半包测试

| 编号 | 名称 | 输入 | 预期 |
|------|------|------|------|
| TC12 | 半包-仅帧头 | 收到 `F4 F3 F2` 后中断 | 状态机停留在 WAIT_HEAD_3, 无帧输出 |
| TC13 | 半包-缺长度 | 收到 `F4 F3 F2 F1` 后中断 | 停留在 WAIT_LENGTH_L, 无帧输出 |
| TC14 | 半包-缺负载 | 收到完整帧头+长度，缺 payload | 停留在 WAIT_PAYLOAD, 补充后完成 |
| TC15 | 半包恢复 | 半包 + 延迟补充剩余字节 | 1 帧, 正确解析 |
| TC16 | 超时半包丢弃 | 半包 + 超时 | 状态机复位, 记录 error |

### 12.5 错帧测试

| 编号 | 名称 | 输入 | 预期 |
|------|------|------|------|
| TC17 | 帧尾错误 | 正确数据但帧尾 `04 03 02 FF` | 丢弃, error_count++ |
| TC18 | Length 超大 | Length=0xFFFF | 超长保护, 复位 |
| TC19 | Length=0 | Length=0x0000 | 直接校验帧尾, 若帧尾正确则输出 |
| TC20 | 中间字节模拟帧头 | payload 中含 `F4F3F2F1` | 不应误触发, 校验通过后正常输出 |
| TC21 | 完全垃圾数据 | 随机字节流 | 不应解析出任何帧, 稳定运行 |

### 12.6 空数据/边界测试

| 编号 | 名称 | 输入 | 预期 |
|------|------|------|------|
| TC22 | 空输入 | 空字节流 | 无帧输出, 状态机不崩溃 |
| TC23 | 单字节输入 | `0xFC` | 等待后续, 无帧输出 |
| TC24 | 帧头命中但后续错 | `FC FB FA FD FF FF ...` | 帧尾不匹配, 丢弃 |
| TC25 | 极短帧 | Length=2, 命令+参数最短 | 正常解析 |
| TC26 | 无目标上报帧 | 完整帧, target_state=0x00, 距离=0 | 解析正确, state=NO_TARGET |

### 12.7 边界值测试

| 编号 | 名称 | 输入 | 预期 |
|------|------|------|------|
| TC27 | 最大距离 1000cm | detect_distance=E803 | 1000 cm |
| TC28 | 最小距离 1cm | moving_distance=0100 | 1 cm |
| TC29 | 能量 0 | moving_energy=00 | 能量 0 |
| TC30 | 能量 100 | static_energy=64 | 能量 100 |
| TC31 | 最大帧长 512 | 构造 512 字节帧 | 正常解析或受保护复位 |

### 12.8 波特率切换测试

| 编号 | 名称 | 输入 | 预期 |
|------|------|------|------|
| TC32 | 从 256000 切 115200 | A1命令 + code=04 + 保存 | 应答在旧波特率, 切换后新波特率通信正常 |
| TC33 | 确认读回波特率 | 读 A1 命令 | ret=0, baud_code=新值 |
| TC34 | 设置非法波特率 | code=0xFF | ret=1, 返回错误 |

### 12.9 测试运行示例

```python
# Python 测试框架示例 (pytest)
class TestLD2410BParser:
    def setup_method(self):
        self.parser = LD2410BParser()

    def feed_bytes(self, data: bytes):
        for b in data:
            self.parser.feed_byte(b)

    def test_basic_report_no_target(self):
        """TC01: 无目标上报帧"""
        frame = bytes([
            0xF4, 0xF3, 0xF2, 0xF1,  # 帧头
            0x08, 0x00,               # Length=8
            0x02, 0xAA,               # DataType=2, fixed AA
            0x00,                     # target_state=NO_TARGET
            0x00, 0x00,               # moving_distance=0
            0x00,                     # moving_energy=0
            0x00, 0x00,               # static_distance=0
            0x00,                     # static_energy=0
            0x00, 0x00,               # detect_distance=0
            0x55,                     # fixed 55
            0x00,                     # checksum (to be calculated)
            0xF8, 0xF7, 0xF6, 0xF5,  # 帧尾
        ])
        # 计算校验和
        frame[-5] = sum(frame[:-5]) & 0xFF

        self.feed_bytes(frame)
        assert len(self.parser.frames) == 1
        report = self.parser.frames[0]
        assert report.frame_type == 'REPORT'
        assert report.target_state == 0x00  # NO_TARGET

    def test_sticky_packet(self):
        """TC08: 两帧粘包"""
        frame1 = build_report_frame(state=0x01, moving_dist=50)
        frame2 = build_report_frame(state=0x02, static_dist=100)
        self.feed_bytes(frame1 + frame2)
        assert len(self.parser.frames) == 2

    def test_half_packet_recovery(self):
        """TC15: 半包恢复"""
        frame = build_report_frame(state=0x03, moving_dist=30, static_dist=80)
        half = frame[:10]   # 前半
        rest = frame[10:]  # 后半
        self.feed_bytes(half)
        assert len(self.parser.frames) == 0  # 尚未完成
        self.feed_bytes(rest)
        assert len(self.parser.frames) == 1  # 补充后完成

    def test_garbage_data(self):
        """TC21: 完全垃圾数据"""
        import random
        garbage = bytes([random.randint(0, 255) for _ in range(1000)])
        self.feed_bytes(garbage)
        assert len(self.parser.frames) == 0  # 不应产生有效帧
        assert not self.parser.is_stuck()    # 不应卡死

    def test_engineer_mode(self):
        """TC07: 工程模式帧"""
        frame = build_engineer_frame(
            state=0x03, moving_dist=30, static_dist=100,
            gates=[(0,0,30,30), (20,10,30,30), (40,30,30,30)] + [(0,0,30,30)]*6
        )
        self.feed_bytes(frame)
        assert len(self.parser.frames) == 1
        report = self.parser.frames[0]
        assert report.datatype == 0x01
        assert len(report.gates) == 9
```

### 12.10 测试覆盖矩阵

| 测试维度 | 覆盖用例 | 通过标准 |
|----------|---------|---------|
| 正常解码 | TC01-TC07 | 所有字段解析正确 |
| 粘包 | TC08-TC11 | 多帧完整分离 |
| 半包 | TC12-TC16 | 半包保持、恢复、超时复位 |
| 错帧/异常 | TC17-TC21 | 丢弃正确，不崩溃 |
| 空/边界 | TC22-TC26 | 稳健处理 |
| 值域边界 | TC27-TC31 | 边界值正确 |
| 波特率 | TC32-TC34 | 切换流程正确 |

---

## 附录

### A. 命令速查表

| 命令字 | 方向 | 功能 | 参数 |
|--------|------|------|------|
| `0x00FF` | 发→收 | 使能配置 | 无 |
| `0x00FE` | 发→收 | 结束配置 | 无 |
| `0x0061` | 发→收 | 读取参数 | 无 |
| `0x0062` | 发→收 | 开启工程模式 | `0x00` |
| `0x0063` | 发→收 | 关闭工程模式 | `0x00` |
| `0x0064` | 发→收 | 设置灵敏度 | `[gate][mov_th][stc_th]` |
| `0x00A0` | 发→收 | 读取固件版本 | 无 |
| `0x00A1` | 发→收 | 设置/读取波特率 | 读: `0x00`; 写: `[code][save]` |
| `0x00A2` | 发→收 | 恢复出厂设置 | 无 |
| `0x00A3` | 发→收 | 重启模块 | 无 |
| `0x00AA` | 发→收 | 设置距离分辨率 | `[resolution]` |
| `0x000B` | 发→收 | 开始底噪检测 | `0x00` |
| `0x001B` | 发→收 | 查询底噪检测状态 | 无 |

### B. 校验和算法

上报帧的 Check 字节算法：

```c
uint8_t ld2410b_checksum(const uint8_t *frame, uint16_t len) {
    // 校验范围: 从帧头 (F4F3F2F1) 开始到 0x55 之前 (不含 0x55)
    // len = 到 55 标记之前的字节数
    uint32_t sum = 0;
    for (uint16_t i = 0; i < len; i++) {
        sum += frame[i];
    }
    return (uint8_t)(sum & 0xFF);
}
```

验证：`sum(frame[0..check_pos-1]) & 0xFF == frame[check_pos]`

### C. 推荐 Parser 集成流程

```
系统初始化
   │
   ├── 1. UART 初始化 (256000 8N1)
   ├── 2. Parser 初始化 (状态复位)
   ├── 3. 使能配置模式 (0x00FF)
   ├── 4. 读取固件版本 (0x00A0)  ← 记录日志
   ├── 5. 查询/开始底噪检测 (0x001B/0x000B)
   ├── 6. 读取/调整灵敏度 (0x0061/0x0064)
   ├── 7. 结束配置模式 (0x00FE)
   │
   └── 8. 进入主循环
         ├── UART RX → ld2410b_feed_byte() 逐一处理
         ├── 回调分发 on_report() / on_response()
         └── 心跳/异常重连机制
```

### D. 错误码汇总

| 错误码 | 含义 | 处理建议 |
|--------|------|---------|
| `ERR_NONE` (0x00) | 无错误 | — |
| `ERR_FRAME_HEAD` (0x01) | 帧头不匹配 | 丢弃, 跳过 1 字节重试 |
| `ERR_FRAME_TAIL` (0x02) | 帧尾不匹配 | 丢弃当前帧, 复位 |
| `ERR_FRAME_CHECKSUM` (0x03) | 校验和不匹配 | 丢弃, 记录统计 |
| `ERR_FRAME_TOO_LARGE` (0x04) | 帧长度超限 | 复位, 可能为总线干扰 |
| `ERR_FRAME_TIMEOUT` (0x05) | 帧接收超时 | 复位, 尝试重新同步 |
| `ERR_CMD_TIMEOUT` (0x10) | 配置命令应答超时 | 重试或重启模块 |

---

> **文档修订记录**  
> v1.0 — 初始版本，包含完整的 LD2410B 协议解析方案、Parser 状态机设计、API 封装和测试用例。
