# LD2453 Parser Validation

> 目的：区分“离线解析器自测”“手册/协议依据”“真实传感器上电实采”三类证据。本文件为新增独立验证记录。

## 1. 当前结论

**状态：PARTIAL / P1 未完成。**

已完成：

- PowerShell 解析器 self-test：PASS。
- `tools/ld2453_reader.ps1` 已支持有界采集与 metadata 输出参数。

未完成：

- LD2453 官方 PDF 未本地归档。
- 未确认 CH340/LD2453 所在 COM 口。
- 未执行真实 LD2453 30 秒串口采集。
- 未完成单目标已知位置 x/y 符号与量纲校验。

## 2. 离线 self-test

运行命令：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\tools\ld2453_reader.ps1 -SelfTest
```

输出：

```text
LD2453 parser self-test: PASS
```

解释：

- 该结果只证明示例帧解析逻辑与当前内置样例一致。
- 它不证明真实硬件已连接。
- 它不证明 LD2453 在实际场景中能分离多人。
- 它不替代 `UP-R` 正后方径向实采。

## 3. 当前解析器字段约定

`tools/ld2453_reader.ps1` 输出字段：

- `slot`：帧内槽位，不是跨帧身份。
- `x_mm`：目标 x 坐标，用于空间判定。
- `y_mm`：目标 y 坐标，用于空间判定。
- `speed_cm_s`：速度趋势。
- `pixel_distance_mm`：保留记录，不作为真实径向距离。
- `raw_hex`：30 字节原始帧十六进制。

## 4. PowerShell 采集器当前能力

新增参数：

- `-TrialId`
- `-Scenario`
- `-MetaOutput`
- `-DurationSeconds`

建议 30 秒通讯自检命令：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\tools\ld2453_reader.ps1 `
  -Port COMx `
  -Output .\ei_experiments\raw\ld2453_comm_selfcheck_r01.jsonl `
  -TrialId ld2453_comm_selfcheck_r01 `
  -Scenario comm_selfcheck `
  -DurationSeconds 30
```

将自动输出：

- `.jsonl`
- `.metadata.json`

metadata 包含：

- `schema_version`
- `trial_id`
- `scenario`
- `transport`
- `capture_started_utc`
- `capture_finished_utc`
- `clock_anchors`
- `record_counts.ld2453_targets`
- `record_counts.parse_errors`
- `target_count_histogram`
- `data_status`

## 5. 当前端口状态

本机当前可见串口：

- `COM3`
- `COM4`

未确认哪个端口对应 CH340/LD2453；本轮未盲连、未采集，避免污染验证记录。

## 6. 实采通过判据

通讯自检通过需要同时满足：

- 连续输出 `ld2453_targets`。
- `raw_hex` 长度为 60 个十六进制字符，即 30 字节。
- 帧尾为 `55cc`。
- `targets` 数组长度属于 `{0,1,2,3}`。
- metadata 中 `parse_errors` 可追溯。

## 7. 单目标位置校验

通讯自检通过后，再执行单目标已知位置校验：

- 一名目标站/坐在已测量位置，例如雷达正前方约 1.0 m。
- 使用地面网格 + 卷尺/激光测距记录真值。
- 核对 `y_mm` 是否为正且量级合理。
- 核对 `x_mm` 左右符号与坐标约定是否一致。
- 记录安装高度、俯仰角、横向偏移、照片编号。

该步骤通过后，才进入 E0/U1/UP-R pilot。

## 8. 当前阻塞项

1. LD2453 官方 PDF 本地归档。
2. 确认实际 CH340/LD2453 COM 口。
3. 接入真实 LD2453 硬件并执行 30 秒自检。

## 9. 裁定

当前只能裁定：

- `parser self-test = PASS`
- `real sensor validation = NOT RUN`
- `UP-R evidence = NOT RUN`
- `LD2410B negative control = NOT RUN`

因此总研究状态仍为 **REVISE**，不能进入 PASS。
