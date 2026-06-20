#include "privacy_state_machine.h"

static constexpr uint16_t HUMAN_NEAR_MM = 1500;
static constexpr uint16_t SUSPECT_NEAR_MM = 900;
static constexpr uint16_t PROTECT_NEAR_MM = 800;
static constexpr uint32_t SUSPECT_HOLD_MS = 2000;
static constexpr uint32_t PROTECT_HOLD_MS = 3500;
static constexpr uint32_t DOWNGRADE_HOLD_MS = 2000;
static constexpr uint32_t PROTECT_MIN_HOLD_MS = 5000;
static constexpr uint32_t STATE_CLEAR_MS = 2000;

static uint8_t stateRank(PrivacyState state)
{
    return static_cast<uint8_t>(state);
}

const char* privacyStateToCN(PrivacyState state)
{
    switch (state) {
    case PrivacyState::NORMAL:
        return "正常";
    case PrivacyState::HUMAN_DETECTED:
        return "有人";
    case PrivacyState::APPROACHING:
        return "接近";
    case PrivacyState::SUSPECTED_PEEPING:
        return "疑似偷窥";
    case PrivacyState::PRIVACY_PROTECT:
        return "隐私保护";
    case PrivacyState::ALARM:
        return "报警";
    default:
        return "未知";
    }
}

const char* privacyStateToEN(PrivacyState state)
{
    switch (state) {
    case PrivacyState::NORMAL:
        return "NORMAL";
    case PrivacyState::HUMAN_DETECTED:
        return "HUMAN_DETECTED";
    case PrivacyState::APPROACHING:
        return "APPROACHING";
    case PrivacyState::SUSPECTED_PEEPING:
        return "SUSPECTED_PEEPING";
    case PrivacyState::PRIVACY_PROTECT:
        return "PRIVACY_PROTECT";
    case PrivacyState::ALARM:
        return "ALARM";
    default:
        return "UNKNOWN";
    }
}

const char* radarTrendToEN(RadarTrend trend)
{
    switch (trend) {
    case RadarTrend::APPROACHING:
        return "APPROACHING";
    case RadarTrend::LEAVING:
        return "LEAVING";
    case RadarTrend::STABLE:
        return "STABLE";
    case RadarTrend::NONE:
        return "NONE";
    default:
        return "UNKNOWN";
    }
}

PrivacyStateMachine::PrivacyStateMachine()
    : _state(PrivacyState::NORMAL),
      _prevState(PrivacyState::NORMAL),
      _stateEnterTime(0),
      _nearSinceTime(0),
      _suspectSinceTime(0),
      _noTargetSinceTime(0),
      _downgradeSinceTime(0),
      _sensitivity(SENSITIVITY_FACTOR)
{
}

PrivacyState PrivacyStateMachine::update(const TargetInfo& info)
{
    const bool present = _hasTarget(info);
    const uint16_t primaryDistanceMm = present ? _primaryDistanceMm(info) : 0;
    return update(info, RadarTrend::UNKNOWN, primaryDistanceMm, present);
}

PrivacyState PrivacyStateMachine::update(const TargetInfo& info,
                                         RadarTrend trend,
                                         uint16_t averageDistanceMm,
                                         bool present)
{
    const uint32_t now = millis();
    _prevState = _state;

    if (!present || !_hasTarget(info)) {
        if (_noTargetSinceTime == 0) {
            _noTargetSinceTime = now;
        }

        if (now - _noTargetSinceTime >= STATE_CLEAR_MS) {
            _setState(PrivacyState::NORMAL, now);
            _nearSinceTime = 0;
            _suspectSinceTime = 0;
            _downgradeSinceTime = 0;
        }

        return _state;
    }

    _noTargetSinceTime = 0;

    if (averageDistanceMm == 0) {
        averageDistanceMm = _primaryDistanceMm(info);
    }

    const bool near = averageDistanceMm > 0 && averageDistanceMm <= _thresholdMm(HUMAN_NEAR_MM);
    const bool suspectNear = averageDistanceMm > 0 && averageDistanceMm <= _thresholdMm(SUSPECT_NEAR_MM);
    const bool protectNear = averageDistanceMm > 0 && averageDistanceMm <= _thresholdMm(PROTECT_NEAR_MM);
    const bool protectLocked = _state == PrivacyState::PRIVACY_PROTECT &&
                               _stateEnterTime > 0 &&
                               now - _stateEnterTime < PROTECT_MIN_HOLD_MS;

    if (!near) {
        _nearSinceTime = 0;
        _suspectSinceTime = 0;

        if (stateRank(_state) <= stateRank(PrivacyState::HUMAN_DETECTED)) {
            _setState(PrivacyState::HUMAN_DETECTED, now);
        } else if (!protectLocked) {
            if (_downgradeSinceTime == 0) {
                _downgradeSinceTime = now;
            }

            if (now - _downgradeSinceTime >= DOWNGRADE_HOLD_MS) {
                _setState(PrivacyState::HUMAN_DETECTED, now);
            }
        }

        return _state;
    }

    if (_nearSinceTime == 0) {
        _nearSinceTime = now;
    }

    if (_state == PrivacyState::NORMAL) {
        _setState(PrivacyState::HUMAN_DETECTED, now);
    }

    if (stateRank(_state) < stateRank(PrivacyState::SUSPECTED_PEEPING)) {
        _downgradeSinceTime = 0;
    }

    if (trend == RadarTrend::APPROACHING &&
        stateRank(_state) < stateRank(PrivacyState::APPROACHING)) {
        _setState(PrivacyState::APPROACHING, now);
    }

    if (suspectNear) {
        _downgradeSinceTime = 0;

        if (_suspectSinceTime == 0) {
            _suspectSinceTime = now;
        }

        if (now - _suspectSinceTime >= SUSPECT_HOLD_MS &&
            stateRank(_state) < stateRank(PrivacyState::SUSPECTED_PEEPING)) {
            _setState(PrivacyState::SUSPECTED_PEEPING, now);
        }
    } else {
        _suspectSinceTime = 0;

        if (stateRank(_state) >= stateRank(PrivacyState::SUSPECTED_PEEPING) && !protectLocked) {
            if (_downgradeSinceTime == 0) {
                _downgradeSinceTime = now;
            }

            if (now - _downgradeSinceTime >= DOWNGRADE_HOLD_MS) {
                _setState(PrivacyState::APPROACHING, now);
            }
        }
    }

    if (protectNear &&
        _suspectSinceTime > 0 &&
        now - _suspectSinceTime >= PROTECT_HOLD_MS) {
        _setState(PrivacyState::PRIVACY_PROTECT, now);
    }

    if (trend == RadarTrend::LEAVING &&
        !suspectNear &&
        stateRank(_state) >= stateRank(PrivacyState::APPROACHING) &&
        !protectLocked) {
        if (_downgradeSinceTime == 0) {
            _downgradeSinceTime = now;
        }

        if (now - _downgradeSinceTime >= DOWNGRADE_HOLD_MS) {
            _setState(PrivacyState::HUMAN_DETECTED, now);
        }
    }

    return _state;
}

uint32_t PrivacyStateMachine::getStateHoldMs() const
{
    return _stateEnterTime > 0 ? millis() - _stateEnterTime : 0;
}

uint32_t PrivacyStateMachine::getDowngradeHoldMs() const
{
    return _downgradeSinceTime > 0 ? millis() - _downgradeSinceTime : 0;
}

void PrivacyStateMachine::reset()
{
    const uint32_t now = millis();
    _setState(PrivacyState::NORMAL, now);
    _nearSinceTime = 0;
    _suspectSinceTime = 0;
    _noTargetSinceTime = 0;
    _downgradeSinceTime = 0;
}

bool PrivacyStateMachine::gestureRelease()
{
    if (_state == PrivacyState::ALARM || _state == PrivacyState::PRIVACY_PROTECT) {
        reset();
        return true;
    }

    return false;
}

void PrivacyStateMachine::forceState(PrivacyState state)
{
    _setState(state, millis());
    _nearSinceTime = 0;
    _suspectSinceTime = 0;
    _noTargetSinceTime = 0;
    _downgradeSinceTime = 0;

    Serial.printf("[STATE] force -> %s\n", privacyStateToEN(_state));
}

String PrivacyStateMachine::getStateJSON(const TargetInfo& info) const
{
    String json = "{";
    json += "\"state\":\"";
    json += privacyStateToEN(_state);
    json += "\",";
    json += "\"state_cn\":\"";
    json += privacyStateToCN(_state);
    json += "\",";
    json += "\"target_state\":";
    json += info.target_state;
    json += ",";
    json += "\"distance_cm\":";
    json += _primaryDistanceMm(info) / 10;
    json += ",";
    json += "\"moving_energy\":";
    json += info.moving_energy;
    json += ",";
    json += "\"static_energy\":";
    json += info.static_energy;
    json += ",";
    json += "\"detect_distance_cm\":";
    json += info.detect_distance_cm;
    json += ",";
    json += "\"state_hold_ms\":";
    json += getStateHoldMs();
    json += ",";
    json += "\"downgrade_hold_ms\":";
    json += getDowngradeHoldMs();
    json += ",";
    json += "\"timestamp_ms\":";
    json += millis();
    json += "}";

    return json;
}

void PrivacyStateMachine::printStateTransition() const
{
    if (_state != _prevState) {
        Serial.printf("[STATE] %s -> %s\n",
                      privacyStateToEN(_prevState),
                      privacyStateToEN(_state));
    }
}

void PrivacyStateMachine::_setState(PrivacyState nextState, uint32_t now)
{
    if (_state == nextState) {
        return;
    }

    _state = nextState;
    _stateEnterTime = now;
    _downgradeSinceTime = 0;
}

bool PrivacyStateMachine::_hasTarget(const TargetInfo& info) const
{
    return info.target_state > 0;
}

uint16_t PrivacyStateMachine::_primaryDistanceMm(const TargetInfo& info) const
{
    if (info.detect_distance_cm > 0) {
        return static_cast<uint16_t>(info.detect_distance_cm * 10);
    }

    if (info.target_state == 1 && info.moving_distance_cm > 0) {
        return static_cast<uint16_t>(info.moving_distance_cm * 10);
    }

    if (info.target_state == 2 && info.static_distance_cm > 0) {
        return static_cast<uint16_t>(info.static_distance_cm * 10);
    }

    if (info.target_state == 3) {
        if (info.moving_distance_cm > 0 && info.static_distance_cm > 0) {
            return static_cast<uint16_t>(min(info.moving_distance_cm, info.static_distance_cm) * 10);
        }

        if (info.moving_distance_cm > 0) {
            return static_cast<uint16_t>(info.moving_distance_cm * 10);
        }

        if (info.static_distance_cm > 0) {
            return static_cast<uint16_t>(info.static_distance_cm * 10);
        }
    }

    return 0;
}

uint16_t PrivacyStateMachine::_thresholdMm(uint16_t baseMm) const
{
    const float factor = _sensitivity > 0.1f ? _sensitivity : 1.0f;
    return static_cast<uint16_t>(baseMm / factor);
}
