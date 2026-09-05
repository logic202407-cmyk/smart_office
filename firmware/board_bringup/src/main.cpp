#include <Arduino.h>
#include <Wire.h>

constexpr int kLedPin = 1;
constexpr int kSdaPin = 4;
constexpr int kSclPin = 5;
constexpr int kRadarRxPin = 17;
constexpr int kRadarTxPin = 18;
constexpr uint32_t kRadarBaud = 115200;
constexpr uint8_t kOledAddress = 0x3C;
constexpr uint8_t kPajAddress = 0x73;
constexpr size_t kRadarFrameBytes = 30;

HardwareSerial radar(1);

struct RadarStats {
  uint32_t bytes = 0;
  uint32_t headers = 0;
  uint32_t validFrames = 0;
  uint32_t invalidFrames = 0;
  uint8_t lastTargets = 0;
  uint8_t headerMatch = 0;
  uint8_t frame[kRadarFrameBytes] = {};
  size_t frameLength = 0;
};

RadarStats radarStats;

const uint8_t kPajInit[][2] = {
  {0xEF,0x00},{0x37,0x07},{0x38,0x17},{0x39,0x06},{0x42,0x01},{0x46,0x2D},{0x47,0x0F},{0x48,0x3C},{0x49,0x00},{0x4A,0x1E},{0x4C,0x20},{0x51,0x10},{0x5E,0x10},{0x60,0x27},{0x80,0x42},{0x81,0x44},{0x82,0x04},{0x8B,0x01},{0x90,0x06},{0x95,0x0A},{0x96,0x0C},{0x97,0x05},{0x9A,0x14},{0x9C,0x3F},{0xA5,0x19},{0xCC,0x19},{0xCD,0x0B},{0xCE,0x13},{0xCF,0x64},{0xD0,0x21},{0xEF,0x01},{0x02,0x0F},{0x03,0x10},{0x04,0x02},{0x25,0x01},{0x27,0x39},{0x28,0x7F},{0x29,0x08},{0x3E,0xFF},{0x5E,0x3D},{0x65,0x96},{0x67,0x97},{0x69,0xCD},{0x6A,0x01},{0x6D,0x2C},{0x6E,0x01},{0x72,0x01},{0x73,0x35},{0x77,0x01},{0xEF,0x00}
};

void scanI2c() {
  int devices = 0;
  for (uint8_t address = 1; address < 127; ++address) {
    Wire.beginTransmission(address);
    if (Wire.endTransmission() == 0) {
      Serial.printf("I2C device: 0x%02X\n", address);
      ++devices;
    }
  }
  Serial.printf("I2C devices=%d\n", devices);
}

void oledCommand(uint8_t command) {
  Wire.beginTransmission(kOledAddress);
  Wire.write(0x00);
  Wire.write(command);
  Wire.endTransmission();
}

void drawOledPattern() {
  const uint8_t initSequence[] = {0xAE, 0x20, 0x00, 0x40, 0xA1, 0xC8, 0x81, 0x7F,
                                  0xA6, 0xA8, 0x3F, 0xD3, 0x00, 0xDA, 0x12, 0xD5,
                                  0x80, 0xD9, 0xF1, 0xDB, 0x40, 0x8D, 0x14, 0xAF};
  for (uint8_t command : initSequence) oledCommand(command);
  for (uint8_t page = 0; page < 8; ++page) {
    oledCommand(0xB0 | page); oledCommand(0x00); oledCommand(0x10);
    for (uint8_t chunk = 0; chunk < 8; ++chunk) {
      Wire.beginTransmission(kOledAddress); Wire.write(0x40);
      for (uint8_t column = 0; column < 16; ++column) Wire.write(((column + page) & 1) ? 0xAA : 0x55);
      Wire.endTransmission();
    }
  }
}

uint8_t pajRead(uint8_t reg) {
  Wire.beginTransmission(kPajAddress);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom(kPajAddress, static_cast<uint8_t>(1)) != 1) return 0xFF;
  return Wire.read();
}

void reportPajIdentity() {
  Serial.printf("PAJ7620 id=0x%02X 0x%02X (expected 0x20 0x76)\n", pajRead(0x00), pajRead(0x01));
}

bool pajWrite(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(kPajAddress);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool initPajGesture() {
  for (const auto &entry : kPajInit) {
    if (!pajWrite(entry[0], entry[1])) return false;
  }
  return true;
}

void pollPajGesture() {
  static unsigned long lastPoll = 0;
  if (millis() - lastPoll < 50) return;
  lastPoll = millis();
  const uint8_t gesture1 = pajRead(0x43);
  const uint8_t gesture2 = pajRead(0x44);
  if (gesture1 != 0 || gesture2 != 0) {
    Serial.printf("PAJ7620 gesture raw=0x%02X 0x%02X\n", gesture1, gesture2);
  }
}

void completeRadarFrame() {
  if (radarStats.frame[28] == 0x55 && radarStats.frame[29] == 0xCC) {
    ++radarStats.validFrames;
    uint8_t targets = 0;
    for (uint8_t slot = 0; slot < 3; ++slot) {
      bool nonzero = false;
      const size_t offset = 4 + slot * 8;
      for (uint8_t index = 0; index < 8; ++index) nonzero |= radarStats.frame[offset + index] != 0;
      if (nonzero) ++targets;
    }
    radarStats.lastTargets = targets;
  } else {
    ++radarStats.invalidFrames;
  }
  radarStats.frameLength = 0;
  radarStats.headerMatch = 0;
}

void drainRadarFrames() {
  constexpr uint8_t kHeader[] = {0xAA, 0xFF, 0x03, 0x00};
  while (radar.available()) {
    const uint8_t byteValue = static_cast<uint8_t>(radar.read());
    ++radarStats.bytes;
    if (radarStats.frameLength > 0) {
      radarStats.frame[radarStats.frameLength++] = byteValue;
      if (radarStats.frameLength == kRadarFrameBytes) completeRadarFrame();
      continue;
    }
    if (byteValue == kHeader[radarStats.headerMatch]) {
      if (++radarStats.headerMatch == sizeof(kHeader)) {
        memcpy(radarStats.frame, kHeader, sizeof(kHeader));
        radarStats.frameLength = sizeof(kHeader);
        ++radarStats.headers;
        radarStats.headerMatch = 0;
      }
    } else {
      radarStats.headerMatch = byteValue == kHeader[0] ? 1 : 0;
    }
  }
}

void sendRadarCommand(const uint8_t *payload, size_t length) {
  const uint8_t header[] = {0xFD, 0xFC, 0xFB, 0xFA};
  const uint8_t tail[] = {0x04, 0x03, 0x02, 0x01};
  radar.write(header, sizeof(header));
  radar.write(static_cast<uint8_t>(length & 0xFF));
  radar.write(static_cast<uint8_t>(length >> 8));
  radar.write(payload, length);
  radar.write(tail, sizeof(tail));
  radar.flush();
}

bool awaitRadarAck(uint16_t expectedCommand, uint32_t timeoutMs) {
  uint8_t buffer[96] = {};
  size_t used = 0;
  const unsigned long deadline = millis() + timeoutMs;
  while (static_cast<int32_t>(deadline - millis()) > 0) {
    while (radar.available()) {
      const uint8_t value = static_cast<uint8_t>(radar.read());
      ++radarStats.bytes;
      if (used == sizeof(buffer)) {
        memmove(buffer, buffer + 1, sizeof(buffer) - 1);
        --used;
      }
      buffer[used++] = value;
    }
    for (size_t start = 0; start + 10 <= used; ++start) {
      if (buffer[start] != 0xFD || buffer[start + 1] != 0xFC || buffer[start + 2] != 0xFB || buffer[start + 3] != 0xFA) continue;
      const uint16_t payloadLength = buffer[start + 4] | (static_cast<uint16_t>(buffer[start + 5]) << 8);
      const size_t total = 4 + 2 + payloadLength + 4;
      if (start + total > used) continue;
      const size_t tail = start + total - 4;
      if (buffer[tail] != 0x04 || buffer[tail + 1] != 0x03 || buffer[tail + 2] != 0x02 || buffer[tail + 3] != 0x01) continue;
      const uint16_t command = buffer[start + 6] | (static_cast<uint16_t>(buffer[start + 7]) << 8);
      const uint16_t status = payloadLength >= 4 ? buffer[start + 8] | (static_cast<uint16_t>(buffer[start + 9]) << 8) : 0xFFFF;
      Serial.printf("LD2453 ACK cmd=0x%04X status=%u length=%u\n", command, status, payloadLength);
      return command == expectedCommand && status == 0;
    }
    delay(2);
  }
  Serial.printf("LD2453 ACK timeout for cmd=0x%04X\n", expectedCommand);
  return false;
}

void verifyRadarTransmitPath() {
  delay(150);
  const uint8_t enableConfig[] = {0xFF, 0x00, 0x01, 0x00};
  const uint8_t readVersion[] = {0xA0, 0x00};
  const uint8_t endConfig[] = {0xFE, 0x00};
  while (radar.available()) radar.read();

  sendRadarCommand(enableConfig, sizeof(enableConfig));
  const bool enableOk = awaitRadarAck(0x01FF, 400);
  bool versionOk = false;
  if (enableOk) {
    sendRadarCommand(readVersion, sizeof(readVersion));
    versionOk = awaitRadarAck(0x01A0, 400);
  }
  sendRadarCommand(endConfig, sizeof(endConfig));
  const bool endOk = awaitRadarAck(0x01FE, 400);
  Serial.printf("LD2453 TX verification enable=%s version=%s exit=%s\n",
                enableOk ? "PASS" : "FAIL", versionOk ? "PASS" : "FAIL", endOk ? "PASS" : "FAIL");
}

void setup() {
  pinMode(kLedPin, OUTPUT);
  digitalWrite(kLedPin, LOW);
  Serial.begin(115200);
  delay(1200);
  Serial.println("SMARTOFFICE_V2_UART_TX_TEST");
  Wire.begin(kSdaPin, kSclPin);
  scanI2c(); reportPajIdentity();
  Serial.printf("PAJ7620 gesture init=%s\n", initPajGesture() ? "PASS" : "FAIL");
  drawOledPattern();
  radar.setRxBufferSize(2048);
  radar.begin(kRadarBaud, SERIAL_8N1, kRadarRxPin, kRadarTxPin);
  Serial.println("LD2453 TX test scheduled after startup stabilization");
}

void loop() {
  static unsigned long lastReport = 0;
  static bool radarTxTestDone = false;
  drainRadarFrames();
  pollPajGesture();
  if (!radarTxTestDone && millis() >= 5000) {
    radarTxTestDone = true;
    verifyRadarTransmitPath();
  }
  if (millis() - lastReport >= 5000) {
    lastReport = millis();
    Serial.printf("alive ms=%lu; LD2453 bytes=%lu headers=%lu valid=%lu invalid=%lu targets=%u\n",
                  millis(), radarStats.bytes, radarStats.headers, radarStats.validFrames,
                  radarStats.invalidFrames, radarStats.lastTargets);
  }
}



