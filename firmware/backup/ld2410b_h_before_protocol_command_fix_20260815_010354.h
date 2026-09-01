// ============================================================
// ld2410b.h �?LD2410B 雷达传感器驱动头文件
// 项目：智慧办公防偷窥人体感知系统
// 阶段：Phase 2 �?LD2410B 雷达数据读取
// ============================================================
// 功能说明�?//   1. 字节级状态机解析 LD2410B 上报�?(F4F3F2F1 ... F8F7F6F5)
//   2. 支持粘包/半包/错帧恢复
//   3. UART2 初始�?(256000 8N1)
//   4. 配置命令发�?(使能配置/读取版本/工程模式)
// ============================================================
#ifndef LD2410B_H
#define LD2410B_H

#include <Arduino.h>
#include <stdint.h>

// ============================================================
// 协议常量
// ============================================================
// 上报�?(雷达主动上报目标数据)
#define LD2410B_REPORT_HEADER_B0  0xF4
#define LD2410B_REPORT_HEADER_B1  0xF3
#define LD2410B_REPORT_HEADER_B2  0xF2
#define LD2410B_REPORT_HEADER_B3  0xF1
#define LD2410B_REPORT_TAIL_B0    0xF8
#define LD2410B_REPORT_TAIL_B1    0xF7
#define LD2410B_REPORT_TAIL_B2    0xF6
#define LD2410B_REPORT_TAIL_B3    0xF5

// 配置�?(主机<->雷达双向)
#define LD2410B_CFG_HEADER_B0     0xFD
#define LD2410B_CFG_HEADER_B1     0xFC
#define LD2410B_CFG_HEADER_B2     0xFB
#define LD2410B_CFG_HEADER_B3     0xFA
#define LD2410B_CFG_TAIL_B0       0x04
#define LD2410B_CFG_TAIL_B1       0x03
#define LD2410B_CFG_TAIL_B2       0x02
#define LD2410B_CFG_TAIL_B3       0x01

// 目标状态�?#define LD2410B_TARGET_NONE       0x00  // 无目�?#define LD2410B_TARGET_MOVING     0x01  // 运动目标
#define LD2410B_TARGET_STATIC     0x02  // 静止目标
#define LD2410B_TARGET_BOTH       0x03  // 运动 + 静止目标

// 上报帧基础数据长度 (不含帧头/帧尾/长度字段)
#define LD2410B_REPORT_DATA_LEN   9     // state(1) + moving_dist(2) + moving_energy(1)
                                       // + static_dist(2) + static_energy(1) + detect_dist(2)
#define LD2410B_MAX_GATE_COUNT    9     // Gate 0 through gate 8

// ============================================================
// 数据结构
// ============================================================

/**
 * @brief LD2410B 雷达目标信息结构�? *        由解析层填充，供上层状态机使用
 */
struct LD2410B_TargetInfo {
    uint8_t  target_state;      // 目标状�? 0=�? 1=运动, 2=静止, 3=运动+静止
    uint16_t moving_dist;       // 运动目标距离 (mm)
    uint8_t  moving_energy;     // 运动目标能量 (0~100)
    uint16_t static_dist;       // 静止目标距离 (mm)
    uint8_t  static_energy;     // 静止目标能量 (0~100)
    uint16_t detect_dist;       // 探测距离 (mm)
    bool     engineering_data;
    uint8_t  moving_gate_count;
    uint8_t  static_gate_count;
    uint8_t  moving_gate_energy[LD2410B_MAX_GATE_COUNT];
    uint8_t  static_gate_energy[LD2410B_MAX_GATE_COUNT];
    uint8_t  light_level;
    uint8_t  out_state;
    uint32_t timestamp;         // 最近一次有效帧时间�?(ms)
    bool     valid;             // 当前数据是否有效 (true=雷达数据已更�?
};

/**
 * @brief 字节解析状态机枚举
 *        采用显式状态机逐字节解析，支持粘包/半包恢复
 */
enum LD2410B_ParserState : uint8_t {
    // ---- 上报帧解�?----
    PARSER_WAIT_F4 = 0,         // 等待上报帧头字节0: 0xF4
    PARSER_GOT_F4,              // 已收0xF4, 等待0xF3
    PARSER_GOT_F3,              // 已收0xF4F3, 等待0xF2
    PARSER_GOT_F2,              // 已收0xF4F3F2, 等待0xF1
    PARSER_WAIT_LEN_L,          // 已收帧头, 等待长度低字�?    PARSER_WAIT_LEN_H,          // 已收长度�? 等待长度高字�?    PARSER_WAIT_DATA,           // 正在读取数据负载
    PARSER_WAIT_F8,             // 数据读完, 等待帧尾0xF8
    PARSER_GOT_F8,              // 已收0xF8, 等待0xF7
    PARSER_GOT_F7,              // 已收0xF8F7, 等待0xF6
    PARSER_GOT_F6,              // 已收0xF8F7F6, 等待0xF5

    // ---- 配置帧解�?(补充支持) ----
    PARSER_CFG_GOT_FD,          // 已收0xFD (配置帧起�?, 等待0xFC
    PARSER_CFG_GOT_FC,          // 已收0xFDFC, 等待0xFB
    PARSER_CFG_GOT_FB,          // 已收0xFDFCFB, 等待0xFA
    PARSER_CFG_WAIT_LEN_L,      // 已收配置帧头, 等待长度�?    PARSER_CFG_WAIT_LEN_H,      // 等待长度�?    PARSER_CFG_WAIT_DATA,       // 读取配置帧负�?    PARSER_CFG_WAIT_04,         // 等待配置帧尾0x04
    PARSER_CFG_GOT_04,          // 已收0x04, 等待0x03
    PARSER_CFG_GOT_03,          // 已收0x0403, 等待0x02
    PARSER_CFG_GOT_02,          // 已收0x040302, 等待0x01
};

// ============================================================
// LD2410B 驱动�?// ============================================================
class LD2410B {
public:
    LD2410B();
    ~LD2410B();

    // ============================================================
    // 初始�?& 周期调用
    // ============================================================

    /**
     * @brief 初始�?UART2 并重置解析器
     * @param serial 可�? 指定 HardwareSerial 实例 (默认 &Serial2)
     * @return true  初始化成�?     */
    bool begin(HardwareSerial* serial = nullptr);

    /**
     * @brief 向解析器送入一个字�?(字节级状态机)
     * @param byte �?UART 读取的原始字�?     */
    void feed(uint8_t byte);

    /**
     * @brief �?UART 读取所有可用数据并送入解析�?     *        需�?loop() 中高频调�?     */
    void update();

    // ============================================================
    // 数据获取
    // ============================================================

    /**
     * @brief 获取最新解析的雷达目标信息 (const 引用)
     */
    const LD2410B_TargetInfo& getTargetInfo() const { return _info; }

    /**
     * @brief 获取当前解析器状�?(调试�?
     */
    LD2410B_ParserState getParserState() const { return _state; }

    /**
     * @brief 获取收到有效帧的总数
     */
    uint32_t getFrameCount() const { return _frame_count; }

    /**
     * @brief 检查雷达是否有新数�?(调用后自动清除标�?
     * @return true  有新的目标数�?     */
    bool hasNewData();

    // ============================================================
    // 配置命令发�?(通过 UART)
    // ============================================================

    /**
     * @brief 使能配置模式 (发�?0xFF 0xFF 0x00 0x01)
     *        配置命令必须在使能配置后才有�?     */
    void enableConfig();

    /**
     * @brief 退出配置模�?     */
    void disableConfig();

    /**
     * @brief 读取雷达固件版本
     */
    void readVersion();

    /**
     * @brief 设置/关闭工程模式
     * @param enable true=开启工程模�?(更多数据), false=关闭
     */
    void setEngineeringMode(bool enable);

    /**
     * @brief 设置探测灵敏�?(如需)
     * @param sensitivity 灵敏度�?     */
    void setSensitivity(uint8_t sensitivity);

private:
    // ============================================================
    // 内部方法
    // ============================================================

    /** 重置状态机到初始状�?*/
    void resetParser();

    /**
     * @brief 处理一帧完整的上报数据
     * @param data 帧数据负�?(不含帧头/长度/帧尾)
     * @param len  负载长度
     */
    void processReportFrame(const uint8_t* data, uint16_t len);

    /**
     * @brief 处理一帧完整的配置响应数据
     * @param data 帧数据负�?     * @param len  负载长度
     */
    void processConfigFrame(const uint8_t* data, uint16_t len);

    /** 发送原始配置命�?*/
    void sendCommand(const uint8_t* cmd, uint16_t len);

    // ============================================================
    // 成员变量
    // ============================================================

    HardwareSerial*     _serial;            // UART 对象指针
    LD2410B_ParserState _state;             // 当前状态机状�?    LD2410B_TargetInfo  _info;              // 最新解析结�?    uint32_t            _frame_count;       // 成功解析帧计数器

    // ---- 帧接收缓冲区 ----
    uint8_t             _buf[128];          // 数据负载缓冲�?    uint16_t            _buf_index;         // 当前缓冲区写入位�?    uint16_t            _frame_len;         // 预期负载长度 (从帧中解�?

    // ---- 半包超时 ----
    uint32_t            _last_byte_time;    // 上次收到字节的时间戳 (ms)

    // ---- 新数据标�?----
    bool                _new_data_flag;

    // ---- 配置帧缓�?----
    uint8_t             _cfg_buf[64];       // 配置帧负载缓冲区
    uint16_t            _cfg_index;         // 配置帧缓冲区索引
};

#endif // LD2410B_H
