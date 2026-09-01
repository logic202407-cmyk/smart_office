# LD2453 V2 Board Revision Handoff

## Mission

Guide a manual EasyEDA V2 board revision that replaces the current HLK-LD2410B-P radar interface with an HLK-LD2453 multi-target radar interface. Also produce a firmware migration plan from the current LD2410B parser to the LD2453 UART protocol.

This package is evidence for design work, not a completed V2 design. Keep confirmed facts separate from design recommendations. Do not change module baud, reset the module, or flash firmware as part of the review.

## Confirmed Current Board Facts

The source netlist and schematic image are in `source_board/`.

Current radar part: `U2 = HLK-LD2410B-P`.

Current U2 wiring:

| Current pin | Net | Meaning |
|---|---|---|
| U2.5 VCC 5V | VIN | 5 V input rail |
| U2.4 GND | GND | Ground |
| U2.3 UART Rx | RX_RADAR | ESP32 IO18 UART TX to radar RX |
| U2.2 UART Tx | TX_RADAR | radar TX to ESP32 IO17 UART RX |
| U2.1 OUT | IO21 | LD2410B digital OUT signal |

The existing 5-pin connector footprint `U5` is also mapped as follows:

| U5 pin | Net |
|---|---|
| 1 | VIN (5 V) |
| 2 | GND |
| 3 | RX_RADAR |
| 4 | TX_RADAR |
| 5 | no net |

The board has an AMS1117-3.3 regulator: its input is `VIN` and its output is `+3.3V`.

## Confirmed LD2453 Facts

Use the two PDFs in `ld2453_reference/` as the authoritative protocol and module references.

* Module supply is 3.3 V only. Do not apply the existing 5 V `VIN` rail to LD2453 VCC.
* Module size is approximately 30 mm x 7 mm.
* It reports up to three target slots over UART; it does not provide the LD2410B-compatible `OUT` pin.
* The documentation states a 256000 baud default, but this physically tested module communicated successfully at 115200 baud, 8N1, on COM14. Treat 115200 as the current deployed-module setting and keep baud configurable in firmware.
* Valid raw report frames were observed with header `AA FF 03 00`, three target payload slots, and tail `55 CC`.

## Hardware Changes Required for V2

1. Remove or do not populate the LD2410B U2/U5 radar arrangement. Use an LD2453-specific footprint or a clearly labelled four-pin connector/landing pads.
2. Connect LD2453 `3.3V` only to board `+3.3V`. It must not connect to `VIN` or U5 pin 1.
3. Connect LD2453 `GND` to board GND.
4. Cross the UART signals exactly as follows:

| LD2453 pin | Board net | ESP32 direction |
|---|---|---|
| RX | RX_RADAR | ESP32 IO18 TX -> radar RX |
| TX | TX_RADAR | radar TX -> ESP32 IO17 RX |

5. Do not connect LD2453 to `IO21`; `IO21` only served the LD2410B `OUT` signal. Update/remove the old `PIN_RADAR_OUT` firmware dependency.
6. Do not assume LD2453 can be directly inserted into the old U5 holes. No four consecutive original U5 pins provide the required `3.3V, GND, RX, TX` mapping; U5 pin 1 is unsafe 5 V.
7. Verify the 3.3 V regulator budget for the existing ESP32/display/peripherals plus the LD2453 nominal current specified by the manual. Add local decoupling at the LD2453 supply pins according to the module reference and use short return paths.
8. Preserve an antenna-forward, open sensing direction. Keep copper, metal, enclosure features, cables, and other components out of the antenna radiation area as required by the module placement guidance. Do not place the module flat if the intended sensing direction is horizontal; the antenna face must point toward the monitored area.

## Firmware Baseline and Required Migration

The unmodified current baseline is in `firmware_baseline/`.

Current firmware facts:

* `config.h` uses ESP32 IO17 for radar TX, IO18 for radar RX, IO21 for radar OUT, and `RADAR_UART_BAUD 256000`.
* `ld2410b.h` and `ld2410b.cpp` implement the LD2410B protocol, not LD2453.
* `main.cpp` currently depends on the LD2410B driver.

Required firmware work:

1. Add a separate `ld2453.h/.cpp` driver instead of pretending the LD2453 is protocol compatible with LD2410B.
2. Keep IO17/IO18 if V2 retains `RX_RADAR` and `TX_RADAR`; use the verified 115200 baud setting for the tested module, but make the setting configurable.
3. Parse `AA FF 03 00` reports with exactly three 8-byte target slots and `55 CC` tail. Decode signed X/Y coordinates in mm, signed velocity in cm/s, and pixel distance in mm as defined in the protocol PDF.
4. Model target slots as frame-local observations. A target slot must not be treated as a persistent identity. Do not infer person identity, intention, or screen content.
5. Replace any `IO21`/OUT-based presence logic with LD2453 UART frame-derived target availability.
6. Preserve raw UART captures and add a repeatable 0/1/2/3-person validation table before claiming three-target operation.

## Current Hardware Validation Evidence

`validation_evidence/` contains the latest successful two-target record:

* `ICLM_MTT_Result_2026_08_19_10_20_28.txt`: parsed tool log. Slot 0 has 1891 valid records and slot 1 has 149 valid records. Slot 2 has no valid record in this capture.
* `RadarData_1.dat`: 84900-byte raw record paired with the successful run.
* `FILE_Radar_Config.ini`: paired tool configuration; COM14 and 115200 baud.
* `ld2453_reader.ps1`: local raw-frame inspection helper used during validation.

This proves observed two-slot LD2453 output under the successful geometry. It does not prove stable three-target operation or establish a module firmware version.

Successful physical geometry during the two-target run: antenna/PCB face vertical and facing the people, 30 mm long edge horizontal, 7 mm short edge vertical. A poor orientation can cause a real multi-target module to present only one target.

## Requested Output From GPT

1. A precise schematic-edit checklist for the existing EasyEDA design: components to remove/change/add, net labels, and the final LD2453 pin mapping.
2. A PCB placement/routing checklist, including the radar antenna direction and keepout review items.
3. A proposed LD2453 footprint/connector strategy compatible with hand assembly and the existing board constraints.
4. A firmware change plan or patch outline that preserves existing product logic while replacing the radar transport/parser.
5. A bring-up checklist that begins with power safety and UART frame validation before application-level testing.
6. A list of any information that must be obtained from the editable EasyEDA project before making claims about exact footprint coordinates, copper keepouts, or current capacity.

## Constraints

* Do not route 5 V `VIN` to LD2453.
* Do not direct-plug LD2453 into the old U5 connector footprint.
* Do not use LD2410B frame parsing for LD2453.
* Do not reset, update firmware, or change baud on the tested module without an explicit recovery plan.
* No editable EasyEDA project file is included: only netlists and a schematic export. Therefore exact board edits must remain a guided manual plan until the project source is supplied.
