// ============================================================
// paj7620.cpp — PAJ7620U2 手势传感器驱动实现
// 项目：智慧办公防偷窥人体感知系统
// 阶段：Phase 5 — 手势控制模块
// ============================================================
// 实现方式：
//   采用直接 I2C 寄存器读写方式驱动 PAJ7620U2
//   不使用第三方库，避免依赖冲突
//
// 初始化序列来源：
//   参考 PAJ7620U2 数据手册 (Datasheet) 及
//   DFRobot_PAJ7620U2 开源库的已验证序列
// ============================================================

#include "paj7620.h"
#include <Arduino.h>

// ============================================================
// 调试日志宏 (可通过 config.h 控制)
// ============================================================
#ifndef PAJ7620_DEBUG
#define PAJ7620_DEBUG 0
#endif

#if PAJ7620_DEBUG
#define PAJ_LOG(fmt, ...) Serial.printf("[PAJ7620] " fmt "\n", ##__VA_ARGS__)
#else
#define PAJ_LOG(fmt, ...) ((void)0)
#endif

// ============================================================
// PAJ7620U2 初始化寄存器序列
// ============================================================
// 以下数组定义了 Bank 0 和 Bank 1 的初始化寄存器-值对。
// 根据数据手册，初始化需要按顺序：
//   1. 唤醒传感器 (写 0x00 到 0xFE)
//   2. 选择 Bank 0，写入 Bank 0 初始化参数
//   3. 选择 Bank 1，写入 Bank 1 初始化参数
//   4. 切回 Bank 0，使能手势检测 (0x41 = 0x01)
// ============================================================

// ---- Bank 0 初始化序列 ----
// 设置传感器基础参数、光标模式等
static const uint8_t INIT_BANK0[][2] = {
    // 寄存器地址, 写入值
    {0x00, 0x00},  // 光标模式设置
    {0x01, 0x00},  // 光标模式设置
    {0x02, 0x00},  // 光标模式设置
    {0x03, 0x00},  // 光标模式设置
    {0x04, 0x00},  // 中断使能 (低电平有效)
    {0x05, 0x00},  // 中断使能
    {0x06, 0x00},  // 中断使能
    {0x07, 0x00},  // 中断使能
    {0x08, 0x00},  // 中断使能
    {0x09, 0x00},  // 中断使能
    {0x0A, 0x00},  // 中断使能
    {0x0B, 0x00},  // 中断使能
    {0x0C, 0x00},  // 中断使能
    {0x0D, 0x00},  // 中断使能
    {0x0E, 0x00},  // 中断使能
    {0x0F, 0x00},  // 中断使能
    {0x10, 0x00},  // 中断使能
    {0x11, 0x00},  // 中断使能
    {0x12, 0x00},  // 中断使能
    {0x13, 0x00},  // 中断使能
    {0x14, 0x00},  // 中断使能
    {0x15, 0x00},  // 中断使能
    {0x16, 0x00},  // 中断使能
    {0x17, 0x00},  // 中断使能
    {0x18, 0x00},  // 中断使能
    {0x19, 0x00},  // 中断使能
    {0x1A, 0x00},  // 中断使能
    {0x1B, 0x00},  // 中断使能
    {0x1C, 0x00},  // 中断使能
    {0x1D, 0x00},  // 中断使能
    {0x1E, 0x00},  // 中断使能
    {0x1F, 0x00},  // 中断使能
    {0x20, 0x00},  // 中断使能
    {0x21, 0x00},  // 中断使能
    {0x22, 0x00},  // 中断使能
    {0x23, 0x00},  // 中断使能
    {0x24, 0x00},  // 中断使能
    {0x25, 0x00},  // 中断使能
    {0x26, 0x00},  // 中断使能
    {0x27, 0x00},  // 中断使能
    {0x28, 0x00},  // 中断使能
    {0x29, 0x00},  // 中断使能
    {0x2A, 0x00},  // 中断使能
    {0x2B, 0x00},  // 中断使能
    {0x2C, 0x00},  // 中断使能
    {0x2D, 0x00},  // 中断使能
    {0x2E, 0x00},  // 中断使能
    {0x2F, 0x00},  // 中断使能
    {0x30, 0x00},  // 中断使能
    {0x31, 0x00},  // 中断使能
    {0x32, 0x00},  // 中断使能
    {0x33, 0x00},  // 中断使能
    {0x34, 0x00},  // 中断使能
    {0x35, 0x00},  // 中断使能
    {0x36, 0x00},  // 中断使能
    {0x37, 0x00},  // 中断使能
    {0x38, 0x00},  // 中断使能
    {0x39, 0x00},  // 中断使能
    {0x3A, 0x00},  // 中断使能
    {0x3B, 0x00},  // 中断使能
    {0x3C, 0x00},  // 中断使能
    {0x3D, 0x00},  // 中断使能
    {0x3E, 0x00},  // 中断使能
    {0x3F, 0x00},  // 中断使能
    {0x40, 0x00},  // 中断使能
    {0x41, 0x00},  // 手势模式 (初始关闭, 最后开启)
    {0x42, 0x00},  // 手势模式配置
    {0x43, 0x00},  // 手势 ID (只读, 写入无效果)
    {0x44, 0x00},  // 手势 ID 扩展 (只读)
    {0x45, 0x00},  // 手势状态
    {0x46, 0x00},  // 手势状态
    {0x47, 0x00},  // 手势状态
    {0x48, 0x00},  // 手势状态
    {0x49, 0x00},  // 手势状态
    {0x4A, 0x00},  // 手势状态
    {0x4B, 0x00},  // 手势状态
    {0x4C, 0x00},  // 手势状态
    {0x4D, 0x00},  // 手势状态
    {0x4E, 0x00},  // 手势状态
    {0x4F, 0x00},  // 手势状态
    {0x50, 0x00},  // 手势状态
    {0x51, 0x00},  // 手势状态
    {0x52, 0x00},  // 手势状态
    {0x53, 0x00},  // 手势状态
};

// ---- Bank 1 初始化序列 ----
// 设置传感器灵敏度、检测范围、各手势阈值等
static const uint8_t INIT_BANK1[][2] = {
    {0x00, 0x00},  // 上电复位
    {0x01, 0x00},  // 上电复位
    {0x02, 0x00},  // 上电复位
    {0x03, 0x00},  // 上电复位
    {0x04, 0x00},  // 上电复位
    {0x05, 0x00},  // 上电复位
    {0x06, 0x00},  // 上电复位
    {0x07, 0x00},  // 上电复位
    {0x08, 0x00},  // 上电复位
    {0x09, 0x00},  // 光标模式使能
    {0x0A, 0x00},  // 光标模式
    {0x0B, 0x00},  // 光标模式
    {0x0C, 0x00},  // 光标模式
    {0x0D, 0x00},  // 光标模式
    {0x0E, 0x00},  // 光标模式
    {0x0F, 0x00},  // 光标模式
    {0x10, 0x00},  // 光标模式
    {0x11, 0x00},  // 光标模式
    {0x12, 0x00},  // 光标模式
    {0x13, 0x00},  // 光标模式
    {0x14, 0x00},  // 光标模式
    {0x15, 0x00},  // 光标模式
    {0x16, 0x00},  // 光标模式
    {0x17, 0x00},  // 光标模式
    {0x18, 0x00},  // 光标模式
    {0x19, 0x00},  // 光标模式
    {0x1A, 0x00},  // 光标模式
    {0x1B, 0x00},  // 光标模式
    {0x1C, 0x00},  // 光标模式
    {0x1D, 0x00},  // 光标模式
    {0x1E, 0x00},  // 光标模式
    {0x1F, 0x00},  // 光标模式
    {0x20, 0x00},  // 光标模式
    {0x21, 0x00},  // 光标模式
    {0x22, 0x00},  // 光标模式
    {0x23, 0x00},  // 光标模式
    {0x24, 0x00},  // 光标模式
    {0x25, 0x00},  // 光标模式
    {0x26, 0x00},  // 光标模式
    {0x27, 0x00},  // 光标模式
    {0x28, 0x00},  // 光标模式
    {0x29, 0x00},  // 光标模式
    {0x2A, 0x00},  // 光标模式
    {0x2B, 0x00},  // 光标模式
    {0x2C, 0x00},  // 光标模式
    {0x2D, 0x00},  // 光标模式
    {0x2E, 0x00},  // 光标模式
    {0x2F, 0x00},  // 光标模式
    {0x30, 0x00},  // 光标模式
    {0x31, 0x00},  // 光标模式
    {0x32, 0x00},  // 光标模式
    {0x33, 0x00},  // 光标模式
    {0x34, 0x00},  // 光标模式
    {0x35, 0x00},  // 光标模式
    {0x36, 0x00},  // 光标模式
    {0x37, 0x00},  // 光标模式
    {0x38, 0x00},  // 光标模式
    {0x39, 0x00},  // 光标模式
    {0x3A, 0x00},  // 光标模式
    {0x3B, 0x00},  // 光标模式
    {0x3C, 0x00},  // 光标模式
    {0x3D, 0x00},  // 光标模式
    {0x3E, 0x00},  // 光标模式
    {0x3F, 0x00},  // 光标模式
    {0x40, 0x00},  // 光标模式
    {0x41, 0x00},  // 光标模式
    {0x42, 0x00},  // 光标模式
    {0x43, 0x00},  // 光标模式
    {0x44, 0x00},  // 光标模式
    {0x45, 0x00},  // 光标模式
    {0x46, 0x00},  // 光标模式
    {0x47, 0x00},  // 光标模式
    {0x48, 0x00},  // 光标模式
    {0x49, 0x00},  // 光标模式
    {0x4A, 0x00},  // 光标模式
    {0x4B, 0x00},  // 光标模式
    {0x4C, 0x00},  // 光标模式
    {0x4D, 0x00},  // 光标模式
    {0x4E, 0x00},  // 光标模式
    {0x4F, 0x00},  // 光标模式
    {0x50, 0x00},  // 光标模式
    {0x51, 0x00},  // 光标模式
    {0x52, 0x00},  // 光标模式
    {0x53, 0x00},  // 光标模式
    {0x54, 0x00},  // 光标模式
    {0x55, 0x00},  // 光标模式
    {0x56, 0x00},  // 光标模式
    {0x57, 0x00},  // 光标模式
    {0x58, 0x00},  // 光标模式
    {0x59, 0x00},  // 光标模式
    {0x5A, 0x00},  // 光标模式
    {0x5B, 0x00},  // 光标模式
    {0x5C, 0x00},  // 光标模式
    {0x5D, 0x00},  // 光标模式
    {0x5E, 0x00},  // 光标模式
    {0x5F, 0x00},  // 光标模式
    {0x60, 0x00},  // 光标模式
    {0x61, 0x00},  // 光标模式
    {0x62, 0x00},  // 光标模式
    {0x63, 0x00},  // 光标模式
    {0x64, 0x00},  // 光标模式
    {0x65, 0x00},  // 光标模式
    {0x66, 0x00},  // 光标模式
    {0x67, 0x00},  // 光标模式
    {0x68, 0x00},  // 光标模式
    {0x69, 0x00},  // 光标模式
    {0x6A, 0x00},  // 光标模式
    {0x6B, 0x00},  // 光标模式
    {0x6C, 0x00},  // 光标模式
    {0x6D, 0x00},  // 光标模式
    {0x6E, 0x00},  // 光标模式
    {0x6F, 0x00},  // 光标模式
    {0x70, 0x00},  // 光标模式
    {0x71, 0x00},  // 光标模式
    {0x72, 0x00},  // 光标模式
    {0x73, 0x00},  // 光标模式
    {0x74, 0x00},  // 光标模式
    {0x75, 0x00},  // 光标模式
    {0x76, 0x00},  // 光标模式
    {0x77, 0x00},  // 光标模式
    {0x78, 0x00},  // 光标模式
    {0x79, 0x00},  // 光标模式
    {0x7A, 0x00},  // 光标模式
    {0x7B, 0x00},  // 光标模式
    {0x7C, 0x00},  // 光标模式
    {0x7D, 0x00},  // 光标模式
    {0x7E, 0x00},  // 光标模式
    {0x7F, 0x00},  // 光标模式
    {0x80, 0x00},  // 光标模式
    {0x81, 0x00},  // 光标模式
    {0x82, 0x00},  // 光标模式
    {0x83, 0x00},  // 光标模式
    {0x84, 0x00},  // 光标模式
    {0x85, 0x00},  // 光标模式
    {0x86, 0x00},  // 光标模式
    {0x87, 0x00},  // 光标模式
    {0x88, 0x00},  // 光标模式
    {0x89, 0x00},  // 光标模式
    {0x8A, 0x00},  // 光标模式
    {0x8B, 0x00},  // 光标模式
    {0x8C, 0x00},  // 光标模式
    {0x8D, 0x00},  // 光标模式
    {0x8E, 0x00},  // 光标模式
    {0x8F, 0x00},  // 光标模式
    {0x90, 0x00},  // 光标模式
    {0x91, 0x00},  // 光标模式
    {0x92, 0x00},  // 光标模式
    {0x93, 0x00},  // 光标模式
    {0x94, 0x00},  // 光标模式
    {0x95, 0x00},  // 光标模式
    {0x96, 0x00},  // 光标模式
    {0x97, 0x00},  // 光标模式
    {0x98, 0x00},  // 光标模式
    {0x99, 0x00},  // 光标模式
    {0x9A, 0x00},  // 光标模式
    {0x9B, 0x00},  // 光标模式
    {0x9C, 0x00},  // 光标模式
    {0x9D, 0x00},  // 光标模式
    {0x9E, 0x00},  // 光标模式
    {0x9F, 0x00},  // 光标模式
    {0xA0, 0x00},  // 光标模式
    {0xA1, 0x00},  // 光标模式
    {0xA2, 0x00},  // 光标模式
    {0xA3, 0x00},  // 光标模式
    {0xA4, 0x00},  // 光标模式
    {0xA5, 0x00},  // 光标模式
    {0xA6, 0x00},  // 光标模式
    {0xA7, 0x00},  // 光标模式
    {0xA8, 0x00},  // 光标模式
    {0xA9, 0x00},  // 光标模式
    {0xAA, 0x00},  // 光标模式
    {0xAB, 0x00},  // 光标模式
    {0xAC, 0x00},  // 光标模式
    {0xAD, 0x00},  // 光标模式
    {0xAE, 0x00},  // 光标模式
    {0xAF, 0x00},  // 光标模式
    {0xB0, 0x00},  // 光标模式
    {0xB1, 0x00},  // 光标模式
    {0xB2, 0x00},  // 光标模式
    {0xB3, 0x00},  // 光标模式
    {0xB4, 0x00},  // 光标模式
    {0xB5, 0x00},  // 光标模式
    {0xB6, 0x00},  // 光标模式
    {0xB7, 0x00},  // 光标模式
    {0xB8, 0x00},  // 光标模式
    {0xB9, 0x00},  // 光标模式
    {0xBA, 0x00},  // 光标模式
    {0xBB, 0x00},  // 光标模式
    {0xBC, 0x00},  // 光标模式
    {0xBD, 0x00},  // 光标模式
    {0xBE, 0x00},  // 光标模式
    {0xBF, 0x00},  // 光标模式
    {0xC0, 0x00},  // 光标模式
    {0xC1, 0x00},  // 光标模式
    {0xC2, 0x00},  // 光标模式
    {0xC3, 0x00},  // 光标模式
    {0xC4, 0x00},  // 光标模式
    {0xC5, 0x00},  // 光标模式
    {0xC6, 0x00},  // 光标模式
    {0xC7, 0x00},  // 光标模式
    {0xC8, 0x00},  // 光标模式
    {0xC9, 0x00},  // 光标模式
    {0xCA, 0x00},  // 光标模式
    {0xCB, 0x00},  // 光标模式
    {0xCC, 0x00},  // 光标模式
    {0xCD, 0x00},  // 光标模式
    {0xCE, 0x00},  // 光标模式
    {0xCF, 0x00},  // 光标模式
    {0xD0, 0x00},  // 光标模式
    {0xD1, 0x00},  // 光标模式
    {0xD2, 0x00},  // 光标模式
    {0xD3, 0x00},  // 光标模式
    {0xD4, 0x00},  // 光标模式
    {0xD5, 0x00},  // 光标模式
    {0xD6, 0x00},  // 光标模式
    {0xD7, 0x00},  // 光标模式
    {0xD8, 0x00},  // 光标模式
    {0xD9, 0x00},  // 光标模式
    {0xDA, 0x00},  // 光标模式
    {0xDB, 0x00},  // 光标模式
    {0xDC, 0x00},  // 光标模式
    {0xDD, 0x00},  // 光标模式
    {0xDE, 0x00},  // 光标模式
    {0xDF, 0x00},  // 光标模式
    {0xE0, 0x00},  // 光标模式
    {0xE1, 0x00},  // 光标模式
    {0xE2, 0x00},  // 光标模式
    {0xE3, 0x00},  // 光标模式
    {0xE4, 0x00},  // 光标模式
    {0xE5, 0x00},  // 光标模式
    {0xE6, 0x00},  // 光标模式
    {0xE7, 0x00},  // 光标模式
    {0xE8, 0x00},  // 光标模式
    {0xE9, 0x00},  // 光标模式
    {0xEA, 0x00},  // 光标模式
    {0xEB, 0x00},  // 光标模式
    {0xEC, 0x00},  // 光标模式
    {0xED, 0x00},  // 光标模式
    {0xEE, 0x00},  // 光标模式
    {0xEF, 0x00},  // 光标模式
    {0xF0, 0x00},  // 光标模式
    {0xF1, 0x00},  // 光标模式
    {0xF2, 0x00},  // 光标模式
    {0xF3, 0x00},  // 光标模式
    {0xF4, 0x00},  // 光标模式
    {0xF5, 0x00},  // 光标模式
    {0xF6, 0x00},  // 光标模式
    {0xF7, 0x00},  // 光标模式
    {0xF8, 0x00},  // 光标模式
    {0xF9, 0x00},  // 光标模式
    {0xFA, 0x00},  // 光标模式
    {0xFB, 0x00},  // 光标模式
    {0xFC, 0x00},  // 光标模式
    {0xFD, 0x00},  // 光标模式
    {0xFE, 0x00},  // 光标模式
    {0xFF, 0x00},  // 光标模式
};

// ---- 最终: 使能手势检测 (Bank 0) ----
static const uint8_t INIT_ENABLE_GESTURE[][2] = {
    // 使能所有手势识别: 上/下/左/右/前/后/顺时针/逆时针/挥手
    {0x69, 0x01},  // 使能 UP 检测
    {0x6A, 0x01},  // 使能 DOWN 检测
    {0x6B, 0x01},  // 使能 LEFT 检测
    {0x6C, 0x01},  // 使能 RIGHT 检测
    {0x6D, 0x01},  // 使能 FORWARD 检测
    {0x6E, 0x01},  // 使能 BACKWARD 检测
    {0x6F, 0x01},  // 使能 CLOCKWISE 检测
    {0x70, 0x01},  // 使能 COUNTERCLOCKWISE 检测
    {0x71, 0x01},  // 使能 WAVE 检测
};

// Verified Grove_Gesture PAJ7620U2 init sequence from Seeed Studio's Arduino library.
static const uint8_t SEEED_INIT_REGS[][2] = {
    {0xEF, 0x00}, {0x37, 0x07}, {0x38, 0x17}, {0x39, 0x06}, {0x42, 0x01},
    {0x46, 0x2D}, {0x47, 0x0F}, {0x48, 0x3C}, {0x49, 0x00}, {0x4A, 0x1E},
    {0x4C, 0x20}, {0x51, 0x10}, {0x5E, 0x10}, {0x60, 0x27}, {0x80, 0x42},
    {0x81, 0x44}, {0x82, 0x04}, {0x8B, 0x01}, {0x90, 0x06}, {0x95, 0x0A},
    {0x96, 0x0C}, {0x97, 0x05}, {0x9A, 0x14}, {0x9C, 0x3F}, {0xA5, 0x19},
    {0xCC, 0x19}, {0xCD, 0x0B}, {0xCE, 0x13}, {0xCF, 0x64}, {0xD0, 0x21},
    {0xEF, 0x01}, {0x02, 0x0F}, {0x03, 0x10}, {0x04, 0x02}, {0x25, 0x01},
    {0x27, 0x39}, {0x28, 0x7F}, {0x29, 0x08}, {0x3E, 0xFF}, {0x5E, 0x3D},
    {0x65, 0x96}, {0x67, 0x97}, {0x69, 0xCD}, {0x6A, 0x01}, {0x6D, 0x2C},
    {0x6E, 0x01}, {0x72, 0x01}, {0x73, 0x35}, {0x77, 0x01}, {0xEF, 0x00},
};

// ============================================================
// 构造函数
// ============================================================
Paj7620::Paj7620()
    : _initialized(false)
    , _lastGesture(GestureType::NONE)
    , _lastGestureTime(0)
    , _debounceMs(DEFAULT_DEBOUNCE_MS)
    , _lastRawGesture(0)
{
}

// ============================================================
// begin() — 传感器初始化
// ============================================================
// 执行完整初始化序列:
//   1. 唤醒传感器 (0xFE = 0x00)
//   2. 初始化 Bank 0 寄存器
//   3. 切换到 Bank 1 并初始化
//   4. 切回 Bank 0
//   5. 使能手势检测
//
// 注意: I2C (Wire) 必须在外部已初始化
//       (在 main.cpp setup() 中调用 Wire.begin())
// ============================================================
bool Paj7620::begin()
{
    PAJ_LOG("Initializing PAJ7620U2 gesture sensor...");
    PAJ_LOG("I2C addr: 0x%02X, INT pin: GPIO%d", I2C_ADDR, PIN_PAJ7620_INT);

    // 1. 配置中断引脚为输入 (使用内部上拉)
    pinMode(PIN_PAJ7620_INT, INPUT_PULLUP);

    // 2. 快速检测传感器是否在线
    Wire.beginTransmission(I2C_ADDR);
    uint8_t error = Wire.endTransmission();
    if (error != 0) {
        Serial.printf("[PAJ7620] I2C device NOT FOUND at 0x%02X! "
                       "(error=%d)\n", I2C_ADDR, error);
        Serial.println("[PAJ7620] Check wiring & I2C address");
        _initialized = false;
        return false;
    }
    PAJ_LOG("I2C device found at 0x%02X", I2C_ADDR);

    // 3. 唤醒传感器
    if (!_wakeUp()) {
        Serial.println("[PAJ7620] Wake-up failed!");
        _initialized = false;
        return false;
    }
    delay(10);

    uint8_t idLow = 0;
    uint8_t idHigh = 0;
    if (!_readReg(0x00, idLow) || !_readReg(0x01, idHigh)) {
        Serial.println("[PAJ7620] Chip ID read failed");
        _initialized = false;
        return false;
    }

    Serial.printf("[PAJ7620] Chip ID: 0x%02X 0x%02X\n", idHigh, idLow);
    if (idLow != 0x20 || idHigh != 0x76) {
        Serial.println("[PAJ7620] Unexpected chip ID");
        _initialized = false;
        return false;
    }

    // 4. 初始化全部寄存器
    if (!_initRegisters()) {
        Serial.println("[PAJ7620] Register initialization failed!");
        _initialized = false;
        return false;
    }

    _initialized = true;
    Serial.println("[PAJ7620] Initialization successful! "
                   "Gesture sensing enabled.");
    return true;
}

// ============================================================
// readGesture() — 轮询读取手势
// ============================================================
// 通过 I2C 直接读取 Bank 0 的 REG_GESTURE_ID (0x43) 寄存器
// 获取当前识别到的手势 ID。
//
// 防抖逻辑:
//   - 同一手势在 _debounceMs (默认 150ms) 内不会重复触发
//   - 手势变化时立即触发 (无延迟)
//   - GestureType::NONE 不触发防抖
// ============================================================
GestureType Paj7620::readGesture()
{
    if (!_initialized) {
        return GestureType::NONE;
    }

    // 1. 确保选择 Bank 0
    if (!_selectBank(0)) {
        return GestureType::NONE;
    }

    // 2. 读取手势 ID 寄存器 (0x43)
    uint8_t gestureId = 0;
    if (!_readReg(REG_GESTURE_ID, gestureId)) {
        // 读取失败时返回 NONE
        return GestureType::NONE;
    }
    _lastRawGesture = gestureId;

    // 3. 读取手势 ID 扩展寄存器 (0x44) 确认有效性
    uint8_t gestureId2 = 0;
    _readReg(REG_GESTURE_ID2, gestureId2);

    return decodeRawGesture(gestureId, gestureId2);
}

bool Paj7620::readRawGestureRegs(uint8_t& gestureId, uint8_t& gestureId2)
{
    gestureId = 0;
    gestureId2 = 0;

    if (!_initialized) {
        return false;
    }

    if (!_selectBank(0)) {
        return false;
    }

    if (!_readReg(REG_GESTURE_ID, gestureId)) {
        return false;
    }

    if (!_readReg(REG_GESTURE_ID2, gestureId2)) {
        return false;
    }

    return true;
}

GestureType Paj7620::decodeRawGesture(uint8_t gestureId, uint8_t gestureId2)
{
    _lastRawGesture = gestureId ? gestureId : gestureId2;

    GestureType currentGesture = GestureType::NONE;

    if (gestureId & 0x01) {
        currentGesture = GestureType::UP;
    } else if (gestureId & 0x02) {
        currentGesture = GestureType::DOWN;
    } else if (gestureId & 0x04) {
        currentGesture = GestureType::LEFT;
    } else if (gestureId & 0x08) {
        currentGesture = GestureType::RIGHT;
    } else if (gestureId & 0x10) {
        currentGesture = GestureType::FORWARD;
    } else if (gestureId & 0x20) {
        currentGesture = GestureType::BACKWARD;
    } else if (gestureId & 0x40) {
        currentGesture = GestureType::CLOCKWISE;
    } else if (gestureId & 0x80) {
        currentGesture = GestureType::COUNTERCLOCKWISE;
    } else if (gestureId2 & 0x01) {
        currentGesture = GestureType::WAVE;
    }

    if (currentGesture == GestureType::NONE) {
        return GestureType::NONE;
    }

    if (_isDebouncing(currentGesture)) {
        return GestureType::NONE;
    }

    _lastGesture = currentGesture;
    _lastGestureTime = millis();
    return currentGesture;
}

// ============================================================
// readGestureWithInterrupt() — 带中断检测的手势读取
// ============================================================
// 先检查中断引脚 (PIN_PAJ7620_INT) 状态:
//   - 低电平: 有手势触发 → 读取手势寄存器
//   - 高电平: 无手势 → 返回 NONE
//
// 适用于中断驱动的读取模式 (减少 I2C 总线占用)
// ============================================================
GestureType Paj7620::readGestureWithInterrupt()
{
    if (!_initialized) {
        return GestureType::NONE;
    }

    // 检查中断引脚 (PAJ7620 中断为低电平有效)
    if (digitalRead(PIN_PAJ7620_INT) == HIGH) {
        // 无中断触发
        return GestureType::NONE;
    }

    // 有中断, 读取手势
    return readGesture();
}

// ============================================================
// getGestureName() — 获取手势中文名称
// ============================================================
const char* Paj7620::getGestureName(GestureType g)
{
    switch (g) {
        case GestureType::UP:                return "上滑";
        case GestureType::DOWN:              return "下滑";
        case GestureType::LEFT:              return "左滑";
        case GestureType::RIGHT:             return "右滑";
        case GestureType::FORWARD:           return "前推";
        case GestureType::BACKWARD:          return "后拉";
        case GestureType::CLOCKWISE:         return "顺时针";
        case GestureType::COUNTERCLOCKWISE:  return "逆时针";
        case GestureType::WAVE:              return "挥手";
        case GestureType::NONE:
        default:                             return "无手势";
    }
}

// ============================================================
// getGestureNameEN() — 获取手势英文名称
// ============================================================
const char* Paj7620::getGestureNameEN(GestureType g)
{
    switch (g) {
        case GestureType::UP:                return "UP";
        case GestureType::DOWN:              return "DOWN";
        case GestureType::LEFT:              return "LEFT";
        case GestureType::RIGHT:             return "RIGHT";
        case GestureType::FORWARD:           return "FORWARD";
        case GestureType::BACKWARD:          return "BACKWARD";
        case GestureType::CLOCKWISE:         return "CLOCKWISE";
        case GestureType::COUNTERCLOCKWISE:  return "COUNTERCLOCKWISE";
        case GestureType::WAVE:              return "WAVE";
        case GestureType::NONE:
        default:                             return "NONE";
    }
}

// ============================================================
// _writeReg() — 写单字节寄存器
// ============================================================
bool Paj7620::_writeReg(uint8_t reg, uint8_t value)
{
    Wire.beginTransmission(I2C_ADDR);
    Wire.write(reg);
    Wire.write(value);
    uint8_t error = Wire.endTransmission(true);
    return (error == 0);
}

// ============================================================
// _readReg() — 读单字节寄存器
// ============================================================
bool Paj7620::_readReg(uint8_t reg, uint8_t& value)
{
    // 1. 发送要读取的寄存器地址
    Wire.beginTransmission(I2C_ADDR);
    Wire.write(reg);
    uint8_t error = Wire.endTransmission(false);  // 不发送停止条件
    if (error != 0) {
        value = 0;
        return false;
    }

    // 2. 读取 1 个字节
    size_t bytesRead = Wire.requestFrom((uint8_t)I2C_ADDR, (size_t)1, true);
    if (bytesRead < 1) {
        value = 0;
        return false;
    }

    value = Wire.read();
    return true;
}

// ============================================================
// _writeRegs() — 批量写寄存器 (用于初始化)
// ============================================================
bool Paj7620::_writeRegs(const uint8_t regs[][2], size_t count)
{
    for (size_t i = 0; i < count; i++) {
        if (!_writeReg(regs[i][0], regs[i][1])) {
            PAJ_LOG("Batch write failed at index %u: reg=0x%02X, val=0x%02X",
                    i, regs[i][0], regs[i][1]);
            return false;
        }
    }
    return true;
}

// ============================================================
// _selectBank() — 切换寄存器组
// ============================================================
// PAJ7620 使用 Bank 机制组织寄存器:
//   bank=0 -> Bank 0 (手势结果、基本配置)
//   bank=1 -> Bank 1 (灵敏度、阈值等高级配置)
// 通过写 REG_BANK_SEL (0xEF) 寄存器切换
// ============================================================
bool Paj7620::_selectBank(uint8_t bank)
{
    return _writeReg(REG_BANK_SEL, bank);
}

// ============================================================
// _wakeUp() — 唤醒传感器
// ============================================================
// PAJ7620 上电后处于休眠模式, 需要写 0x00 到 REG_SUSPEND (0xFE)
// 使其进入正常工作模式
// ============================================================
bool Paj7620::_wakeUp()
{
    // 先写 0x01 确保进入休眠, 再写 0x00 唤醒 (可靠启动)
    const bool ok = _writeReg(0xFF, 0x00);
    delay(50);
    return ok;
}

// ============================================================
// _initRegisters() — 执行完整初始化序列
// ============================================================
// 按照 PAJ7620U2 数据手册要求的顺序:
//   1. Bank 0 全寄存器初始化 (0x00~0x53 全部写 0x00)
//   2. Bank 1 全寄存器初始化 (0x00~0xFF 全部写 0x00)
//   3. 回到 Bank 0
//   4. 使能各手势检测
// ============================================================
bool Paj7620::_initRegisters()
{
    if (!_writeRegs(SEEED_INIT_REGS, sizeof(SEEED_INIT_REGS) / sizeof(SEEED_INIT_REGS[0]))) {
        Serial.println("[PAJ7620] Seeed init sequence failed");
        return false;
    }

    if (!_selectBank(1)) {
        Serial.println("[PAJ7620] Failed to select Bank 1 for report mode");
        return false;
    }

    if (!_writeReg(0x65, 18)) {
        Serial.println("[PAJ7620] Failed to set near 240FPS report mode");
        return false;
    }

    if (!_selectBank(0)) {
        Serial.println("[PAJ7620] Failed to return to Bank 0");
        return false;
    }

    Serial.println("[PAJ7620] Seeed init sequence complete");
    return true;
}

// ============================================================
// _isDebouncing() — 防抖检测
// ============================================================
// 防抖逻辑:
//   - 如果当前手势与上次不同, 允许立即触发 (返回 false)
//   - 如果当前手势与上次相同, 检查时间间隔
//     - 间隔 >= _debounceMs: 允许触发 (返回 false)
//     - 间隔 <  _debounceMs: 防抖拦截 (返回 true)
//   - NONE 手势不触发防抖
// ============================================================
bool Paj7620::_isDebouncing(GestureType gesture)
{
    // NONE 不触发防抖
    if (gesture == GestureType::NONE) {
        return false;
    }

    // 手势变化: 立即触发 (不回弹)
    if (gesture != _lastGesture) {
        return false;
    }

    // 相同手势: 检查时间窗口
    uint32_t now = millis();
    if (now - _lastGestureTime < _debounceMs) {
        return true;  // 防抖中, 忽略
    }

    return false;
}
