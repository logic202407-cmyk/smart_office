#include <Arduino.h>
#include "config.h"
#include "ld2410b.h"
#include "oled_ui.h"
#include "paj7620.h"
#include "privacy_state_machine.h"
#include "wifi_telemetry.h"

static LD2410B radar;
static PrivacyStateMachine privacyMachine;
static OLED_UI oled;
static Paj7620 gestureSensor;

static constexpr uint8_t DIST_FILTER_SIZE = 3;
static constexpr uint16_t TREND_THRESHOLD_MM = 120;
static constexpr uint16_t TRACK_PRINT_INTERVAL_MS = 60;
static constexpr uint32_t DATA_STALE_MS = 1000;

static uint32_t lastStatusMs = 0;
static uint32_t lastBlinkMs = 0;
static uint32_t lastGesturePollMs = 0;
static uint32_t lastGestureDiagMs = 0;
static uint32_t lastGestureEventMs = 0;
static bool ledState = false;
static bool gestureOk = false;
static GestureType lastGestureEvent = GestureType::NONE;
static uint16_t pendingFarJumpMm = 0;
static uint8_t pendingFarJumpCount = 0;
static uint8_t stableTrendCount = 0;
static uint16_t stableLockMm = 0;
static uint8_t stableDriftCount = 0;

static uint16_t distSamples[DIST_FILTER_SIZE] = {0};
static uint8_t distSampleIndex = 0;
static uint8_t distSampleCount = 0;
static uint16_t previousAvgDistMm = 0;
static uint16_t displayDistMm = 0;
static uint32_t presentSinceMs = 0;
static PrivacyState lastLedPrivacyState = PrivacyState::NORMAL;

static const char* targetStateName(uint8_t state)
{
    switch (state)
    {
    case LD2410B_TARGET_NONE:
        return "NO_TARGET";
    case LD2410B_TARGET_MOVING:
        return "MOVING";
    case LD2410B_TARGET_STATIC:
        return "STATIC";
    case LD2410B_TARGET_BOTH:
        return "BOTH";
    default:
        return "UNKNOWN";
    }
}

static uint16_t selectPrimaryDistanceMm(const LD2410B_TargetInfo& info)
{
    const bool closeRangeDisplay = displayDistMm > 0 && displayDistMm <= 1200U;
    const bool displayRadarRange = displayDistMm == 0 || displayDistMm <= 1800U;

    if (info.detect_dist > 0 &&
        info.target_state != LD2410B_TARGET_NONE &&
        displayRadarRange)
    {
        return info.detect_dist;
    }

    if (info.detect_dist > 0 && closeRangeDisplay)
    {
        const uint16_t nearestClassified =
            (info.static_dist > 0 && info.moving_dist > 0) ? min(info.static_dist, info.moving_dist)
            : max(info.static_dist, info.moving_dist);

        if (nearestClassified == 0)
        {
            return info.detect_dist;
        }

        const uint16_t gap = nearestClassified > info.detect_dist
            ? nearestClassified - info.detect_dist
            : info.detect_dist - nearestClassified;

        if (gap <= 180U || info.detect_dist < nearestClassified)
        {
            return info.detect_dist;
        }
    }

    // Prefer classified target distances over unclassified detect_dist.
    // detect_dist is the closest gate with energy â€?it gets stuck on nearby
    // reflections/ghosts when the real target moves away.
    
    if (info.target_state == LD2410B_TARGET_BOTH && info.detect_dist > 0)
    {
        const uint16_t nearerClassified = (info.static_dist > 0 && info.moving_dist > 0)
            ? min(info.static_dist, info.moving_dist)
            : max(info.static_dist, info.moving_dist);

        if (nearerClassified > 0 &&
            info.detect_dist <= 1200U &&
            info.detect_dist + 120U <= nearerClassified)
        {
            return info.detect_dist;
        }
    }

    if (info.target_state == LD2410B_TARGET_BOTH)
    {
        // Both gates firing. In a multi-person environment (office with
        // adjacent desks), the two gates may be tracking DIFFERENT people:
        //   - static  = person sitting at adjacent desk (30-80cm)
        //   - moving  = person walking toward/away from screen
        //
        // Heuristic: if the gap between the two distances exceeds 30% of
        // the larger, treat them as different people and lock onto whichever
        // is closer to the current display distance (maintains tracking
        // continuity â€?no sudden jumps to a different person).
        if (info.static_dist > 0 && info.moving_dist > 0)
        {
            const uint16_t larger  = max(info.static_dist, info.moving_dist);
            const uint16_t smaller = min(info.static_dist, info.moving_dist);
            const uint16_t gap     = larger - smaller;

            // Threshold: 300 â†?30%. Floor at 200mm so tiny gaps don't flip.
            if (gap > max(larger * 3U / 10U, 200U))
            {
                // Two different people â€?lock onto the distance closer to
                // the last known display distance.
                if (displayDistMm > 0)
                {
                    const uint16_t diffMoving = info.moving_dist > displayDistMm
                        ? info.moving_dist - displayDistMm
                        : displayDistMm - info.moving_dist;
                    const uint16_t diffStatic = info.static_dist > displayDistMm
                        ? info.static_dist - displayDistMm
                        : displayDistMm - info.static_dist;

                    return (diffMoving < diffStatic) ? info.moving_dist : info.static_dist;
                }

                // No display distance yet: prefer the farther target
                // (the closer one is likely an adjacent desk person).
                return larger;
            }
        }

        // Same person (gates agree), or only one gate valid.
        // Static is the person's settled position â€?prefer it.
        if (info.static_dist > 0)
            return info.static_dist;
        return info.moving_dist;
    }
    
    if (info.target_state == LD2410B_TARGET_MOVING)
    {
        return info.moving_dist;
    }
    
    if (info.target_state == LD2410B_TARGET_STATIC)
    {
        return info.static_dist;
    }
    
    // Fallback: no classified target, use raw detect distance
    if (info.detect_dist > 0)
    {
        return info.detect_dist;
    }
    
    return 0;
}

// Experiment distance source: use values from the current LD2410B frame only.
// No filtering, state memory, target locking, or continuity heuristic is used.
static uint16_t selectDirectDistanceMm(const LD2410B_TargetInfo& info)
{
    if (info.detect_dist > 0)
    {
        return info.detect_dist;
    }

    if (info.static_dist > 0)
    {
        return info.static_dist;
    }

    return info.moving_dist;
}

static TargetInfo toTargetInfo(const LD2410B_TargetInfo& info, uint16_t displayDistanceMm)
{
    TargetInfo target = {};
    target.target_state = info.target_state;
    target.moving_distance_cm = info.moving_dist / 10;
    target.static_distance_cm = info.static_dist / 10;
    target.moving_energy = info.moving_energy;
    target.static_energy = info.static_energy;
    target.detect_distance_cm = info.detect_dist / 10;
    target.display_distance_cm = displayDistanceMm / 10;
    return target;
}

static void resetDistanceFilter()
{
    distSampleIndex = 0;
    distSampleCount = 0;
    previousAvgDistMm = 0;
    displayDistMm = 0;
    pendingFarJumpMm = 0;
    pendingFarJumpCount = 0;
    stableTrendCount = 0;
    stableLockMm = 0;
    stableDriftCount = 0;

    for (uint8_t i = 0; i < DIST_FILTER_SIZE; i++)
    {
        distSamples[i] = 0;
    }
}

static uint16_t updateDisplayDistanceMm(uint16_t rawDistMm, bool present, RadarTrend trend)
{
    if (!present || rawDistMm == 0)
    {
        displayDistMm = 0;
        stableTrendCount = 0;
        stableLockMm = 0;
        stableDriftCount = 0;
        return 0;
    }

    if (displayDistMm == 0)
    {
        displayDistMm = rawDistMm;
        stableTrendCount = 0;
        stableLockMm = rawDistMm;
        stableDriftCount = 0;
        return displayDistMm;
    }

    if (trend == RadarTrend::STABLE)
    {
        if (stableTrendCount < 20)
        {
            stableTrendCount++;
        }
    }
    else
    {
        stableTrendCount = 0;
        stableLockMm = displayDistMm;
        stableDriftCount = 0;
    }

    const int32_t delta = static_cast<int32_t>(rawDistMm) - static_cast<int32_t>(displayDistMm);
    const int32_t absDelta = labs(delta);

    if (stableTrendCount >= 6)
    {
        if (stableLockMm == 0)
        {
            stableLockMm = displayDistMm;
        }

        const int32_t lockDelta = static_cast<int32_t>(rawDistMm) - static_cast<int32_t>(stableLockMm);
        const int32_t absLockDelta = labs(lockDelta);

        if (absLockDelta <= 60)
        {
            stableDriftCount = 0;
            displayDistMm = stableLockMm;
            return displayDistMm;
        }

        if (absLockDelta <= 140)
        {
            stableDriftCount++;
            if (stableDriftCount < 3)
            {
                displayDistMm = stableLockMm;
                return displayDistMm;
            }

            stableDriftCount = 0;
            stableLockMm = static_cast<uint16_t>((stableLockMm * 5UL + rawDistMm) / 6UL);
            displayDistMm = stableLockMm;
            return displayDistMm;
        }

        stableDriftCount = 0;
        stableLockMm = static_cast<uint16_t>((stableLockMm * 3UL + rawDistMm * 2UL) / 5UL);
        displayDistMm = stableLockMm;
        return displayDistMm;
    }
    else
    {
        stableLockMm = displayDistMm;
        stableDriftCount = 0;
    }

    if (absDelta <= 100)
    {
        displayDistMm = static_cast<uint16_t>((displayDistMm * 5UL + rawDistMm) / 6UL);
        return displayDistMm;
    }

    if (absDelta <= 180)
    {
        displayDistMm = static_cast<uint16_t>((displayDistMm * 4UL + rawDistMm) / 5UL);
        return displayDistMm;
    }

    if (absDelta <= 20)
    {
        displayDistMm = static_cast<uint16_t>((displayDistMm * 3UL + rawDistMm * 2UL) / 5UL);
        return displayDistMm;
    }

    if (absDelta <= 90)
    {
        displayDistMm = static_cast<uint16_t>((displayDistMm + rawDistMm * 2UL) / 3UL);
        return displayDistMm;
    }

    const int32_t maxStepNear = (absDelta > 500) ? 260 : 180;
    const int32_t maxStepAway = (absDelta > 500) ? 380 : 240;
    const int32_t maxStep = (delta > 0) ? maxStepAway : maxStepNear;
    const int32_t step = constrain(delta, -maxStep, maxStep);
    displayDistMm = static_cast<uint16_t>(static_cast<int32_t>(displayDistMm) + step);
    return displayDistMm;
}

static void restoreWireBus()
{
    Wire.end();
    pinMode(PIN_I2C_SDA, INPUT_PULLUP);
    pinMode(PIN_I2C_SCL, INPUT_PULLUP);
    delayMicroseconds(80);
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
    Wire.setClock(I2C_FREQ);
    // No setTimeOut â€?let U8g2 I2C transactions complete naturally
}

static void applyGestureAction(uint32_t now, GestureType gesture)
{
    switch (gesture)
    {
    case GestureType::FORWARD:
        privacyMachine.forceState(PrivacyState::PRIVACY_PROTECT);
        Serial.printf("[GESTURE_ACTION] t=%lu FORWARD -> force PRIVACY_PROTECT\n", now);
        break;
    case GestureType::BACKWARD:
    case GestureType::WAVE:
        if (privacyMachine.gestureRelease())
        {
            Serial.printf("[GESTURE_ACTION] t=%lu %s -> release to NORMAL\n",
                          now,
                          Paj7620::getGestureNameEN(gesture));
        }
        break;
    default:
        break;
    }
}

static void updateStatusLed(uint32_t now, PrivacyState state)
{
    uint16_t intervalMs = 0;

    switch (state)
    {
    case PrivacyState::PRIVACY_PROTECT:
    case PrivacyState::ALARM:
        intervalMs = 120;
        break;
    case PrivacyState::SUSPECTED_PEEPING:
        intervalMs = 220;
        break;
    case PrivacyState::APPROACHING:
        intervalMs = 350;
        break;
    case PrivacyState::HUMAN_DETECTED:
        intervalMs = 700;
        break;
    case PrivacyState::NORMAL:
    default:
        ledState = false;
        digitalWrite(PIN_LED, LOW);
        return;
    }

    if (state != lastLedPrivacyState)
    {
        lastLedPrivacyState = state;
        lastBlinkMs = now;
        ledState = true;
        digitalWrite(PIN_LED, HIGH);
        return;
    }

    if (now - lastBlinkMs >= intervalMs)
    {
        lastBlinkMs = now;
        ledState = !ledState;
        digitalWrite(PIN_LED, ledState ? HIGH : LOW);
    }
}

static void pushDistanceSample(uint16_t distMm)
{
    if (distMm == 0)
    {
        return;
    }

    distSamples[distSampleIndex] = distMm;
    distSampleIndex = (distSampleIndex + 1) % DIST_FILTER_SIZE;

    if (distSampleCount < DIST_FILTER_SIZE)
    {
        distSampleCount++;
    }
}

static uint16_t averageDistanceMm()
{
    if (distSampleCount == 0)
    {
        return 0;
    }

    uint32_t sum = 0;
    for (uint8_t i = 0; i < distSampleCount; i++)
    {
        sum += distSamples[i];
    }

    return static_cast<uint16_t>(sum / distSampleCount);
}

static uint16_t filteredDistanceMm()
{
    if (distSampleCount == 0)
    {
        return 0;
    }

    if (distSampleCount == 1)
    {
        return distSamples[0];
    }

    uint16_t values[DIST_FILTER_SIZE] = {0};
    for (uint8_t i = 0; i < distSampleCount; i++)
    {
        values[i] = distSamples[i];
    }

    for (uint8_t i = 0; i + 1 < distSampleCount; i++)
    {
        for (uint8_t j = i + 1; j < distSampleCount; j++)
        {
            if (values[j] < values[i])
            {
                const uint16_t tmp = values[i];
                values[i] = values[j];
                values[j] = tmp;
            }
        }
    }

    if (distSampleCount == 2)
    {
        return static_cast<uint16_t>((values[0] + values[1]) / 2U);
    }

    return values[1];
}

static uint16_t stabilizePrimaryDistanceMm(uint16_t candidateDistMm, RadarTrend trend, bool present, bool trustedDirectSource)
{
    if (!present || candidateDistMm == 0 || displayDistMm == 0)
    {
        pendingFarJumpMm = 0;
        pendingFarJumpCount = 0;
        return candidateDistMm;
    }

    if (trustedDirectSource)
    {
        pendingFarJumpMm = 0;
        pendingFarJumpCount = 0;
        return candidateDistMm;
    }

    const int32_t delta = static_cast<int32_t>(candidateDistMm) - static_cast<int32_t>(displayDistMm);

    if (delta <= 120 || trend != RadarTrend::STABLE)
    {
        pendingFarJumpMm = 0;
        pendingFarJumpCount = 0;
        return candidateDistMm;
    }

    const uint16_t candidateGap = pendingFarJumpMm > candidateDistMm
        ? pendingFarJumpMm - candidateDistMm
        : candidateDistMm - pendingFarJumpMm;

    if (pendingFarJumpMm == 0 || candidateGap > 40)
    {
        pendingFarJumpMm = candidateDistMm;
        pendingFarJumpCount = 1;
        return displayDistMm;
    }

    pendingFarJumpCount++;
    if (pendingFarJumpCount < 4)
    {
        return displayDistMm;
    }

    pendingFarJumpMm = 0;
    pendingFarJumpCount = 0;
    return candidateDistMm;
}

static RadarTrend calculateTrend(uint16_t avgDistMm)
{
    if (previousAvgDistMm == 0 || avgDistMm == 0)
    {
        return RadarTrend::UNKNOWN;
    }

    const int32_t deltaMm = static_cast<int32_t>(avgDistMm) - static_cast<int32_t>(previousAvgDistMm);

    if (deltaMm <= -static_cast<int32_t>(TREND_THRESHOLD_MM))
    {
        return RadarTrend::APPROACHING;
    }

    if (deltaMm >= static_cast<int32_t>(TREND_THRESHOLD_MM))
    {
        return RadarTrend::LEAVING;
    }

    return RadarTrend::STABLE;
}

static void sendStateJson(uint32_t now,
                          const LD2410B_TargetInfo& info,
                          bool present,
                          uint16_t primaryDistMm,
                          uint16_t avgDistMm,
                          uint16_t displayDistanceMm,
                          RadarTrend trend,
                          uint32_t holdMs,
                          PrivacyState state,
                          uint32_t dataAgeMs)
{
    char buffer[768] = {};
    const int written = snprintf(buffer, sizeof(buffer),
                                 "{\"type\":\"state\",\"t_ms\":%lu,\"frames\":%lu,\"present\":%s,\"radar_state\":%u,\"target_state\":%u,\"state\":\"%s\",\"distance_cm\":%u,\"raw_distance_cm\":%u,\"avg_distance_cm\":%u,\"display_distance_cm\":%u,\"trend\":\"%s\",\"hold_ms\":%lu,\"state_hold_ms\":%lu,\"downgrade_hold_ms\":%lu,\"moving_distance_cm\":%u,\"moving_energy\":%u,\"static_distance_cm\":%u,\"static_energy\":%u,\"detect_distance_cm\":%u,\"age_ms\":%lu,\"gesture\":\"%s\",\"gesture_age_ms\":%lu}",
                                 now, radar.getFrameCount(), present ? "true" : "false",
                                 present ? info.target_state : 0, present ? info.target_state : 0,
                                 privacyStateToEN(state), displayDistanceMm / 10, primaryDistMm / 10,
                                 avgDistMm / 10, displayDistanceMm / 10, radarTrendToEN(trend), holdMs,
                                 privacyMachine.getStateHoldMs(), privacyMachine.getDowngradeHoldMs(),
                                 present ? info.moving_dist / 10 : 0, present ? info.moving_energy : 0,
                                 present ? info.static_dist / 10 : 0, present ? info.static_energy : 0,
                                 present ? info.detect_dist / 10 : 0, dataAgeMs,
                                 Paj7620::getGestureNameEN(lastGestureEvent),
                                 lastGestureEventMs > 0 ? now - lastGestureEventMs : 0);
    if (written > 0 && written < static_cast<int>(sizeof(buffer)))
    {
        const String line(buffer);
        Serial.println(line);
        wifiTelemetryMirrorJson(line);
    }
}

static void sendEngineeringJson(uint32_t now, const LD2410B_TargetInfo& info)
{
    if (!info.engineering_data)
        return;

    String line = "{\"type\":\"engineering\",\"t_ms\":" + String(now) + ",\"moving_gate_energy\":[";
    for (uint8_t gate = 0; gate < info.moving_gate_count; ++gate)
        line += (gate == 0 ? "" : ",") + String(info.moving_gate_energy[gate]);
    line += "],\"static_gate_energy\":[";
    for (uint8_t gate = 0; gate < info.static_gate_count; ++gate)
        line += (gate == 0 ? "" : ",") + String(info.static_gate_energy[gate]);
    line += "],\"light\":" + String(info.light_level) + ",\"out\":" + String(info.out_state) + "}";
    Serial.println(line);
    wifiTelemetryMirrorJson(line);
}

static void sendGestureJson(uint32_t now, GestureType gesture, uint8_t rawGesture)
{
    char buffer[128] = {};
    const int written = snprintf(buffer, sizeof(buffer),
                                 "{\"type\":\"gesture\",\"t_ms\":%lu,\"gesture\":\"%s\",\"raw\":%u}",
                                 now, Paj7620::getGestureNameEN(gesture), rawGesture);
    if (written > 0 && written < static_cast<int>(sizeof(buffer)))
    {
        const String line(buffer);
        Serial.println(line);
        wifiTelemetryMirrorJson(line);
    }
}

void setup()
{
    Serial.begin(SERIAL_BAUD);
    // Wait for USB-CDC to enumerate (Windows takes ~2-3s)
    unsigned long serialDeadline = millis() + 4000;
    while (!Serial && millis() < serialDeadline) { delay(10); }
    if (Serial) Serial.println("=== SERIAL CONNECTED ===");
    delay(500);

    pinMode(PIN_LED, OUTPUT);
    digitalWrite(PIN_LED, LOW);

    wifiTelemetryBegin();

    Serial.println();
    Serial.println("====================================");
    Serial.println(" LD2410B PRIVACY STATE TEST");
    Serial.println("====================================");
    Serial.printf("Serial baud    : %d\n", SERIAL_BAUD);
    Serial.printf("Radar baud     : %d\n", RADAR_UART_BAUD);
    Serial.printf("Radar RX pin   : GPIO%d\n", PIN_RADAR_TX);
    Serial.printf("Radar TX pin   : GPIO%d\n", PIN_RADAR_RX);
    Serial.println("Privacy state  : module with hysteresis enabled");
    Serial.printf("OLED I2C       : SDA=GPIO%d SCL=GPIO%d addr=0x%02X\n",
                  OLED_SDA,
                  OLED_SCL,
                  OLED_I2C_ADDR);

    restoreWireBus();
    gestureOk = gestureSensor.begin();
    Serial.printf("[GESTURE] PAJ7620 %s\n", gestureOk ? "OK" : "NOT_FOUND");

    if (oled.begin())
    {
        Serial.println("[OLED] begin OK");
        oled.showSplash();
        delay(800);
    }
    else
    {
        Serial.println("[OLED] begin FAILED");
    }

    if (radar.begin())
    {
        Serial.println("[RADAR] begin OK, enabling engineering telemetry...");
        delay(80);
        radar.enableConfig();
        delay(80);
        radar.setEngineeringMode(true);
        delay(80);
        radar.disableConfig();
    }
    else
    {
        Serial.println("[RADAR] begin FAILED");
    }
}

void loop()
{
    wifiTelemetryPoll();
    radar.update();

    const uint32_t now = millis();

    // === RADAR DATA ===
    if (radar.hasNewData())
    {
        const LD2410B_TargetInfo& info = radar.getTargetInfo();
        const bool present = info.valid && info.target_state != LD2410B_TARGET_NONE;
        const uint16_t primaryDistMm = selectDirectDistanceMm(info);

        if (present && primaryDistMm > 0)
        {
            pushDistanceSample(primaryDistMm);

            if (presentSinceMs == 0)
            {
                presentSinceMs = now;
            }
        }
        else
        {
            presentSinceMs = 0;
            resetDistanceFilter();
        }
    }

    // === OLED RENDER (before gesture - uses clean Wire bus) ===
    if (now - lastStatusMs >= TRACK_PRINT_INTERVAL_MS)
    {
        lastStatusMs = now;

        const LD2410B_TargetInfo& info = radar.getTargetInfo();
        const uint32_t dataAgeMs = info.valid ? now - info.timestamp : 0;
        const bool fresh = info.valid && dataAgeMs <= DATA_STALE_MS;
        const bool present = fresh && info.target_state != LD2410B_TARGET_NONE;
        const uint16_t primaryDistMm = present ? selectDirectDistanceMm(info) : 0;
        const uint16_t avgDistMm = present ? averageDistanceMm() : 0;
        const RadarTrend trend = present ? calculateTrend(avgDistMm) : RadarTrend::NONE;
        const uint16_t filteredDistMm = present ? filteredDistanceMm() : 0;
        const bool trustedDirectSource = present && info.detect_dist > 0 && filteredDistMm == info.detect_dist;
        const uint16_t stableDistMm = present ? stabilizePrimaryDistanceMm(filteredDistMm, trend, present, trustedDirectSource) : 0;
        const uint16_t displayDistanceMm = updateDisplayDistanceMm(stableDistMm, present, trend);
        const uint32_t holdMs = (present && presentSinceMs > 0) ? now - presentSinceMs : 0;
        const TargetInfo targetInfo = toTargetInfo(info, displayDistanceMm);
        const PrivacyState state = privacyMachine.update(targetInfo, trend, avgDistMm, present);
        updateStatusLed(now, state);
        oled.render(privacyMachine, targetInfo, false);

        Serial.printf("[PRIVACY] t=%lu frames=%lu present=%s state=%s(%u) dist=%umm display=%umm avg=%umm trend=%s privacy=%s%s age=%lums\n",
                      now,
                      radar.getFrameCount(),
                      present ? "yes" : "no",
                      present ? targetStateName(info.target_state) : "---",
                      present ? info.target_state : 0,
                      stableDistMm,
                      displayDistanceMm,
                      avgDistMm,
                      radarTrendToEN(trend),
                      privacyStateToEN(state),
                      privacyMachine.stateChanged() ? " *" : "",
                      dataAgeMs);

        sendStateJson(now, info, present, primaryDistMm, avgDistMm, displayDistanceMm, trend, holdMs, state, dataAgeMs);
        sendEngineeringJson(now, info);

        if (present)
        {
            previousAvgDistMm = avgDistMm;
        }
    }

    // === GESTURE POLLING (after OLED, resets Wire for next cycle) ===
    if (gestureOk && now - lastGesturePollMs >= 100)
    {
        lastGesturePollMs = now;
        restoreWireBus();
        uint8_t rawGesture1 = 0;
        uint8_t rawGesture2 = 0;
        const bool rawOk = gestureSensor.readRawGestureRegs(rawGesture1, rawGesture2);
        if (rawOk && (rawGesture1 != 0 || rawGesture2 != 0))
        {
            Serial.printf("[GESTURE_RAW] g1=0x%02X g2=0x%02X int=%d\n",
                          rawGesture1,
                          rawGesture2,
                          digitalRead(PIN_PAJ7620_INT));
        }

        if (rawOk)
        {
            const GestureType gesture = gestureSensor.decodeRawGesture(rawGesture1, rawGesture2);
            if (gesture != GestureType::NONE)
            {
                lastGestureEvent = gesture;
                lastGestureEventMs = now;
                sendGestureJson(now, gesture, gestureSensor.getLastRawGesture());
                applyGestureAction(now, gesture);
                Serial.printf("[GESTURE] %s raw=0x%02X int=%d\n",
                              Paj7620::getGestureNameEN(gesture),
                              gestureSensor.getLastRawGesture(),
                              digitalRead(PIN_PAJ7620_INT));
            }
        }
        else if (!rawOk && now - lastGestureDiagMs >= 1000)
        {
            lastGestureDiagMs = now;
            Serial.printf("[GESTURE_RAW] read_failed int=%d\n", digitalRead(PIN_PAJ7620_INT));
        }
    }

    delay(2);
}
