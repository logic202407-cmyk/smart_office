// ============================================================
// config.h �?引脚宏定�?+ 系统参数定义
// 项目：智慧办公防偷窥人体感知系统
// 状态：引脚已按原理�?网表确认�?026-05-08�?// ============================================================
// 确认来源：Netlist_Schematic1 + 原理�?PinMap
// 网络连接关系�?//   SDA: U1.4 <-> U4.4 <-> U6.2
//   SCL: U1.5 <-> U4.3 <-> U6.5
//   TX_RADAR: U1.10 <-> U2.2 <-> U5.4
//   RX_RADAR: U1.11 <-> U2.3 <-> U5.3
//   IO8: U1.12 <-> U6.3
//   D-: U1.13   D+: U1.14
//   IO21: U1.23 <-> U2.1
//   IO0: U1.27    EN: U1.3
//   TXD0: U1.37   RXD0: U1.36
// ============================================================
#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ============================================================
// 1. I2C 总线 (OLED + PAJ7620)
// ============================================================
#define PIN_I2C_SDA      4   // U1.4 网络SDA �?confirmed GPIO4
#define PIN_I2C_SCL      5   // U1.5 网络SCL �?confirmed GPIO5
#define I2C_FREQ    400000   // I2C 时钟 400kHz (Fast Mode)

// ============================================================
// 2. 雷达 UART (LD2410B)
// ============================================================
#define PIN_RADAR_TX     17  // U1.10 网络TX_RADAR = IO17, 雷达TX->ESP32 RX
#define PIN_RADAR_RX     18  // U1.11 网络RX_RADAR = IO18, ESP32 TX->雷达RX
#define PIN_RADAR_OUT    21  // U1.23 网络IO21 �?confirmed GPIO21, 雷达目标输出中断
#define RADAR_UART_BAUD  256000  // LD2410B 默认波特�?#define RADAR_UART_RX_BUF 256    // UART 接收缓冲�?#define RADAR_FRAME_TIMEOUT_MS 100  // 雷达帧解析超�?(半包保护, ms)

// ============================================================
// 3. 手势传感�?(PAJ7620)
// ============================================================
#define PIN_PAJ7620_INT  8   // U1.12 网络IO8 �?confirmed GPIO8, 手势中断
// PAJ7620 I2C 地址: 0x73 (默认)
#define PAJ7620_I2C_ADDR  0x73

// ============================================================
// 4. 按键 / LED
// ============================================================
#define PIN_BOOT_BTN     0   // U1.27 网络IO0 �?confirmed GPIO0 (BOOT 按钮)
#define PIN_LED          48  // 常见 ESP32-S3-DevKitC-1 板载 LED (RGB, 高电平亮)

// ============================================================
// 5. OLED 显示参数
// ============================================================
#define OLED_I2C_ADDR    0x3C    // SSD1306 最常见 I2C 地址
#define OLED_WIDTH       128     // 宽度 128 像素
#define OLED_HEIGHT      64      // 高度 64 像素
#define OLED_RESET_PIN   -1      // 无独立复位引�?(�?I2C 总线管理)
// OLED_SCL / OLED_SDA �?U8g2 构造函数所需别名 (�?PIN_I2C_SCL/PIN_I2C_SDA 相同)
#define OLED_SCL          PIN_I2C_SCL
#define OLED_SDA          PIN_I2C_SDA

// ============================================================
// 7. 系统参数 (状态机, 阶段2启用)
// ============================================================
#define NEAR_DIST_CM     150     // "接近" 阈�?(cm)
#define VERY_NEAR_DIST_CM 80     // "非常�? 阈�?(cm)
#define SUSPECT_TIME_MS  3000    // 疑似偷窥判定时间 (3s)
#define ALARM_TIME_MS    8000    // 告警持续时间 (8s)
#define NO_TARGET_TIMEOUT_MS 2000 // 目标消失降级时间

// ============================================================
// 8. 串口调试
// ============================================================
#define SERIAL_BAUD      115200  // USB CDC 串口波特�?#define PC_HEARTBEAT_MS  5000    // 定时心跳间隔 (PC 通信)

// EI experiment wireless telemetry: station first, fallback AP preserved.
#define WIFI_TELEMETRY_ENABLED  1
#define WIFI_TELEMETRY_PORT     3333
#define WIFI_TELEMETRY_STA_CONNECT_TIMEOUT_MS 15000UL
#define WIFI_TELEMETRY_FALLBACK_AP_SSID     "SmartOffice-Lab"
#define WIFI_TELEMETRY_FALLBACK_AP_PASSWORD "SmartOfficeLab"

// ============================================================
// 9. LED 闪烁参数 (Phase 1 验证�?
// ============================================================
#define LED_BLINK_MS     500     // LED 闪烁间隔 (ms)

// ============================================================
// 10. 灵敏度系�?(默认 1.0)
// ============================================================
#define SENSITIVITY_FACTOR  1.0f

#endif // CONFIG_H
