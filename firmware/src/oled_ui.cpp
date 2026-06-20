#include "oled_ui.h"
#include <Arduino.h>
#include <Wire.h>

static const char* shortPrivacyState(PrivacyState state)
{
    switch (state) {
    case PrivacyState::NORMAL:
        return "NORMAL";
    case PrivacyState::HUMAN_DETECTED:
        return "HUMAN";
    case PrivacyState::APPROACHING:
        return "APPROACH";
    case PrivacyState::SUSPECTED_PEEPING:
        return "SUSPECT";
    case PrivacyState::PRIVACY_PROTECT:
        return "PROTECT";
    case PrivacyState::ALARM:
        return "ALARM";
    default:
        return "UNKNOWN";
    }
}

static const char* targetTypeName(int targetState)
{
    switch (targetState) {
    case 1:
        return "MOVING";
    case 2:
        return "STATIC";
    case 3:
        return "BOTH";
    default:
        return "NONE";
    }
}

OLED_UI::OLED_UI()
    : _u8g2(U8G2_R0, U8X8_PIN_NONE)
{
}

bool OLED_UI::begin()
{
    Wire.begin(OLED_SDA, OLED_SCL);
    Wire.setClock(I2C_FREQ);

    bool oledFound = false;
    Serial.print("[I2C] scan:");
    for (uint8_t addr = 0x08; addr <= 0x77; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.printf(" 0x%02X", addr);
            if (addr == OLED_I2C_ADDR) {
                oledFound = true;
            }
        }
    }
    Serial.println();

    if (!oledFound) {
        Serial.printf("[OLED] 0x%02X not found, skip display\n", OLED_I2C_ADDR);
        _ok = false;
        return false;
    }

    // U8g2 expects the 8-bit I2C address.
    _u8g2.setI2CAddress(OLED_I2C_ADDR << 1);
    _u8g2.begin();
    _u8g2.setFont(u8g2_font_6x10_tf);
    _u8g2.setFlipMode(0);
    _ok = true;
    return true;
}

void OLED_UI::showSplash()
{
    if (!_ok) return;
    _u8g2.clearBuffer();
    _u8g2.setFont(u8g2_font_10x20_tf);
    _u8g2.drawStr(8, 20, "SmartOffice");
    _u8g2.setFont(u8g2_font_6x10_tf);
    _u8g2.drawStr(10, 38, "OLED OK  I2C 0x3C");
    _u8g2.drawStr(16, 56, "Radar Privacy v1");
    _u8g2.sendBuffer();
}

void OLED_UI::showError(const char* msg)
{
    if (!_ok) return;
    _u8g2.clearBuffer();
    _u8g2.setFont(u8g2_font_6x10_tf);
    _u8g2.drawStr(0, 12, "ERROR:");
    _u8g2.drawStr(0, 28, msg);
    _u8g2.sendBuffer();
}

void OLED_UI::render(const PrivacyStateMachine& sm, const TargetInfo& info, bool pcConnected)
{
    if (!_ok) return;

    int effectiveDist = info.display_distance_cm;
    if (effectiveDist > 0) {
        // Use the smoothed display distance from main.cpp.
    } else if (info.detect_distance_cm > 0) {
        effectiveDist = info.detect_distance_cm;
    } else if (info.moving_distance_cm > 0 && info.static_distance_cm > 0) {
        effectiveDist = min(info.moving_distance_cm, info.static_distance_cm);
    } else if (info.moving_distance_cm > 0) {
        effectiveDist = info.moving_distance_cm;
    } else if (info.static_distance_cm > 0) {
        effectiveDist = info.static_distance_cm;
    }

    // Ensure display is awake
    _u8g2.setPowerSave(0);

    // Use firstPage/nextPage pattern - more reliable than sendBuffer
    _u8g2.firstPage();
    do {
        _u8g2.setFont(u8g2_font_6x10_tf);

        char line[32];
        snprintf(line, sizeof(line), "PRIVACY:%s", shortPrivacyState(sm.getState()));
        _u8g2.drawStr(0, 11, line);

        snprintf(line, sizeof(line), "DIST :%3dcm", effectiveDist);
        _u8g2.drawStr(0, 25, line);

        snprintf(line, sizeof(line), "TARGET:%s", targetTypeName(info.target_state));
        _u8g2.drawStr(0, 39, line);

        snprintf(line, sizeof(line), "HOLD:%5.1fs", sm.getStateHoldMs() / 1000.0f);
        _u8g2.drawStr(0, 53, line);

        _drawFooter(pcConnected);
    } while (_u8g2.nextPage());
}

void OLED_UI::_drawHeader(const char* stateCN, const TargetInfo& info)
{
    char header[24];
    snprintf(header, sizeof(header), "[%s] %dcm", stateCN, info.detect_distance_cm);
    _u8g2.drawStr(0, 12, header);
}

void OLED_UI::_drawTargetType(const TargetInfo& info, int y)
{
    char line[24];
    snprintf(line, sizeof(line), "TARGET:%s", targetTypeName(info.target_state));
    _u8g2.drawStr(0, y, line);
}

void OLED_UI::_drawFooter(bool pcConnected)
{
    _u8g2.drawStr(78, 63, pcConnected ? "PC:ON" : "LOCAL");
}
