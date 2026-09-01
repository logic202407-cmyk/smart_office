// Distance-only experiment firmware for SmartOffice / LD2410B.
//
// Design rule: one valid radar frame produces one JSON record. This program
// intentionally contains no temporal filtering, state machine, target locking,
// gesture processing, OLED rendering, or PC-side protection action.

#include <Arduino.h>

#include "config.h"
#include "ld2410b.h"

static LD2410B radar;

static void sendMeasurement(const LD2410B_TargetInfo& info)
{
    const bool present = info.valid && info.target_state != LD2410B_TARGET_NONE;
    // LD2410B detect_dist is the module's direct reported detection distance.
    // A zero means no direct distance is available; it is not substituted with
    // moving/static values so no hidden selection rule changes the measurement.
    const uint16_t directDistanceMm = present ? info.detect_dist : 0;

    Serial.printf(
        "{\"type\":\"measurement\",\"t_ms\":%lu,\"frames\":%lu,"
        "\"present\":%s,\"target_state\":%u,"
        "\"direct_distance_mm\":%u,\"direct_distance_cm\":%u,"
        "\"moving_distance_mm\":%u,\"moving_energy\":%u,"
        "\"static_distance_mm\":%u,\"static_energy\":%u,"
        "\"measurement_valid\":%s}\n",
        millis(),
        radar.getFrameCount(),
        present ? "true" : "false",
        present ? info.target_state : 0,
        directDistanceMm,
        directDistanceMm / 10,
        present ? info.moving_dist : 0,
        present ? info.moving_energy : 0,
        present ? info.static_dist : 0,
        present ? info.static_energy : 0,
        directDistanceMm > 0 ? "true" : "false");
}

void setup()
{
    Serial.begin(SERIAL_BAUD);
    const uint32_t serialDeadline = millis() + 4000;
    while (!Serial && millis() < serialDeadline) {
        delay(10);
    }

    pinMode(PIN_LED, OUTPUT);
    digitalWrite(PIN_LED, LOW);
    radar.begin();
}

void loop()
{
    radar.update();
    if (!radar.hasNewData()) {
        return;
    }

    const LD2410B_TargetInfo& info = radar.getTargetInfo();
    sendMeasurement(info);
    digitalWrite(PIN_LED, (info.valid && info.target_state != LD2410B_TARGET_NONE) ? HIGH : LOW);
}
