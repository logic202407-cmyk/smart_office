# EI 无线遥测验收（SoftAP + TCP）

## 目的与边界

本通道把 ESP32 已有的状态、工程帧和手势 JSONL **镜像**到单个 TCP 客户端。
它不接收控制命令；USB CDC 串口仍是原始调试与回退路径。Wi-Fi 断开不能停止雷达、OLED 或隐私状态机。

## 首次使用

1. 通过 USB 烧录新固件；烧录完成后，可用充电宝或 USB 电源给 ESP32 供电。
2. 电脑连接 ESP32 创建的 Wi-Fi：SSID `SmartOffice-Lab`，密码 `SmartOfficeLab`。
3. 在本目录运行（不要与同名旧试验号冲突）：

```powershell
& 'C:\Users\郑翔元\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\tools\ei_capture_tcp.py `
  --trial-id ipad_user_only_r01 `
  --duration 20 `
  --scenario ipad_11in_seated_user_only
```

4. 通过标准：`ei_experiments\raw\` 生成同名 `.jsonl` 与 `.metadata.json`；元数据中 `transport.kind` 为 `tcp`，并至少有状态 JSON 或工程 JSON。

## 台架可行性四组记录

每组 20 秒，保持 iPad、雷达和坐姿用户位置不变：

1. `ipad_user_only_r01`：用户独自静坐。
2. `ipad_second_person_100cm_r01`：第二人在用户身后约 1 m 静止。
3. `ipad_approach_hold_leave_r01`：第二人从后方走近，停留 3–5 秒后离开。
4. `ipad_side_passby_r01`：第二人从侧后方正常经过。

这些记录只验证安装几何与传感器可观测性，不用于声称屏幕可读性、隐私侵害或算法性能。
