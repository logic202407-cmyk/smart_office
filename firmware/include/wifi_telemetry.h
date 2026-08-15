#ifndef WIFI_TELEMETRY_H
#define WIFI_TELEMETRY_H

#include <Arduino.h>

// Experimental-only JSONL mirror. It never receives commands and failure to
// connect must never affect the radar, state machine, OLED, or USB serial log.
void wifiTelemetryBegin();
void wifiTelemetryPoll();
void wifiTelemetryMirrorJson(const String& line);

#endif // WIFI_TELEMETRY_H
