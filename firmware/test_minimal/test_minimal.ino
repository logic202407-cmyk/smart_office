#include <Arduino.h>

void setup() {
    Serial.begin(115200);
    delay(100);

    pinMode(48, OUTPUT);  // ESP32-S3-DevKitC-1 板载 LED

    Serial.println();
    Serial.println("=== MINIMAL BOOT TEST ===");
    Serial.printf("Chip: %s Rev %d\n", ESP.getChipModel(), ESP.getChipRevision());
    Serial.printf("CPU: %d MHz\n", ESP.getCpuFreqMHz());
    Serial.printf("Flash: %d MB\n", ESP.getFlashChipSize() / 1048576);
    Serial.printf("PSRAM: %d MB\n", ESP.getPsramSize() / 1048576);
    Serial.printf("Free heap: %d\n", ESP.getFreeHeap());
    Serial.println("=== BOOT OK ===");
}

void loop() {
    digitalWrite(48, HIGH);
    delay(500);
    digitalWrite(48, LOW);
    delay(500);
    Serial.println("blink");
}
