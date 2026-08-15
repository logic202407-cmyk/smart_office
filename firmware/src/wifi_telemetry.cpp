#include "wifi_telemetry.h"

#include <WiFi.h>

#include "config.h"
#include "wifi_credentials.h"

#if WIFI_TELEMETRY_ENABLED
namespace {
WiFiServer telemetryServer(WIFI_TELEMETRY_PORT);
WiFiClient telemetryClient;
bool telemetryServerStarted = false;
bool fallbackApStarted = false;
uint32_t stationConnectStartedMs = 0;

void startTelemetryServer(const char* mode)
{
    telemetryServer.begin();
    telemetryServerStarted = true;
    Serial.printf("[WIFI] %s IP=%s TCP=%u\n",
                  mode,
                  WiFi.localIP().toString().c_str(),
                  WIFI_TELEMETRY_PORT);
}

void startFallbackAp()
{
    WiFi.disconnect(true, true);
    WiFi.mode(WIFI_AP);
    if (!WiFi.softAP(WIFI_TELEMETRY_FALLBACK_AP_SSID,
                     WIFI_TELEMETRY_FALLBACK_AP_PASSWORD))
    {
        Serial.println("[WIFI] Fallback AP start FAILED; USB telemetry remains available");
        return;
    }

    fallbackApStarted = true;
    telemetryServer.begin();
    telemetryServerStarted = true;
    Serial.printf("[WIFI] fallback AP=%s IP=%s TCP=%u\n",
                  WIFI_TELEMETRY_FALLBACK_AP_SSID,
                  WiFi.softAPIP().toString().c_str(),
                  WIFI_TELEMETRY_PORT);
}
}
#endif

void wifiTelemetryBegin()
{
#if WIFI_TELEMETRY_ENABLED
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_TELEMETRY_STA_SSID, WIFI_TELEMETRY_STA_PASSWORD);
    stationConnectStartedMs = millis();
    Serial.printf("[WIFI] connecting to STA SSID=%s\n", WIFI_TELEMETRY_STA_SSID);
#endif
}

void wifiTelemetryPoll()
{
#if WIFI_TELEMETRY_ENABLED
    if (!telemetryServerStarted)
    {
        if (WiFi.status() == WL_CONNECTED)
        {
            startTelemetryServer("STA connected");
        }
        else if (!fallbackApStarted &&
                 millis() - stationConnectStartedMs >= WIFI_TELEMETRY_STA_CONNECT_TIMEOUT_MS)
        {
            Serial.println("[WIFI] STA connect timeout; starting fallback AP");
            startFallbackAp();
        }
    }

    if (!telemetryServerStarted)
    {
        return;
    }

    if (telemetryClient && !telemetryClient.connected())
    {
        telemetryClient.stop();
    }

    if (!telemetryClient)
    {
        WiFiClient candidate = telemetryServer.available();
        if (candidate)
        {
            telemetryClient = candidate;
            telemetryClient.setNoDelay(true);
            Serial.println("[WIFI] TCP client connected");
        }
    }
#endif
}

void wifiTelemetryMirrorJson(const String& line)
{
#if WIFI_TELEMETRY_ENABLED
    if (telemetryClient && telemetryClient.connected())
    {
        telemetryClient.println(line);
    }
#else
    (void)line;
#endif
}
