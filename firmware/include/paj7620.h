// ============================================================
// paj7620.h — PAJ7620U2 手势传感器驱动头文件
// 项目：智慧办公防偷窥人体感知系统
// 阶段：Phase 5 — 手势控制模块
// ============================================================
// 通信方式：I2C (与 OLED 共用总线, SDA=GPIO4, SCL=GPIO5)
// I2C 地址：0x73 (PAJ7620_I2C_ADDR)
// 中断引脚：GPIO8 (PIN_PAJ7620_INT, 低电平有效)
// ============================================================
// 手势识别库 PAJ7620U2 支持的 9 种手势 (含 WAVE):
//   UP / DOWN / LEFT / RIGHT / FORWARD / BACKWARD
//   CLOCKWISE / COUNTERCLOCKWISE / WAVE
// ============================================================
#ifndef PAJ7620_H
#define PAJ7620_H

#include <Arduino.h>
#include <Wire.h>
#include "config.h"

// ============================================================
// GestureType — 手势类型枚举
// ============================================================
// 与 PAJ7620U2 数据手册的 Gesture ID 一一对应:
//   0x00 = NONE (无手势)
//   0x01 = UP
//   0x02 = DOWN
//   0x03 = LEFT
//   0x04 = RIGHT
//   0x05 = FORWARD
//   0x06 = BACKWARD
//   0x07 = CLOCKWISE
//   0x08 = COUNTERCLOCKWISE
//   0x09 = WAVE
// ============================================================
enum class GestureType : uint8_t {
    NONE              = 0x00,
    UP                = 0x01,
    DOWN              = 0x02,
    LEFT              = 0x03,
    RIGHT             = 0x04,
    FORWARD           = 0x05,
    BACKWARD          = 0x06,
    CLOCKWISE         = 0x07,
    COUNTERCLOCKWISE  = 0x08,
    WAVE              = 0x09
};

// ============================================================
// Paj7620 — PAJ7620U2 手势传感器驱动类
// ============================================================
// 使用说明：
//   1. 确保在调用本类前 I2C (Wire) 已在 main.cpp 中初始化
//      使用 Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL)
//   2. 调用 begin() 执行传感器初始化序列
//   3. 在 loop() 中周期性调用 readGesture() 获取手势
//   4. 手势结果自带防抖处理，同一手势连续触发间隔
//      需大于 DEBOUNCE_MS
// ============================================================
class Paj7620 {
public:
    Paj7620();

    // ---- 初始化 ----
    // 执行 PAJ7620U2 完整的初始化序列 (寄存器配置)
    // 返回 true 表示初始化成功，false 表示 I2C 通信失败
    bool begin();

    // ---- 读取手势 ----
    // 轮询读取当前手势 (不依赖中断引脚)
    // 内部包含防抖处理: 同一手势在 DEBOUNCE_MS 内不重复触发
    // 返回 GestureType 枚举值
    GestureType readGesture();

    // ---- 读取手势 (带中断检测) ----
    // 检查中断引脚 (PIN_PAJ7620_INT) 状态后再读取
    // 返回 GestureType 枚举值
    GestureType readGestureWithInterrupt();

    // ---- 获取手势名称 ----
    // 将 GestureType 转换为可读字符串 (中文)
    static const char* getGestureName(GestureType g);

    // ---- 获取手势名称 (英文) ----
    static const char* getGestureNameEN(GestureType g);

    // ---- 状态查询 ----
    // 传感器是否已初始化
    bool isInitialized() const { return _initialized; }

    // ---- 设置防抖时间 ----
    void setDebounceMs(uint32_t ms) { _debounceMs = ms; }

    // ---- 调试: 上次读取的原始手势 ID ----
    uint8_t getLastRawGesture() const { return _lastRawGesture; }
    bool readRawGestureRegs(uint8_t& gestureId, uint8_t& gestureId2);
    GestureType decodeRawGesture(uint8_t gestureId, uint8_t gestureId2);

private:
    // ============================================================
    // PAJ7620U2 寄存器地址定义
    // ============================================================
    static constexpr uint8_t REG_BANK_SEL     = 0xEF;  // 寄存器组选择
    static constexpr uint8_t REG_SUSPEND      = 0xFE;  // 休眠控制
    static constexpr uint8_t REG_GESTURE_ID   = 0x43;  // 手势 ID (Bank 0)
    static constexpr uint8_t REG_GESTURE_ID2  = 0x44;  // 手势 ID 扩展 (Bank 0)

    // ============================================================
    // 常量
    // ============================================================
    static constexpr uint8_t I2C_ADDR         = PAJ7620_I2C_ADDR;  // 0x73
    static constexpr uint32_t DEFAULT_DEBOUNCE_MS = 150;  // 默认防抖时间 (ms)
    static constexpr int      I2C_TIMEOUT_MS  = 50;     // I2C 通信超时

    // ============================================================
    // 内部方法
    // ============================================================
    // 写单字节寄存器
    bool _writeReg(uint8_t reg, uint8_t value);

    // 读单字节寄存器
    bool _readReg(uint8_t reg, uint8_t& value);

    // 批量写寄存器 (用于初始化序列)
    bool _writeRegs(const uint8_t regs[][2], size_t count);

    // 切换寄存器组: bank=0 -> Bank 0, bank=1 -> Bank 1
    bool _selectBank(uint8_t bank);

    // 传感器硬件复位/唤醒
    bool _wakeUp();

    // 执行完整初始化序列
    bool _initRegisters();

    // 防抖检测: 同一手势是否在防抖窗口内
    bool _isDebouncing(GestureType gesture);

    // ============================================================
    // 成员变量
    // ============================================================
    bool        _initialized;       // 初始化标志
    GestureType _lastGesture;       // 上次有效手势
    uint32_t    _lastGestureTime;   // 上次有效手势的时间戳 (ms)
    uint32_t    _debounceMs;        // 防抖时间窗口 (ms)
    uint8_t     _lastRawGesture;    // 上次原始手势值 (调试用)
};

#endif // PAJ7620_H
