// ============================================================
// ld2410b.cpp �?LD2410B 雷达传感器驱动实�?// 项目：智慧办公防偷窥人体感知系统
// 阶段：Phase 2 �?LD2410B 雷达数据读取
// ============================================================
// 核心设计�?//   1. 字节级状态机逐字节解析，不依�?readString/readBytes
//   2. 帧头 0xF4F3F2F1 检�?-> 长度解析 -> 数据读取 -> 帧尾 0xF8F7F6F5 校验
//   3. 粘包处理：任意字节位置检测到 0xF4 即尝试重新同步帧�?//   4. 半包处理：超�?RADAR_FRAME_TIMEOUT_MS 未收到完整帧则自动重�?//   5. 错帧处理：任何预期字节不匹配立即回到 PARSER_WAIT_F4
// ============================================================

#include "ld2410b.h"
#include "config.h"
#include <string.h>  // memcpy

// ============================================================
// 构�?/ 析构
// ============================================================
LD2410B::LD2410B()
    : _serial(nullptr)
    , _state(PARSER_WAIT_F4)
    , _frame_count(0)
    , _buf_index(0)
    , _frame_len(0)
    , _last_byte_time(0)
    , _new_data_flag(false)
    , _cfg_index(0)
{
    // 初始化目标信�?    memset(&_info, 0, sizeof(_info));
    _info.valid = false;
}

LD2410B::~LD2410B()
{
    // �?}

// ============================================================
// 初始�?UART2 (256000 8N1)
// ============================================================
bool LD2410B::begin(HardwareSerial* serial)
{
    if (serial == nullptr)
    {
        serial = &Serial2;  // 默认使用 UART2
    }
    _serial = serial;

    // ----- 配置 UART2 引脚并启�?-----
    // PIN_RADAR_TX (GPIO10) -> ESP32 RX2 (接收雷达数据)
    // PIN_RADAR_RX (GPIO11) -> ESP32 TX2 (发送配置命令给雷达)
    // 引脚号在 config.h 中已确认 (confirmed from schematic/netlist)
    // 分配接收缓冲�?(避免默认缓冲区过小丢失数�?
    _serial->setRxBufferSize(RADAR_UART_RX_BUF);

    _serial->begin(RADAR_UART_BAUD, SERIAL_8N1, PIN_RADAR_TX, PIN_RADAR_RX);

    // 重置解析器状�?    resetParser();

    Serial.printf("[LD2410B] UART2 initialized: %d baud 8N1, RX=GPIO%d, TX=GPIO%d\n",
                  RADAR_UART_BAUD, PIN_RADAR_TX, PIN_RADAR_RX);

    return true;
}

// ============================================================
// 重置解析�?// ============================================================
void LD2410B::resetParser()
{
    _state       = PARSER_WAIT_F4;
    _buf_index   = 0;
    _frame_len   = 0;
    _cfg_index   = 0;
    _last_byte_time = 0;
}

// ============================================================
// 字节级状态机核心
// ============================================================
// 状态转移图 (上报�?:
//
//   PARSER_WAIT_F4 --(0xF4)--> PARSER_GOT_F4
//   PARSER_GOT_F4  --(0xF3)--> PARSER_GOT_F3
//                   --(0xF4)--> PARSER_GOT_F4    (粘包：连�?xF4, 重新同步)
//                   --(else)--> PARSER_WAIT_F4   (错帧重置)
//   PARSER_GOT_F3  --(0xF2)--> PARSER_GOT_F2
//                   --(0xF4)--> PARSER_GOT_F4    (部分粘包恢复)
//                   --(else)--> PARSER_WAIT_F4
//   PARSER_GOT_F2  --(0xF1)--> PARSER_WAIT_LEN_L (帧头完整!)
//                   --(0xF4)--> PARSER_GOT_F4
//                   --(else)--> PARSER_WAIT_F4
//   PARSER_WAIT_LEN_L  ------> PARSER_WAIT_LEN_H
//   PARSER_WAIT_LEN_H  ------> PARSER_WAIT_DATA  (长度检查通过)
//                         --(invalid)--> PARSER_WAIT_F4
//   PARSER_WAIT_DATA   ------> PARSER_WAIT_F8    (数据收齐)
//   PARSER_WAIT_F8 --(0xF8)--> PARSER_GOT_F8
//                   --(else)--> PARSER_WAIT_F4    (帧尾不匹�?
//   PARSER_GOT_F8  --(0xF7)--> PARSER_GOT_F7
//                   --(else)--> PARSER_WAIT_F4
//   PARSER_GOT_F7  --(0xF6)--> PARSER_GOT_F6
//                   --(else)--> PARSER_WAIT_F4
//   PARSER_GOT_F6  --(0xF5)--> [帧完成] -> PARSER_WAIT_F4
//                   --(else)--> PARSER_WAIT_F4
//
// 配置帧走另一分支: PARSER_CFG_GOT_FD -> ... -> PARSER_CFG_GOT_02
// ============================================================
void LD2410B::feed(uint8_t byte)
{
    uint32_t now = millis();

    // ---- 半包检�? 距离上次字节超过超时则重�?----
    // 当状态处于帧解析�?(非初始等待�? 但超时无数据, 视为半包丢弃
    if (_state != PARSER_WAIT_F4 &&
        _state != PARSER_CFG_GOT_FD &&
        now - _last_byte_time > RADAR_FRAME_TIMEOUT_MS)
    {
        // 超时重置 �?防止残帧永远卡住状态机
        Serial.printf("[LD2410B] Frame timeout (state=%d), resetting parser\n",
                      static_cast<int>(_state));
        resetParser();
    }
    _last_byte_time = now;

    // ========================================================
    // 主状态机 (Switch-Case)
    // ========================================================
    switch (_state)
    {
    // ==================== 上报帧头检�?====================
    case PARSER_WAIT_F4:
        if (byte == LD2410B_REPORT_HEADER_B0)
        {
            _state = PARSER_GOT_F4;
        }
        else if (byte == LD2410B_CFG_HEADER_B0)
        {
            // 检测到配置帧起�?            _state = PARSER_CFG_GOT_FD;
            _cfg_index = 0;
        }
        // 其他字节忽略 (保持等待)
        break;

    case PARSER_GOT_F4:
        if (byte == LD2410B_REPORT_HEADER_B1)
        {
            _state = PARSER_GOT_F3;
        }
        else if (byte == LD2410B_REPORT_HEADER_B0)
        {
            // 连续 F4: 粘包场景, 保持 GOT_F4 (重新同步)
            _state = PARSER_GOT_F4;
        }
        else
        {
            _state = PARSER_WAIT_F4;  // 错帧重置
        }
        break;

    case PARSER_GOT_F3:
        if (byte == LD2410B_REPORT_HEADER_B2)
        {
            _state = PARSER_GOT_F2;
        }
        else if (byte == LD2410B_REPORT_HEADER_B0)
        {
            _state = PARSER_GOT_F4;  // 部分粘包恢复
        }
        else
        {
            _state = PARSER_WAIT_F4;
        }
        break;

    case PARSER_GOT_F2:
        if (byte == LD2410B_REPORT_HEADER_B3)
        {
            // 帧头完整! 进入长度读取
            _state = PARSER_WAIT_LEN_L;
        }
        else if (byte == LD2410B_REPORT_HEADER_B0)
        {
            _state = PARSER_GOT_F4;
        }
        else
        {
            _state = PARSER_WAIT_F4;
        }
        break;

    // ==================== 长度字段解析 ====================
    case PARSER_WAIT_LEN_L:
        _frame_len = byte;               // 长度低字�?        _state = PARSER_WAIT_LEN_H;
        break;

    case PARSER_WAIT_LEN_H:
        _frame_len |= ((uint16_t)byte << 8);  // 长度高字�?        // 检查长度合理�? 基础数据9字节, 工程模式下更�?        if (_frame_len < LD2410B_REPORT_DATA_LEN || _frame_len > sizeof(_buf))
        {
            // 长度异常, 丢弃
            Serial.printf("[LD2410B] Invalid frame len=%u\n", _frame_len);
            _state = PARSER_WAIT_F4;
        }
        else
        {
            _buf_index = 0;
            _state = PARSER_WAIT_DATA;
        }
        break;

    // ==================== 数据负载读取 ====================
    case PARSER_WAIT_DATA:
        if (_buf_index < sizeof(_buf))
        {
            _buf[_buf_index++] = byte;
        }
        // 数据收齐? (帧长度可能包含工程模式的额外数据)
        if (_buf_index >= _frame_len)
        {
            _state = PARSER_WAIT_F8;  // 切换到帧尾检�?        }
        break;

    // ==================== 上报帧帧尾校�?====================
    case PARSER_WAIT_F8:
        if (byte == LD2410B_REPORT_TAIL_B0)
        {
            _state = PARSER_GOT_F8;
        }
        else
        {
            // 帧尾不匹�? 丢弃整帧
            Serial.printf("[LD2410B] Tail mismatch: expected 0xF8, got 0x%02X\n", byte);
            _state = PARSER_WAIT_F4;
        }
        break;

    case PARSER_GOT_F8:
        if (byte == LD2410B_REPORT_TAIL_B1)
        {
            _state = PARSER_GOT_F7;
        }
        else
        {
            _state = PARSER_WAIT_F4;
        }
        break;

    case PARSER_GOT_F7:
        if (byte == LD2410B_REPORT_TAIL_B2)
        {
            _state = PARSER_GOT_F6;
        }
        else
        {
            _state = PARSER_WAIT_F4;
        }
        break;

    case PARSER_GOT_F6:
        if (byte == LD2410B_REPORT_TAIL_B3)
        {
            // ================================================
            // 帧完�? 处理数据
            // ================================================
            processReportFrame(_buf, _frame_len);
            _frame_count++;
            _state = PARSER_WAIT_F4;  // 回到初始�? 准备下一�?        }
        else
        {
            _state = PARSER_WAIT_F4;
        }
        break;

    // ==================== 配置帧解�?(基础支持) ====================
    case PARSER_CFG_GOT_FD:
        if (byte == LD2410B_CFG_HEADER_B1)      _state = PARSER_CFG_GOT_FC;
        else if (byte == LD2410B_CFG_HEADER_B0) _state = PARSER_CFG_GOT_FD;  // 粘包
        else                                     _state = PARSER_WAIT_F4;
        break;

    case PARSER_CFG_GOT_FC:
        if (byte == LD2410B_CFG_HEADER_B2)      _state = PARSER_CFG_GOT_FB;
        else if (byte == LD2410B_CFG_HEADER_B0) _state = PARSER_CFG_GOT_FD;
        else                                     _state = PARSER_WAIT_F4;
        break;

    case PARSER_CFG_GOT_FB:
        if (byte == LD2410B_CFG_HEADER_B3)      _state = PARSER_CFG_WAIT_LEN_L;
        else if (byte == LD2410B_CFG_HEADER_B0) _state = PARSER_CFG_GOT_FD;
        else                                     _state = PARSER_WAIT_F4;
        break;

    case PARSER_CFG_WAIT_LEN_L:
        _frame_len = byte;
        _state = PARSER_CFG_WAIT_LEN_H;
        break;

    case PARSER_CFG_WAIT_LEN_H:
        _frame_len |= ((uint16_t)byte << 8);
        if (_frame_len == 0 || _frame_len > sizeof(_cfg_buf))
        {
            _state = PARSER_WAIT_F4;
        }
        else
        {
            _cfg_index = 0;
            _state = PARSER_CFG_WAIT_DATA;
        }
        break;

    case PARSER_CFG_WAIT_DATA:
        if (_cfg_index < sizeof(_cfg_buf))
            _cfg_buf[_cfg_index++] = byte;
        if (_cfg_index >= _frame_len)
            _state = PARSER_CFG_WAIT_04;
        break;

    case PARSER_CFG_WAIT_04:
        if (byte == LD2410B_CFG_TAIL_B0)        _state = PARSER_CFG_GOT_04;
        else                                     _state = PARSER_WAIT_F4;
        break;

    case PARSER_CFG_GOT_04:
        if (byte == LD2410B_CFG_TAIL_B1)        _state = PARSER_CFG_GOT_03;
        else                                     _state = PARSER_WAIT_F4;
        break;

    case PARSER_CFG_GOT_03:
        if (byte == LD2410B_CFG_TAIL_B2)        _state = PARSER_CFG_GOT_02;
        else                                     _state = PARSER_WAIT_F4;
        break;

    case PARSER_CFG_GOT_02:
        if (byte == LD2410B_CFG_TAIL_B3)
        {
            // 配置帧完�?            processConfigFrame(_cfg_buf, _frame_len);
            _state = PARSER_WAIT_F4;
        }
        else
        {
            _state = PARSER_WAIT_F4;
        }
        break;

    // ---- 防御: 未知状�?-> 重置 ----
    default:
        resetParser();
        break;
    }
}

// ============================================================
// �?UART 读取所有可用数据并送入状态机
// ============================================================
void LD2410B::update()
{
    if (_serial == nullptr) return;

    // 逐字节读�? 每次读取全部可用数据
    while (_serial->available() > 0)
    {
        uint8_t byte = _serial->read();
        feed(byte);

        // 串口打印原始字节 (调试�? 可注释掉)
        // Serial.printf("%02X ", byte);
    }
}

// ============================================================
// 检查是否有新数�?// ============================================================
bool LD2410B::hasNewData()
{
    bool flag = _new_data_flag;
    _new_data_flag = false;
    return flag;
}

// ============================================================
// 处理上报帧数�?// ============================================================
// 上报帧数据格�?(基础模式, 9字节):
//   [0] target_state      : 1B  (0=�? 1=运动, 2=静止, 3=运动+静止)
//   [1-2] moving_dist     : 2B LE (mm)
//   [3] moving_energy     : 1B  (0~100)
//   [4-5] static_dist     : 2B LE (mm)
//   [6] static_energy     : 1B  (0~100)
//   [7-8] detect_dist     : 2B LE (mm)
//
// 工程模式附加更多传感器数�? 但目标字段布局不变�?// ============================================================
void LD2410B::processReportFrame(const uint8_t* data, uint16_t len)
{
    // Both basic (0x02) and engineering (0x01) reports carry the same
    // target fields at offsets 2..10. Engineering reports are longer.
    if (len < 13) return;

    const bool knownReportType = data[0] == 0x01 || data[0] == 0x02;
    const bool validPayloadMarkers = knownReportType &&
                                     data[1] == 0xAA &&
                                     data[len - 2] == 0x55 &&
                                     data[len - 1] == 0x00;
    if (!validPayloadMarkers)
    {
        Serial.printf("[LD2410B] Invalid report payload markers: type=%02X head=%02X tail=%02X %02X len=%u\n",
                      data[0], data[1], data[len - 2], data[len - 1], len);
        return;
    }

    // 解析数据 (LE = Little Endian)
    _info.target_state  = data[2];
    _info.moving_dist   = (data[3] | ((uint16_t)data[4] << 8)) * 10;
    _info.moving_energy = data[5];
    _info.static_dist   = (data[6] | ((uint16_t)data[7] << 8)) * 10;
    _info.static_energy = data[8];
    _info.detect_dist   = (data[9] | ((uint16_t)data[10] << 8)) * 10;

    // Engineering-mode extension: retain raw per-gate energies only.
    _info.engineering_data = false;
    _info.moving_gate_count = 0;
    _info.static_gate_count = 0;
    memset(_info.moving_gate_energy, 0, sizeof(_info.moving_gate_energy));
    memset(_info.static_gate_energy, 0, sizeof(_info.static_gate_energy));
    _info.light_level = 0;
    _info.out_state = 0;

    if (data[0] == 0x01 && len >= 17)
    {
        const uint8_t movingCount = data[11] < LD2410B_MAX_GATE_COUNT
            ? static_cast<uint8_t>(data[11] + 1U) : LD2410B_MAX_GATE_COUNT;
        const uint8_t staticCount = data[12] < LD2410B_MAX_GATE_COUNT
            ? static_cast<uint8_t>(data[12] + 1U) : LD2410B_MAX_GATE_COUNT;
        const uint16_t requiredLen = static_cast<uint16_t>(17U + movingCount + staticCount);

        if (len >= requiredLen)
        {
            uint16_t offset = 13;
            _info.engineering_data = true;
            _info.moving_gate_count = movingCount;
            _info.static_gate_count = staticCount;
            for (uint8_t gate = 0; gate < movingCount; ++gate)
                _info.moving_gate_energy[gate] = data[offset++];
            for (uint8_t gate = 0; gate < staticCount; ++gate)
                _info.static_gate_energy[gate] = data[offset++];
            _info.light_level = data[offset++];
            _info.out_state = data[offset];
        }
    }
    _info.timestamp     = millis();
    _info.valid         = true;
    _new_data_flag      = true;

    // ---- 串口打印解析结果 (调试) ----
#if 0
    // Per-frame verbose log. Keep disabled during normal bring-up to avoid flooding USB CDC.
    const char* state_str = "UNKNOWN";
    switch (_info.target_state)
    {
    case LD2410B_TARGET_NONE:   state_str = "NO_TARGET";  break;
    case LD2410B_TARGET_MOVING: state_str = "MOVING";     break;
    case LD2410B_TARGET_STATIC: state_str = "STATIC";     break;
    case LD2410B_TARGET_BOTH:   state_str = "BOTH";       break;
    }

    Serial.printf("[RADAR] Frame#%u | State=%s | Moving=%ucm(%u%%) | Static=%ucm(%u%%) | Detect=%ucm\n",
                  _frame_count,
                  state_str,
                  _info.moving_dist / 10,  _info.moving_energy,   // mm -> cm
                  _info.static_dist / 10,  _info.static_energy,   // mm -> cm
                  _info.detect_dist / 10);
#endif
}

// ============================================================
// 处理配置帧响�?(基础日志)
// ============================================================
void LD2410B::processConfigFrame(const uint8_t* data, uint16_t len)
{
    Serial.printf("[RADAR CFG] Response len=%u: ", len);
    for (uint16_t i = 0; i < len && i < 16; i++)
    {
        Serial.printf("%02X ", data[i]);
    }
    Serial.println();
}

// ============================================================
// 发送配置命�?// ============================================================
// 配置帧格�?
//   FD FC FB FA [Len_L] [Len_H] [Cmd/Data...] 04 03 02 01
// ============================================================
void LD2410B::sendCommand(const uint8_t* cmd, uint16_t len)
{
    if (_serial == nullptr) return;

    _serial->write(cmd, len);
    _serial->flush();

    Serial.print("[LD2410B] CMD sent: ");
    for (uint16_t i = 0; i < len; i++)
    {
        Serial.printf("%02X ", cmd[i]);
    }
    Serial.println();
}

// ============================================================
// 使能配置模式
// ============================================================
// 命令: FD FC FB FA 04 00 FF FF 00 01 04 03 02 01
//   Len=4, Cmd=0xFFFF (使能), Data=00 01 (enable)
// ============================================================
void LD2410B::enableConfig()
{
    const uint8_t cmd[] = {
        0xFD, 0xFC, 0xFB, 0xFA,
        0x04, 0x00,
        0xFF, 0x00,
        0x01, 0x00,
        0x04, 0x03, 0x02, 0x01
    };
    sendCommand(cmd, sizeof(cmd));
}

// ============================================================
// 退出配置模�?// ============================================================
// 命令: FD FC FB FA 04 00 FF FF 00 00 04 03 02 01
//   Data=00 00 (disable)
// ============================================================
void LD2410B::disableConfig()
{
    const uint8_t cmd[] = {
        0xFD, 0xFC, 0xFB, 0xFA,
        0x02, 0x00,
        0xFE, 0x00,
        0x04, 0x03, 0x02, 0x01
    };
    sendCommand(cmd, sizeof(cmd));
}

// ============================================================
// 读取固件版本
// ============================================================
// 命令: FD FC FB FA 04 00 00 00 A0 00 04 03 02 01
//   Read register 0x00A0 (版本信息)
// ============================================================
void LD2410B::readVersion()
{
    uint8_t cmd[] = {
        0xFD, 0xFC, 0xFB, 0xFA,
        0x04, 0x00,
        0x00, 0x00,              // 读命�?        0xA0, 0x00,              // 寄存器地址: 版本
        0x04, 0x03, 0x02, 0x01
    };
    sendCommand(cmd, sizeof(cmd));
}

// ============================================================
// 设置工程模式
// ============================================================
// 命令: FD FC FB FA 05 00 01 00 A1 00 01 04 03 02 01
//   Write register 0x00A1 (工程模式), value=0x01 (enable)
// ============================================================
void LD2410B::setEngineeringMode(bool enable)
{
    const uint8_t command = enable ? 0x62 : 0x63;
    const uint8_t cmd[] = {
        0xFD, 0xFC, 0xFB, 0xFA,
        0x02, 0x00,
        command, 0x00,
        0x04, 0x03, 0x02, 0x01
    };
    sendCommand(cmd, sizeof(cmd));
}

// ============================================================
// 设置探测灵敏�?// ============================================================
void LD2410B::setSensitivity(uint8_t sensitivity)
{
    // 灵敏度设置通常通过写寄存器 0x00AA (或类�? 实现
    // 具体寄存器地址需查阅 LD2410B 数据手册
    Serial.printf("[LD2410B] setSensitivity(%u) �?TODO: implement with correct register\n",
                  sensitivity);
}
