// ============================================================
// PC 串口通信 — 头文件
// USB CDC JSON 发送 + 定时心跳
// ============================================================
#ifndef PC_COMM_H
#define PC_COMM_H

#include <Arduino.h>
#include "privacy_state_machine.h"

class PCComm {
public:
    PCComm();

    // 初始化串口 (USB CDC)
    void begin(long baud = SERIAL_BAUD);

    // 主循环处理: 状态变化发送 + 定时心跳
    void handle(const PrivacyStateMachine& sm, const TargetInfo& info);

    // 强制发送 JSON 状态
    void sendStateJSON(const String& json);

    // 发送心跳 (简化 JSON)
    void sendHeartbeat();

    // 获取串口连接状态
    bool isConnected() const;

    // 上次通信时间戳
    unsigned long getLastCommTime() const { return _lastCommTime; }

private:
    unsigned long _lastStateSendTime;   // 上次发送状态时间
    unsigned long _lastHeartbeatTime;   // 上次心跳时间
    unsigned long _lastCommTime;        // 最后通信时间
    bool          _stateChanged;        // 标记状态已变化待发送
    PrivacyState  _lastSentState;       // 上次发送的状态
};

#endif // PC_COMM_H
