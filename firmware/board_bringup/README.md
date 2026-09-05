# SmartOffice V2 board bring-up diagnostic

This isolated PlatformIO project is for staged V2 board acceptance. It is not the production privacy-risk firmware.

## Confirmed on the assembled V2 board

- ESP32-S3 USB Serial/JTAG application and no-button automatic upload operate on COM15.
- OLED at I2C 0x3C renders a test pattern.
- PAJ7620 at I2C 0x73 reports ID 0x20 0x76 and emitted raw gesture values 0x04/0x08 during a left/right hand-wave test.
- LD2453 reports complete 30-byte frames at 115200 baud to ESP GPIO17; observed frames had valid AA FF 03 00 and 55 CC delimiters with no invalid frames in the capture.

## Open items

- LD2453 configuration-command receive path remains unresolved. The reversible exit-config command returned ACK, while enable-config and firmware-version queries timed out. Do not claim bidirectional command control is verified.
- LED2 did not visibly blink when GPIO1 was toggled; deferred for hardware inspection.
- U5 is a passive expansion header and needs an attached device or loopback for an electrical functional test.

## Use

The ESP32-S3 is configured in the V1-compatible USB Serial/JTAG mode. Use COM15 for monitoring and automatic upload. Do not retain the temporary ARDUINO_USB_MODE=0 test override.
