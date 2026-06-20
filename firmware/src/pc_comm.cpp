// ============================================================
// PC 串口通信 — 实现
// USB CDC JSON 发送 + 定时心跳
// ============================================================
#include "pc_comm.h"
#include "config.h"

PCComm::PCComm()
    : _lastStateSendTime(0)
    , _lastHeartbeatTime(0)
    , _lastCommTime(0)
    , _stateChanged(false)
    , _lastSentState(PrivacyState::NORMAL)
{}

void PCComm::begin(long baud) {
    Serial.begin(baud);
    // 等待串口稳定
    delay(100);
}

bool PCComm::isConnected() const {
    // USB CDC 连接检测: Serial 对象在连接时可用
    // 对于 ESP32-S3 with USB CDC, Serial 始终可用
    // 但我们可以通过 DTR 信号检测
    return true; // USB CDC 始终可用
}

void PCComm::handle(const PrivacyStateMachine& sm, const TargetInfo& info) {
    unsigned long now = millis();

    // ---- 检测状态变化 ----
    PrivacyState currentState = sm.getState();
    if (currentState != _lastSentState) {
        _stateChanged = true;
    }

    // ---- 状态变化时立即发送 ----
    if (_stateChanged) {
        String json = sm.getStateJSON(info);
        sendStateJSON(json);
        _lastSentState = currentState;
        _stateChanged = false;
        _lastStateSendTime = now;
        _lastCommTime = now;
    }

    // ---- 定时心跳 ----
    if (now - _lastHeartbeatTime >= PC_HEARTBEAT_MS) {
        sendHeartbeat();
        _lastHeartbeatTime = now;
        _lastCommTime = now;
    }
}

void PCComm::sendStateJSON(const String& json) {
    Serial.println(json);
    Serial.flush();
}

void PCComm::sendHeartbeat() {
    // 心跳 JSON (轻量)
    String hb = "{";
    hb += "\"type\":\"heartbeat\",";
    hb += "\"timestamp_ms\":";
    hb += millis();
    hb += ",\"uptime_s\":";
    hb += millis() / 1000;
    hb += "}";
    Serial.println(hb);
    Serial.flush();
}
