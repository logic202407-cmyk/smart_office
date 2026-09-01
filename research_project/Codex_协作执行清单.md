# Codex × DeepSeek 协作执行清单（单页）

> 按 **P0 冻结 → 解析器 → 测试执行 → 论文** 四阶段排序。每条标注 **owner**：
> - **Codex**（主开发者）：真实硬件、PCB/网表核对、ESP32 固件、串口采集、实验执行、集成决策；
> - **DeepSeek**（协作者）：文献、研究设计、统计、独立审稿、风险审查。
>
> **DeepSeek 不对**硬件状态、编译/烧录、串口数据、实验数值下结论；这些一律以 Codex 实测为准。
> 引用文档：`deepseek_review.md`、`ld2453_到货测试执行单_修订建议.md`、`ld2453_reader_字段与元数据清单.md`、`预注册研究协议_雷达空间风险.md`、`EI_论文计划_RQ基线指标_对照修订稿.md`、`literature_review_radar_screen_privacy.md`。

---

## 阶段 0 · P0 冻结与到货前

- [ ] **【阻塞项·Codex】** 归档《HLK-LD2453 使用手册》+《串口通信协议》原版 PDF（含版本号）到工作区。（手册事实已核验：3.0–3.6 V 典型 3.3 V、7×30 mm、~76 mA、256000、三目标、30 字节帧、第 4 字段 “distance sampling length / pixel distance value”）
- [ ] **【Codex】** 与卖家确认 CH340 至雷达 VCC/UART 逻辑均为 3.3 V、排线适配。
- [ ] **【Codex】** 登记 V2 硬件架构“雷达支路 3.3 V 去耦滤波”与手册一致（已核验，无需改，仅记录）。
- [ ] **【Codex】** 建立论文实验专用 git 标签（DeepSeek 不执行任何 git 操作，此条仅列给 Codex）。
- [ ] **【DeepSeek】** 完成文献 DOI 逐条核验（投稿硬门槛，见文献文件）。

---

## 阶段 1 · 解析器（`ld2453_reader.py/.ps1`）

- [ ] **【Codex】** 保留 `pixel_distance_mm` 字段名（与手册 “pixel distance value” 一致，**不改名**）。
- [ ] **【Codex+DeepSeek 约定】** 分析时：空间位置只用 `x_mm/y_mm`；`pixel_distance_mm` 仅记录、不当真实径向距离；`slot` 不当跨帧稳定 ID。
- [ ] **【Codex】** 建议新增：同名 `metadata.json`（schema/trial_id/scenario/transport/起止/帧数/目标数分布）+ `clock_anchor`（墙钟 UTC↔本地 ms）+ 解析异常计数。是否采纳由 Codex 定。
- [ ] **【Codex】** 上电校验：单目标已知距离实采 → 核对帧长 30、尾 `55 CC`、x/y 量纲/符号约定 → 产出 `ld2453_parser_validation.md`。

---

## 阶段 2 · 测试执行（`ld2453_到货测试执行单_修订建议.md`）

- [ ] **【Codex】** 通讯自检：只接 3.3 V；记录 COM 号；`-SelfTest` PASS；30 s 实采判据=帧长恒 30、尾恒 `55 CC`、targets∈{0,1,2,3}。
- [ ] **【Codex】** 安装初值冻结：离地 1.5 m、横偏 30–50 cm、俯仰记录；地面 50 cm 网格 + 照片编号 + 干扰源位置。
- [ ] **【Codex】** 试次矩阵：E0-A（纯净）/ E0-B（带干扰）/ U1 / **UP-R 正后方径向对齐 0.5·1.0 m**（关键通过项）/ UP-L 侧后方 / UP2 动态 / **NEG=LD2410B 负对照**。
- [ ] **【Codex】** 真值+同步：卷尺/激光测距真值位置；事件打墙钟戳；采集端 `clock_anchor`；视频仅离线标注。
- [ ] **【Codex】** 量化判定：PASS/REVISE/NO-GO（NO-GO=UP-R 正后方连续复测仍无法 ≥2 可解释目标）。

---

## 阶段 3 · 论文（`EI_论文计划_RQ基线指标_对照修订稿.md` + 预注册协议）

- [ ] **【DeepSeek 定稿，Codex 确认】** RQ 扩展：新增 RQ4（多目标分离）、RQ5（目标关联+主目标选择）。
- [ ] **【DeepSeek】** 基线改为 B0（LD2410B 负对照锚点）→ B4（LD2453 完整）；“主目标选择”与“取最近目标”分离，规则采集前冻结。
- [ ] **【DeepSeek】** 指标补齐：多目标分离（≥2 目标帧占比、计数误差、MOTA/MOTP、y/x 差 MAE）、主目标识别正确率、负对照对比。
- [ ] **【DeepSeek 起草，采集前冻结】** 预注册协议 H1–H6 + 主/次指标 + 统计决策规则（配对比较、混合效应 `(1|参与者)+(1|位置)+(1|试次)`、FDR、H6 非劣效界）。
- [ ] **【DeepSeek】** 样本量：以 G*Power/Lakens 论证功效/CI 精度，替换“每条件 30 次”口头约定。
- [ ] **【Codex】** 独立复跑 + 方法学审查 + 引用/数据完整性审查（投稿硬门槛）。

---

## 依赖与阻塞

- **已解除**：LD2453 手册事实（供电/尺寸/帧格式/字段语义）——由 Codex 核验。
- **当前阻塞**：① 手册 PDF 落盘归档；② 到货后 `parser_validation.md`；③ UP-R 正后方实采（决定 REVISE→PASS 或 NO-GO）。
- **不可越界（全程）**：不识别身份、不推断意图、不做内容重建；厂商参数不当实验结果；只讲“空间风险”。

---

## 分工红线（一次写清）

| 事项 | 谁 |
|---|---|
| 硬件/PCB/网表/固件/串口/实验结论 | **Codex**（唯一） |
| 文献/研究设计/统计/审稿/风险 | **DeepSeek** |
| git 操作 | **Codex**（DeepSeek 不执行） |
| 是否覆盖 `ld2453_reader.ps1`、执行单、硬件架构 | **Codex** 决定；DeepSeek 只出“修订建议”新文件 |
