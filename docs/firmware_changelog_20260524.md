# SmartOffice_PeepPrevention 固件修改记录

**日期：** 2026-05-24  
**项目：** SmartOffice_PeepPrevention（ESP32-S3 + LD2410B 雷达 + OLED）  
**工作目录：** `/mnt/d/SmartOffice_PeepPrevention/firmware`

---

## 问题背景

在真实办公室场景（机房教室，左右和后方均有其他人），LD2410B 雷达 FOV（~60°水平）内存在**多个目标**：

- **正前方目标**：走近/远离屏幕的人（需要跟踪的威胁目标）
- **旁边工位目标**：坐在相邻位置、处于静止状态的人（无害干扰）

雷达的 BOTH 状态用两个 gate 分别报告不同目标的距离。之前 `selectPrimaryDistanceMm()` 在 BOTH 状态下无条件偏向 `static_dist`，导致当旁边工位的人被静态 gate 捕获时，OLED 显示距离会**突然跳到 30-40cm**，即使正前方的目标还远在 78-150cm。

---

## 修改内容

### 1. 多目标场景下的锁相逻辑（本次核心修改）

**文件：** `src/main.cpp`，函数 `selectPrimaryDistanceMm()`

**原理：**

当两个 gate 距离差值超过阈值（>30% 且至少 >200mm），判定为**两个不同的人**，执行锁相：

- 计算 `moving_dist` 和 `static_dist` 各自与当前显示距离的差值
- **选择离当前显示距离更近的那个 gate**，维持跟踪连续性
- 避免显示距离从 150cm 突然跳到 30cm（跳到旁边同事身上）

**阈值设计：**
- `gap > max(larger * 30%, 200mm)`：间隙超过较大值的 30% 或 200mm（取大者）
- 200mm 下限防止微小波动触发锁相

**边界情况：**
- 两个 gate 数值接近（同一人的 moving + static）→ 走原有逻辑，优先 static
- `displayDistMm == 0`（首次启动）→ 选较远的目标（旁边工位更可能是近处干扰）

**代码位置：** `main.cpp` 第 56-100 行

---

### 2. 之前已完成的修改（回顾）

| 问题 | 修改 | 文件 |
|------|------|------|
| OLED 不更新 | flash 脚本文件名匹配 `firmware.bin`→`firmware_app.bin` | `E:\OneDrive\Desktop\flash_read.py` |
| OLED 卡死 | 移除 `Serial.flush()` 死锁 | `src/oled_ui.cpp` |
| OLED 丢失画面 | Wire 重置顺序：OLED 渲染前不再调 `restoreWireBus()` | `src/main.cpp` |
| OLED 渲染模式 | 改用 U8g2 标准 `firstPage()/nextPage()` 替代 `sendBuffer()` | `src/oled_ui.cpp` |
| 刷新率低 | `TRACK_PRINT_INTERVAL_MS` 从 150ms 降至 80ms | `src/main.cpp` |
| 远离方向跟踪滞后 | `selectPrimaryDistanceMm()` BOTH 状态优先 `static_dist` 而非 `min()` | `src/main.cpp` |
| 远离步长太小 | 远离方向 `maxStepAway=200`（是靠近方向 `maxStepNear=70` 的 2.85 倍） | `src/main.cpp` 平滑函数 |
| Serial 干扰 OLED | `render()` 中禁用所有 `Serial.print`，改用 LED 闪烁 | `src/oled_ui.cpp` |

---

## 锁相逻辑工作流程

```
雷达上报: moving_dist=670mm, static_dist=300mm, state=BOTH
              ↓
gap = |670 - 300| = 370mm
threshold = max(670 * 30%, 200) = max(201, 200) = 201mm
370 > 201 → 判定为两个不同的人
              ↓
当前 displayDistMm = 1325mm（上一帧显示）
diffMoving = |670 - 1325| = 655mm
diffStatic = |300 - 1325| = 1025mm
655 < 1025 → 选择 moving_dist = 670mm
              ↓
平滑函数: displayDistMm 从 1325 → 约1250mm（逐步过渡）
              ↓
OLED 显示: 125cm → 逐渐收敛到真实距离
```

---

## 编译 & 烧录信息

| 项目 | 值 |
|------|-----|
| 平台 | ESP32-S3-DevKitC-1 (8MB Flash, 无 PSRAM) |
| 最近编译大小 | RAM: 21180B (6.5%), Flash: 324089B (9.7%) |
| 编译命令 | `cd firmware && platformio run` |
| 烧录命令 | `cp .pio/build/.../firmware.bin → OneDrive/Desktop/` → `powershell.exe "python flash_read.py"` |

---

## 验证数据（串口输出关键帧）

```
t=5700  BOTH  static=30cm  moving=67cm  raw=67cm  display=125cm  ← 锁相选 moving
t=7793  BOTH  static=30cm  moving=79cm  raw=79cm  display=143cm  ← 锁相选 moving
t=13422 BOTH  static=38cm  moving=30cm  raw=38cm  display=116cm  ← gap小，走原逻辑
t=15355 BOTH  static=30cm  moving=87cm  raw=87cm  display=78cm   ← 锁相选 moving
```

**结论：** `static_dist=30cm` 的幽灵读数（旁边工位同事）被成功过滤，显示距离不再突然跳到 30-40cm。

---

## 后续可能的优化方向

1. **雷达安装角度调整**：物理缩小 FOV 覆盖范围（遮罩/定向天线）
2. **输入参数调节**：调整 LD2410B 的灵敏度阈值，减少远距离低能量误报
3. **轨迹预测**：引入卡尔曼滤波，基于历史轨迹判断目标是否为同一人
4. **多雷达方案**：双 LD2410B 交叉覆盖，区分正前方和侧方目标
