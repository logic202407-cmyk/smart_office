# Codex 侧草案（解析器元数据 / BOM / 复现 / 主目标时序伪代码）

> **重要声明**：本文件是**草案与模板**，供 Codex 采纳后自行实现、编译、实测。**以下代码片段未经编译、未经硬件实测，不声称可用**；是否采用、如何并入 `tools/ld2453_reader.*` 由 Codex 决定。本文件**不覆盖** `tools/ld2453_reader.ps1`，**不触碰** `D:\SmartOffice_PeepPrevention`。

---

## 1. 解析器元数据 + 时钟锚点增补（Python 草案，未编译）

> 目标：在现有 `ld2453_reader.py` 采集流程旁写同名 `.metadata.json` 与时钟锚点，不改字段名。

```python
# 仅示意增补逻辑，未编译/未实测
import json, time, datetime as dt

def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")

def write_metadata(path_meta, *, trial_id, scenario, port, baud,
                   start_utc, end_utc, anchors, record_counts, hist):
    meta = {
        "schema_version": "1.0",
        "trial_id": trial_id,
        "scenario": scenario,
        "transport": {"kind": "serial", "port": port, "baud": baud},
        "capture_started_utc": start_utc,
        "capture_finished_utc": end_utc,
        "clock_anchors": anchors,            # [{"wall_utc":..., "monotonic_ms":...}]
        "record_counts": record_counts,      # {"ld2453_targets": n, "parse_errors": m}
        "target_count_histogram": hist,      # {"0":a,"1":b,"2":c,"3":d}
        "data_status": "raw_complete_pending_annotation",
    }
    with open(path_meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

# 采集开始/结束各记一条 anchor：
#   anchors.append({"wall_utc": utc_now(), "monotonic_ms": time.monotonic_ns()//1_000_000})
# 解析异常：帧长!=30 或尾!=55CC 时 parse_errors += 1，不写入 JSONL（或写 type=parse_error 行）
```

> PowerShell 版对应要点（**不重写原 .ps1**）：在 `finally` 前写元数据；用 `Get-Date -AsUTC` 记墙钟；用 `Stopwatch.ElapsedMilliseconds` 记单调；异常帧计数用变量累加。

---

## 2. 主目标选择 + 时序风险判定（算法伪代码，非 ESP32 固件）

> 这是**算法设计**层草案，供 Codex 在固件/PC 端实现；不含 ESP-IDF 细节，未经烧录。

```
每帧 f:
  cands = [t for t in f.targets if t.y_mm > 0 and in_fov(t)]
  main  = min(cands, key=y) if cands else None        # 或预注册的 R-B/R-C
  if main and main.y <= R_risk:
      hold += dt; if hold >= T_dwell: base=1
  else:
      base=0; hold=0
  multi = 1 if (n_targets>=2 and second_y_diff <= D_near) else 0
  risk  = base AND/OR multi  (组合方式预注册)
```

---

## 3. BOM 模板（供 Codex 填写，DeepSeek 只出模板）

| 项 | 型号/规格 | 数量 | 备注 |
|---|---|---|---|
| 雷达 | HLK-LD2453（24 GHz，3.3 V，UART 256000） | 1 | 手册版本号：____ |
| 主控 | ESP32-S3 | 1 | 固件版本：____ |
| 串口 | CH340（3.3 V 逻辑） | 1 | 排线适配确认 |
| 支架 | 非金属、可调角度 | 1 | 刚性固定 |
| 电源 | USB-C 5V → 3.3V 稳压/去耦 | 1 | 雷达支路独立去耦 |
| 显示 | 待测终端/显示器 | 1 | 安装几何记录 |
| 测量 | 卷尺/激光测距/量角器/50cm 网格 | 各 1 | 真值 |

---

## 4. 复现实验说明模板（供 Codex 填写）

```
1. 硬件：BOM（上表）+ 安装几何（高度/横偏/俯仰/离地）照片编号。
2. 软件：固件版本、解析器版本、雷达工程参数（距离门/灵敏度/无人延时）、分析脚本版本。
3. 数据：原始 JSONL + metadata.json + 标注文件 + 视频索引（仅离线，知情同意）。
4. 流程：按《到货测试执行单_修订建议》试次矩阵 E0-A/E0-B/U1/UP-R/UP-L/UP2/NEG 执行。
5. 复跑：第三方按上述可在同一硬件重跑，输出同名文件与指标。
```

---

## 5. 分工红线（重申）

- 本文件一切代码/参数均为**草案**；**编译通过、烧录正常、串口可采、实验数值**均由 Codex 实测裁定。
- DeepSeek 不出“编译成功/串口数据/实验结果”结论。
