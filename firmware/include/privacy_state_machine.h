#ifndef PRIVACY_STATE_MACHINE_H
#define PRIVACY_STATE_MACHINE_H

#include <Arduino.h>
#include "config.h"

struct TargetInfo {
    int target_state;        // 0=none, 1=moving, 2=static, 3=moving+static
    int moving_distance_cm;
    int static_distance_cm;
    int moving_energy;
    int static_energy;
    int detect_distance_cm;
    int display_distance_cm;   // Smoothed distance for OLED/PC display only
};

enum class RadarTrend : uint8_t {
    UNKNOWN = 0,
    APPROACHING,
    LEAVING,
    STABLE,
    NONE
};

enum class PrivacyState : uint8_t {
    NORMAL = 0,
    HUMAN_DETECTED,
    APPROACHING,
    SUSPECTED_PEEPING,
    PRIVACY_PROTECT,
    ALARM
};

extern const char* privacyStateToCN(PrivacyState state);
extern const char* privacyStateToEN(PrivacyState state);
extern const char* radarTrendToEN(RadarTrend trend);

class PrivacyStateMachine {
public:
    PrivacyStateMachine();

    PrivacyState update(const TargetInfo& info);
    PrivacyState update(const TargetInfo& info,
                        RadarTrend trend,
                        uint16_t averageDistanceMm,
                        bool present);

    PrivacyState getState() const { return _state; }
    PrivacyState getPrevState() const { return _prevState; }
    bool stateChanged() const { return _state != _prevState; }

    uint32_t getStateHoldMs() const;
    uint32_t getDowngradeHoldMs() const;

    void reset();
    bool gestureRelease();
    void forceState(PrivacyState state);

    String getStateJSON(const TargetInfo& info) const;

    void setSensitivity(float factor) { _sensitivity = factor; }
    float getSensitivity() const { return _sensitivity; }

    void printStateTransition() const;

private:
    PrivacyState _state;
    PrivacyState _prevState;
    uint32_t _stateEnterTime;
    uint32_t _nearSinceTime;
    uint32_t _suspectSinceTime;
    uint32_t _noTargetSinceTime;
    uint32_t _downgradeSinceTime;
    float _sensitivity;

    void _setState(PrivacyState nextState, uint32_t now);
    bool _hasTarget(const TargetInfo& info) const;
    uint16_t _primaryDistanceMm(const TargetInfo& info) const;
    uint16_t _thresholdMm(uint16_t baseMm) const;
};

#endif
