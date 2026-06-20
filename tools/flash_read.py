import subprocess, serial, time, os

# Working directory: D:\SmartOffice_PeepPrevention\tools\
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

# Auto-rename firmware.bin → firmware_app.bin (PlatformIO outputs firmware.bin)
firmware_path = os.path.join(TOOLS_DIR, "firmware.bin")
firmware_app_path = os.path.join(TOOLS_DIR, "firmware_app.bin")
if os.path.exists(firmware_path):
    if os.path.exists(firmware_app_path):
        os.remove(firmware_app_path)
    os.rename(firmware_path, firmware_app_path)
    print("Renamed firmware.bin → firmware_app.bin")

# Flash
print("=== Flashing ===")
result = subprocess.run([
    "python", "-m", "esptool", "--chip", "esp32s3", "--port", "COM5",
    "--baud", "921600", "--before", "default-reset", "--after", "hard-reset",
    "write-flash",
    "0x0", os.path.join(TOOLS_DIR, "bootloader.bin"),
    "0x8000", os.path.join(TOOLS_DIR, "partitions.bin"),
    "0x10000", os.path.join(TOOLS_DIR, "firmware_app.bin"),
], capture_output=True, text=True)
print(result.stdout[-300:])
if result.returncode != 0:
    print(f"FLASH FAILED: {result.stderr}")
    exit(1)

# Wait for CDC enumeration
print("\n=== Serial (wait 5s, then 12s read) ===")
time.sleep(5)
ser = serial.Serial('COM5', 115200, timeout=2)
start = time.time()
lines = []
while time.time() - start < 12:
    try:
        line = ser.readline().decode('utf-8', errors='replace').strip()
        if line:
            lines.append(line)
            print(line)
    except:
        pass
ser.close()
print(f'\n=== {len(lines)} lines ===')
