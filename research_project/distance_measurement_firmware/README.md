# 测距实验固件

这是用于 EI 论文第一阶段的“原始测距基线”固件，不是原 SmartOffice 防偷窥程序的替代版本。

## 行为

- 接收 LD2410B 的每个有效上报帧；
- 每帧输出一条 JSON 到 USB CDC（115200 baud）；
- `direct_distance_mm` 仅等于 LD2410B 原始 `detect_dist`；
- 当 `detect_dist` 为 0 时，`measurement_valid=false`，不会用 moving/static 字段替代；
- 同时输出 moving/static 距离和能量，供后续离线诊断；
- 不包含滤波、锁点、趋势、状态机、手势、OLED 或 PC 隐私动作。

## 这样做的原因

先获得可审计的传感器原始基线，才能严谨回答“一个简单滤波是否真的改善稳定性或延迟”。若直接加入复杂逻辑，论文无法区分改善来自雷达、安装环境还是算法本身。

## 部署方式

1. 保存现有 `firmware/src/main.cpp` 为带时间戳的备份。
2. 用本目录的 `main.cpp` 临时替换该文件。
3. 在 `D:\SmartOffice_PeepPrevention\firmware` 编译、烧录并保留构建日志。
4. 采集至少三个固定位置、每个位置三次的静止试验；每一试次使用唯一的 `trial_id`。
5. 完成原始基线后，恢复旧 `main.cpp`，或另建一个明确命名的滤波对照版本。

原隐私工程代码不应删除；测距实验与产品功能必须分开维护。
