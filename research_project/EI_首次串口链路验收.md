# EI 首次串口链路验收

## 已核对的现行通信事实

- PC 端口：`COM13`（由操作者提供）。
- USB CDC 波特率：`115200`。
- 当前固件完整状态 JSON 在状态变化时发送；心跳每 5 秒发送一次。
- 采集工具：`tools/ei_capture_serial.py`，只读串口、不会向样机发送任何命令。

## 首次验收操作

1. 关闭正在占用 `COM13` 的串口助手或 PC 客户端。
2. 确认样机已上电，雷达正常工作。
3. 在本目录运行：

```powershell
.\tools\ei_capture_serial.ps1 -Port COM13 -TrialId link_check_001 -DurationSeconds 30 -Scenario link_check
```

4. 在 30 秒内依次完成：无人、进入雷达范围、靠近、离开。不要人为触发 PC 端遮罩/锁屏。
5. 验收通过标准：生成一对同名 `.jsonl` 与 `.metadata.json` 文件；JSONL 中至少有一条 `heartbeat`，并有合理的状态记录或诊断行。

## 当前限制

现行固件没有持续发送每帧传感器数据。因此首次验收只能证明 USB CDC 与状态事件链路可用，不能用于距离精度、滤波效果或 B0–B3 消融统计。链路验收通过后，再以最小、可回退的固件改动添加实验模式连续遥测。
