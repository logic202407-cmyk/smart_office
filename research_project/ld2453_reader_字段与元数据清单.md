# LD2453 解析器 · 字段语义与元数据清单（修订建议）

> 本文件是对 `tools/ld2453_reader.py` / `tools/ld2453_reader.ps1` 的**修订建议**，供 Codex 决定是否采纳；**不覆盖**这两个文件。
>
> 事实基准以 Codex 已核验的 **LD2453 V1.0 手册**为准。本清单不把厂商宣传参数当作实验结果。

---

## 1. 已确认的协议事实（LD2453 V1.0 手册）

| 项 | 值 |
|---|---|
| 帧头 | `AA FF 03 00`（4 字节） |
| 目标记录 | 3 × 8 字节 |
| 帧尾 | `55 CC`（2 字节） |
| 帧长 | **30 字节** |
| 目标 8 字节 | x(2B) + y(2B) + speed(2B) + 第 4 字段(2B) |
| 第 4 字段 | 手册描述 “distance sampling length / pixel distance value” |
| 数值编码 | 符号-幅值：`bit15=符号`，幅值=`&0x7FFF`（x/y/speed） |
| 波特率 | 256000（8N1） |

现有解析器的帧结构、3×8 目标、符号-幅值解码与上述一致，**判定正确**。

---

## 2. 字段语义约定（分析时强制遵守，不改解析器字段名）

- `x_mm`、`y_mm`：**空间位置**——唯一用于空间判定（距离/分离/风险区）的字段。
- `speed_cm_s`：径向速度（符号-幅值），仅作趋势参考。
- `pixel_distance_mm`：手册的 “pixel distance value / distance sampling length”，**保留命名，仅记录**；**不得当作目标真实径向距离使用**（真实距离判据用 `y_mm`）。
- `slot`：帧内槽位编号 1–3，**不当作跨帧稳定的人**；跨帧关联需另行做目标关联（帧间集合匹配/匈牙利或“N 人计数”级保守输出）。

> 结论：现有 `pixel_distance_mm` 命名是保守且正确的，**不改名**；风险点只在“后续分析误把它当真实距离”，以本条约定消除。

---

## 3. 建议新增的输出（不破坏现有字段，向后兼容）

1. **同名 `metadata.json`**（与 `tools/ei_capture_serial/tcp` 的规范对齐）：
   ```json
   {
     "schema_version": "1.0",
     "trial_id": "ld2453_pilot_r01",
     "scenario": "single_target_known_distance",
     "transport": {"kind": "serial", "port": "COM7", "baud": 256000},
     "capture_started_utc": "...", "capture_finished_utc": "...",
     "clock_anchors": [{"wall_utc": "...", "monotonic_ms": 0}],
     "record_counts": {"ld2453_targets": 0, "parse_errors": 0},
     "target_count_histogram": {"0": 0, "1": 0, "2": 0, "3": 0},
     "data_status": "raw_complete_pending_annotation"
   }
   ```
2. **时钟锚点 `clock_anchor`**：采集开始/结束各打一条（墙钟 UTC ↔ 本地单调 ms），供视频/人工真值对齐。
3. **解析异常计数**：帧长 ≠30、尾非 `55 CC` 的事件计数并（可选）落盘异常片段，供排查。
4. 保留 `raw_hex` 与 `t_ms`（本地单调 ms）。

---

## 4. 上电校验步骤（产出 `ld2453_parser_validation.md`）

1. 单目标已知距离（如 1.0 m，卷尺/激光测距核对真值）静止实采 30 s。
2. 核对：帧长恒 30、尾恒 `55 CC`、目标数 ∈ {0,1,2,3}、`x/y` 量纲为 mm、符号约定与预期一致（人在雷达正前方时 `y>0`，左/右与 `x` 符号对应）。
3. 自测示例（官方手册示例帧）与实测帧**双向核对**，记录差异。
4. 结论写成 `PASS / REVISE`，作为解析器可用性依据；**此步是常规上电自检，不是“协议未核验”**（协议已由手册确认）。

---

## 5. 不改动清单（明确边界）

- **保留** `pixel_distance_mm` 字段名（与手册 “pixel distance value” 一致）。
- **不覆盖** `tools/ld2453_reader.ps1` 与 `tools/ld2453_reader.py`（是否采纳本清单由 Codex 决定）。
- 不把第 4 字段当真实径向距离（真实距离用 `y_mm`）。
