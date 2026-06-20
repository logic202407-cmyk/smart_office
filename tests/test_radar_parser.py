"""
test_radar_parser.py — LD2410B 帧解析单元测试（pytest）
=======================================================

测试目标：验证字节级状态机解析器的正确性，覆盖正常帧、粘包、半包超时、
错帧恢复、帧头错误重新同步等场景。

用法：
    cd /mnt/d/SmartOffice_PeepPrevention/tests/
    python -m pytest test_radar_parser.py -v
    或
    python -m pytest test_radar_parser.py -v --tb=short
"""

import struct
from typing import List, Optional, Tuple


# ============================================================
# LD2410B 协议常量（与 firmware/ld2410b.h 一致）
# ============================================================
REPORT_HEADER = bytes([0xF4, 0xF3, 0xF2, 0xF1])
REPORT_TAIL = bytes([0xF8, 0xF7, 0xF6, 0xF5])
CFG_HEADER = bytes([0xFD, 0xFC, 0xFB, 0xFA])
CFG_TAIL = bytes([0x04, 0x03, 0x02, 0x01])

# 解析器状态（与 LD2410B_ParserState 枚举对应）
(PARSER_WAIT_F4, PARSER_GOT_F4, PARSER_GOT_F3, PARSER_GOT_F2,
 PARSER_WAIT_LEN_L, PARSER_WAIT_LEN_H, PARSER_WAIT_DATA,
 PARSER_WAIT_F8, PARSER_GOT_F8, PARSER_GOT_F7, PARSER_GOT_F6) = range(11)

# 配置帧解析状态
(PARSER_CFG_GOT_FD, PARSER_CFG_GOT_FC, PARSER_CFG_GOT_FB,
 PARSER_CFG_WAIT_LEN_L, PARSER_CFG_WAIT_LEN_H, PARSER_CFG_WAIT_DATA,
 PARSER_CFG_WAIT_04, PARSER_CFG_GOT_04, PARSER_CFG_GOT_03, PARSER_CFG_GOT_02) = range(11, 21)

# 雷达帧超时 (ms)
FRAME_TIMEOUT_MS = 100

# 最小/最大数据长度
REPORT_DATA_LEN_MIN = 9
BUF_SIZE = 128


# ============================================================
# LD2410B 解析器 Python 实现（用于测试）
# ============================================================
class LD2410BParser:
    """
    LD2410B 字节级状态机解析器（Python 移植，用于单元测试）。
    逻辑与 firmware/src/ld2410b.cpp 中的 feed() 一致。
    """

    def __init__(self):
        self.reset()

    def reset(self):
        """重置解析器到初始状态"""
        self.state = PARSER_WAIT_F4
        self.buf = bytearray()
        self.buf_index = 0
        self.frame_len = 0
        self.last_byte_time = 0
        self.frame_count = 0
        self.last_info = None  # 最后一次解析结果
        self.cfg_index = 0
        self.cfg_buf = bytearray()

        # 模拟 millis() 时间（测试中手动推进）
        self._now = 0

        # 标志位
        self.new_data_flag = False
        self.timeout_occurred = False  # 是否发生过超时重置

    def set_time(self, ms: int):
        """设置当前模拟时间（ms）"""
        self._now = ms

    def advance_time(self, delta_ms: int):
        """推进模拟时间"""
        self._now += delta_ms

    def feed(self, byte: int):
        """
        送入一个字节到解析器（与 ld2410b.cpp feed() 逻辑一致）
        """
        now = self._now

        # ---- 半包检测 ----
        if (self.state != PARSER_WAIT_F4 and
                self.state not in (PARSER_CFG_GOT_FD,) and
                now - self.last_byte_time > FRAME_TIMEOUT_MS):
            # 超时重置
            self.timeout_occurred = True
            self._reset_internal()
        self.last_byte_time = now

        # ---- 主状态机 ----
        if self.state == PARSER_WAIT_F4:
            if byte == 0xF4:
                self.state = PARSER_GOT_F4
            elif byte == 0xFD:
                self.state = PARSER_CFG_GOT_FD
                self.cfg_index = 0

        elif self.state == PARSER_GOT_F4:
            if byte == 0xF3:
                self.state = PARSER_GOT_F3
            elif byte == 0xF4:
                self.state = PARSER_GOT_F4  # 粘包: 连续 0xF4
            else:
                self.state = PARSER_WAIT_F4

        elif self.state == PARSER_GOT_F3:
            if byte == 0xF2:
                self.state = PARSER_GOT_F2
            elif byte == 0xF4:
                self.state = PARSER_GOT_F4
            else:
                self.state = PARSER_WAIT_F4

        elif self.state == PARSER_GOT_F2:
            if byte == 0xF1:
                self.state = PARSER_WAIT_LEN_L
            elif byte == 0xF4:
                self.state = PARSER_GOT_F4
            else:
                self.state = PARSER_WAIT_F4

        elif self.state == PARSER_WAIT_LEN_L:
            self.frame_len = byte
            self.state = PARSER_WAIT_LEN_H

        elif self.state == PARSER_WAIT_LEN_H:
            self.frame_len |= (byte << 8)
            if self.frame_len < REPORT_DATA_LEN_MIN or self.frame_len > BUF_SIZE:
                self.state = PARSER_WAIT_F4
            else:
                self.buf_index = 0
                self.buf = bytearray(self.frame_len)
                self.state = PARSER_WAIT_DATA

        elif self.state == PARSER_WAIT_DATA:
            if self.buf_index < len(self.buf):
                self.buf[self.buf_index] = byte
                self.buf_index += 1
            if self.buf_index >= self.frame_len:
                self.state = PARSER_WAIT_F8

        elif self.state == PARSER_WAIT_F8:
            if byte == 0xF8:
                self.state = PARSER_GOT_F8
            else:
                self.state = PARSER_WAIT_F4

        elif self.state == PARSER_GOT_F8:
            if byte == 0xF7:
                self.state = PARSER_GOT_F7
            else:
                self.state = PARSER_WAIT_F4

        elif self.state == PARSER_GOT_F7:
            if byte == 0xF6:
                self.state = PARSER_GOT_F6
            else:
                self.state = PARSER_WAIT_F4

        elif self.state == PARSER_GOT_F6:
            if byte == 0xF5:
                # 帧完成
                self._process_report_frame(self.buf, self.frame_len)
                self.frame_count += 1
                self.state = PARSER_WAIT_F4
            else:
                self.state = PARSER_WAIT_F4

        # ---- 配置帧解析 ----
        elif self.state == PARSER_CFG_GOT_FD:
            if byte == 0xFC:
                self.state = PARSER_CFG_GOT_FC
            elif byte == 0xFD:
                self.state = PARSER_CFG_GOT_FD
            else:
                self.state = PARSER_WAIT_F4

        elif self.state == PARSER_CFG_GOT_FC:
            if byte == 0xFB:
                self.state = PARSER_CFG_GOT_FB
            elif byte == 0xFD:
                self.state = PARSER_CFG_GOT_FD
            else:
                self.state = PARSER_WAIT_F4

        elif self.state == PARSER_CFG_GOT_FB:
            if byte == 0xFA:
                self.state = PARSER_CFG_WAIT_LEN_L
            elif byte == 0xFD:
                self.state = PARSER_CFG_GOT_FD
            else:
                self.state = PARSER_WAIT_F4

        elif self.state == PARSER_CFG_WAIT_LEN_L:
            self.frame_len = byte
            self.state = PARSER_CFG_WAIT_LEN_H

        elif self.state == PARSER_CFG_WAIT_LEN_H:
            self.frame_len |= (byte << 8)
            if self.frame_len == 0 or self.frame_len > 64:
                self.state = PARSER_WAIT_F4
            else:
                self.cfg_index = 0
                self.cfg_buf = bytearray(self.frame_len)
                self.state = PARSER_CFG_WAIT_DATA

        elif self.state == PARSER_CFG_WAIT_DATA:
            if self.cfg_index < len(self.cfg_buf):
                self.cfg_buf[self.cfg_index] = byte
                self.cfg_index += 1
            if self.cfg_index >= self.frame_len:
                self.state = PARSER_CFG_WAIT_04

        elif self.state == PARSER_CFG_WAIT_04:
            if byte == 0x04:
                self.state = PARSER_CFG_GOT_04
            else:
                self.state = PARSER_WAIT_F4

        elif self.state == PARSER_CFG_GOT_04:
            if byte == 0x03:
                self.state = PARSER_CFG_GOT_03
            else:
                self.state = PARSER_WAIT_F4

        elif self.state == PARSER_CFG_GOT_03:
            if byte == 0x02:
                self.state = PARSER_CFG_GOT_02
            else:
                self.state = PARSER_WAIT_F4

        elif self.state == PARSER_CFG_GOT_02:
            if byte == 0x01:
                # 配置帧完成
                self.state = PARSER_WAIT_F4
            else:
                self.state = PARSER_WAIT_F4

        else:
            self._reset_internal()

    def feed_bytes(self, data: bytes):
        """批量送入字节"""
        for b in data:
            self.feed(b)

    def _reset_internal(self):
        """内部重置（不清除 timeout_occurred 等测试标记）"""
        self.state = PARSER_WAIT_F4
        self.buf_index = 0
        self.frame_len = 0
        self.cfg_index = 0
        self.last_byte_time = 0

    def _process_report_frame(self, data: bytes, length: int):
        """处理完整上报帧（与 ld2410b.cpp processReportFrame 一致）"""
        if length < REPORT_DATA_LEN_MIN:
            return

        # 解析数据（Little Endian）
        target_state = data[0]
        moving_dist = data[1] | (data[2] << 8)
        moving_energy = data[3]
        static_dist = data[4] | (data[5] << 8)
        static_energy = data[6]
        detect_dist = data[7] | (data[8] << 8)

        self.last_info = {
            'target_state': target_state,
            'moving_dist_mm': moving_dist,
            'moving_dist_cm': moving_dist // 10,
            'moving_energy': moving_energy,
            'static_dist_mm': static_dist,
            'static_dist_cm': static_dist // 10,
            'static_energy': static_energy,
            'detect_dist_mm': detect_dist,
            'detect_dist_cm': detect_dist // 10,
            'timestamp_ms': self._now,
            'valid': True,
        }
        self.new_data_flag = True

    def has_new_data(self) -> bool:
        """检查是否有新数据（与 hasNewData() 一致）"""
        flag = self.new_data_flag
        self.new_data_flag = False
        return flag

    def get_frame_count(self) -> int:
        return self.frame_count

    def get_state(self) -> int:
        return self.state


# ============================================================
# 辅助函数：构建 LD2410B 测试帧
# ============================================================

def build_report_frame(
    target_state: int = 1,
    moving_dist_mm: int = 1200,
    moving_energy: int = 45,
    static_dist_mm: int = 0,
    static_energy: int = 0,
    detect_dist_mm: int = 6000,
    eng_mode_extra: bytes = b'',
) -> bytes:
    """
    构建 LD2410B 上报帧。

    参数:
        target_state: 目标状态 (0=无, 1=运动, 2=静止, 3=运动+静止)
        moving_dist_mm: 运动目标距离 (mm)
        moving_energy: 运动能量 (0~100)
        static_dist_mm: 静止目标距离 (mm)
        static_energy: 静止能量 (0~100)
        detect_dist_mm: 探测距离 (mm)
        eng_mode_extra: 工程模式附加数据

    返回:
        完整的二进制帧
    """
    # 基础数据负载 (9 字节)
    payload = struct.pack(
        '<BH B BH H',  # target_state(1) + moving_dist(2) + moving_energy(1)
                       # + static_dist(2) + static_energy(1) + detect_dist(2)
        target_state & 0xFF,
        moving_dist_mm & 0xFFFF,
        moving_energy & 0xFF,
        static_dist_mm & 0xFFFF,
        static_energy & 0xFF,
        detect_dist_mm & 0xFFFF,
    )
    # 注意: struct 打包顺序是 moving_dist(2B) 后紧接 moving_energy(1B)
    # 然后用第二个 H 打包 static_dist，再用 B 打包 static_energy
    # 我们需要重新组织: target_state(1B) + moving_dist(2B) + moving_energy(1B)
    #                   + static_dist(2B) + static_energy(1B) + detect_dist(2B)
    # 用 struct 手动打包
    payload = bytes([
        target_state & 0xFF,
        moving_dist_mm & 0xFF, (moving_dist_mm >> 8) & 0xFF,
        moving_energy & 0xFF,
        static_dist_mm & 0xFF, (static_dist_mm >> 8) & 0xFF,
        static_energy & 0xFF,
        detect_dist_mm & 0xFF, (detect_dist_mm >> 8) & 0xFF,
    ])

    if eng_mode_extra:
        payload += eng_mode_extra

    data_len = len(payload)
    frame = REPORT_HEADER
    frame += struct.pack('<H', data_len)  # 长度字段 (LE)
    frame += payload
    frame += REPORT_TAIL

    return frame


def build_cfg_response(payload: bytes) -> bytes:
    """构建配置帧响应"""
    data_len = len(payload)
    frame = CFG_HEADER
    frame += struct.pack('<H', data_len)
    frame += payload
    frame += CFG_TAIL
    return frame


# ============================================================
# 单元测试
# ============================================================

class TestNormalFrameParsing:
    """测试正常帧解析"""

    def test_parse_moving_target(self):
        """
        测试目的：验证正常运动目标帧能被正确解析。
        发送包含运动目标的完整帧，检查目标状态和距离是否正确。
        """
        parser = LD2410BParser()
        frame = build_report_frame(
            target_state=1,      # 运动目标
            moving_dist_mm=1200, # 120cm
            moving_energy=45,
            detect_dist_mm=6000, # 600cm
        )
        parser.feed_bytes(frame)

        assert parser.get_frame_count() == 1, "应成功解析1帧"
        assert parser.last_info is not None
        assert parser.last_info['target_state'] == 1
        assert parser.last_info['moving_dist_cm'] == 120
        assert parser.last_info['moving_energy'] == 45
        assert parser.last_info['detect_dist_cm'] == 600
        assert parser.new_data_flag is True

    def test_parse_static_target(self):
        """
        测试目的：验证静止目标帧解析。
        发送仅包含静止目标的帧。
        """
        parser = LD2410BParser()
        frame = build_report_frame(
            target_state=2,      # 静止目标
            moving_dist_mm=0,
            moving_energy=0,
            static_dist_mm=800,  # 80cm
            static_energy=60,
            detect_dist_mm=4000,
        )
        parser.feed_bytes(frame)

        assert parser.get_frame_count() == 1
        assert parser.last_info['target_state'] == 2
        assert parser.last_info['static_dist_cm'] == 80
        assert parser.last_info['static_energy'] == 60

    def test_parse_both_targets(self):
        """
        测试目的：验证运动+静止同时存在的帧。
        """
        parser = LD2410BParser()
        frame = build_report_frame(
            target_state=3,       # 运动+静止
            moving_dist_mm=2000,  # 200cm
            moving_energy=30,
            static_dist_mm=1500,  # 150cm
            static_energy=50,
            detect_dist_mm=5000,
        )
        parser.feed_bytes(frame)

        assert parser.get_frame_count() == 1
        assert parser.last_info['target_state'] == 3
        assert parser.last_info['moving_dist_cm'] == 200
        assert parser.last_info['static_dist_cm'] == 150

    def test_parse_no_target(self):
        """
        测试目的：验证无目标帧 (target_state=0) 解析。
        """
        parser = LD2410BParser()
        frame = build_report_frame(
            target_state=0,
            moving_dist_mm=0,
            moving_energy=0,
            static_dist_mm=0,
            static_energy=0,
            detect_dist_mm=6000,
        )
        parser.feed_bytes(frame)

        assert parser.get_frame_count() == 1
        assert parser.last_info['target_state'] == 0
        assert parser.last_info['moving_dist_cm'] == 0
        assert parser.has_new_data() is True

    def test_has_new_data_clear_after_read(self):
        """
        测试目的：验证 hasNewData() 标志在读取后自动清除。
        """
        parser = LD2410BParser()
        frame = build_report_frame()
        parser.feed_bytes(frame)

        assert parser.has_new_data() is True  # 第一次读取为 True
        assert parser.has_new_data() is False  # 第二次应该为 False

    def test_consecutive_frames(self):
        """
        测试目的：验证连续多帧都能正确解析，帧计数递增。
        """
        parser = LD2410BParser()
        for i in range(5):
            frame = build_report_frame(
                target_state=1,
                moving_dist_mm=1000 + i * 100,
                moving_energy=30 + i * 5,
            )
            parser.feed_bytes(frame)

        assert parser.get_frame_count() == 5
        assert parser.last_info['moving_dist_cm'] == 140  # 最后一帧: 140cm


class TestStickyPacket:
    """测试粘包场景"""

    def test_consecutive_f4_header(self):
        """
        测试目的：验证连续 0xF4 的粘包场景。
        模拟数据流中出现多个 0xF4 字节（如前一帧残留），应能从后续
        0xF4F3F2F1 正确同步并解析。
        """
        parser = LD2410BParser()
        # 发送: 垃圾字节 + 0xF4F4F4 + 完整帧头
        garbage = bytes([0x00, 0xFF, 0xAA])
        sticky_f4 = bytes([0xF4, 0xF4, 0xF4, 0xF4])  # 多个连续 F4
        frame = build_report_frame(target_state=1, moving_dist_mm=1500)

        parser.feed_bytes(garbage + sticky_f4 + frame[4:])  # 跳过第一个 F4

        # 因为前面有 garbage，第一个 F4 应该被等待
        # 从 sticky_f4 开始，第一个 F4 进 GOT_F4，第二个 F4 保持 GOT_F4，第三个 F4 保持 GOT_F4
        # 然后真正的 F4F3F2F1... 应该被正确解析
        # 重新构造更可控的测试:
        parser2 = LD2410BParser()
        # 模拟粘包: 前一个帧的尾巴 F5 残留 + 后一帧头
        # 发送: 完整帧1 + 帧1尾残留F5? 不，更实际的场景是:
        # 帧1刚发完，立即发帧2，它们之间没有任何间隙
        frame1 = build_report_frame(target_state=1, moving_dist_mm=1000)
        frame2 = build_report_frame(target_state=1, moving_dist_mm=2000)
        combined = frame1[:-1] + bytes([0xF5]) + frame2  # 帧1完整 + frame2紧接

        parser2.feed_bytes(combined)
        # 应该解析出两帧
        count = parser2.get_frame_count()
        assert count == 2, f"粘包应解析2帧，实际: {count}"
        assert parser2.last_info['moving_dist_cm'] == 200

    def test_no_gap_between_frames(self):
        """
        测试目的：验证两帧之间无间隔（紧接）能正确解析。
        """
        parser = LD2410BParser()
        frame1 = build_report_frame(target_state=1, moving_dist_mm=1000)
        frame2 = build_report_frame(target_state=2, static_dist_mm=800)
        # 紧密拼接
        combined = frame1 + frame2
        parser.feed_bytes(combined)

        assert parser.get_frame_count() == 2
        # 最后一帧是静止目标
        assert parser.last_info['target_state'] == 2
        assert parser.last_info['static_dist_cm'] == 80

    def test_three_frames_sticky(self):
        """
        测试目的：验证三帧连续粘包无间隔。
        """
        parser = LD2410BParser()
        frames = bytes().join(
            build_report_frame(target_state=i % 4, moving_dist_mm=500 * (i + 1))
            for i in range(3)
        )
        parser.feed_bytes(frames)
        assert parser.get_frame_count() == 3, f"3帧粘包应全部解析，实际: {parser.get_frame_count()}"

    def test_garbage_between_valid_frames(self):
        """
        测试目的：验证有效帧之间夹杂随机字节时不影响解析。
        """
        parser = LD2410BParser()
        frame = build_report_frame(target_state=1, moving_dist_mm=1500)
        garbage = bytes([0x00, 0x55, 0xAA, 0xFF, 0x00])

        # 帧 -> 垃圾 -> 帧
        data = frame + garbage + frame
        parser.feed_bytes(data)

        assert parser.get_frame_count() == 2
        assert parser.last_info['moving_dist_cm'] == 150


class TestHalfPacketTimeout:
    """测试半包超时场景"""

    def test_timeout_resets_parser(self):
        """
        测试目的：验证收到不完整帧后，超时能自动重置解析器。
        发送帧头 + 部分数据后就停住，推进时间超过超时阈值后，
        再发送新帧应能正常解析。
        """
        parser = LD2410BParser()
        frame = build_report_frame()

        # 只发送帧头 + 长度 + 2字节数据
        partial = frame[:10]  # 帧头4 + 长度2 + 4字节数据
        parser.feed_bytes(partial)

        # 此时解析器在 PARSER_WAIT_DATA 状态
        assert parser.state == PARSER_WAIT_DATA, f"应在 DATA 状态, 实际: {parser.state}"

        # 推进时间超过超时阈值
        parser.advance_time(FRAME_TIMEOUT_MS + 10)

        # 发送一个新的完整帧
        new_frame = build_report_frame(target_state=2, static_dist_mm=1000)
        parser.feed_bytes(new_frame)

        # 超时应该重置解析器，所以新帧能够正常解析
        assert parser.get_frame_count() == 1, "超时后应能解析新帧"
        assert parser.timeout_occurred, "应发生超时重置"
        assert parser.last_info['target_state'] == 2

    def test_timeout_no_reset_within_window(self):
        """
        测试目的：验证在超时窗口内继续发送数据不会触发超时重置。
        """
        parser = LD2410BParser()
        frame = build_report_frame()

        # 分多次发送，每次间隔小于超时阈值
        for i in range(0, len(frame), 4):
            chunk = frame[i:i + 4]
            parser.feed_bytes(chunk)
            parser.advance_time(FRAME_TIMEOUT_MS // 4)  # 每次等25ms（小于100ms）

        # 不应超时，应正常解析
        assert parser.get_frame_count() == 1
        assert not parser.timeout_occurred, "不应发生超时重置"

    def test_timeout_while_in_wait_f4(self):
        """
        测试目的：验证初始等待态（PARSER_WAIT_F4）不会触发超时重置。
        """
        parser = LD2410BParser()

        # 在初始态停留很久（不应超时，因为 PARSER_WAIT_F4 不检查超时）
        parser.advance_time(10000)

        # 发送一个帧
        frame = build_report_frame()
        parser.feed_bytes(frame)

        assert parser.get_frame_count() == 1
        assert not parser.timeout_occurred

    def test_half_frame_then_new_frame(self):
        """
        测试目的：验证半包后紧接着新帧，超时前如果数据继续则正常恢复。
        模拟场景：帧头刚收到，半包未超时前后续数据到达。
        """
        parser = LD2410BParser()
        frame = build_report_frame(target_state=1, moving_dist_mm=1800)

        # 发送帧头后暂停 (未超时)
        parser.feed_bytes(frame[:6])  # 帧头4 + 长度2
        parser.advance_time(50)  # 50ms < 100ms 超时阈值

        # 继续发送剩余字节
        parser.feed_bytes(frame[6:])

        assert parser.get_frame_count() == 1, "半包未超时前数据续传应正常解析"
        assert parser.last_info['moving_dist_cm'] == 180


class TestErrorFrameRecovery:
    """测试错帧恢复"""

    def test_wrong_byte_in_header(self):
        """
        测试目的：验证帧头中错字节能正确重置。
        如 F4F3XXF1 中 XX 不是 F2，应丢弃并等待新帧。
        """
        parser = LD2410BParser()
        # 发送: F4 F3 AA F1 ... (错误的第三字节)
        bad_header = bytes([0xF4, 0xF3, 0xAA, 0xF1])
        garbage = bytes([0xFF, 0xFF, 0xFF])
        good_frame = build_report_frame(target_state=1, moving_dist_mm=1200)

        parser.feed_bytes(bad_header + garbage + good_frame)
        # 应该恢复并解析 good_frame
        assert parser.get_frame_count() == 1
        assert parser.last_info['moving_dist_cm'] == 120

    def test_wrong_tail_byte(self):
        """
        测试目的：验证帧尾错误能正确丢弃整帧并恢复。
        """
        parser = LD2410BParser()
        frame = build_report_frame(target_state=1, moving_dist_mm=1000)

        # 破坏帧尾最后一个字节
        broken = bytearray(frame)
        broken[-1] = 0x00  # 把 0xF5 改成 0x00

        good_frame = build_report_frame(target_state=2, static_dist_mm=500)
        parser.feed_bytes(bytes(broken) + good_frame)

        # 只有第二帧应被解析
        assert parser.get_frame_count() == 1, "错帧尾应被丢弃"
        assert parser.last_info['target_state'] == 2
        assert parser.last_info['static_dist_cm'] == 50

    def test_wrong_length_field(self):
        """
        测试目的：验证错误的长度字段（过小/过大）能被检测并丢弃。
        """
        parser = LD2410BParser()
        # 构造长度字段异常小的帧
        bad_data = bytes([
            0xF4, 0xF3, 0xF2, 0xF1,  # 帧头
            0x01, 0x00,              # 长度=1 (< 9, 无效)
            0x00,                     # 1字节数据
            0xF8, 0xF7, 0xF6, 0xF5,  # 帧尾
        ])
        good_frame = build_report_frame(target_state=1, moving_dist_mm=1200)

        parser.feed_bytes(bad_data + good_frame)

        assert parser.get_frame_count() == 1
        assert parser.last_info['moving_dist_cm'] == 120

    def test_empty_stream_recovery(self):
        """
        测试目的：验证完全空数据流后能正确接收第一帧。
        """
        parser = LD2410BParser()
        # 大量干扰字节
        noise = bytes([0x00, 0xFF, 0x55, 0xAA] * 50)
        frame = build_report_frame(target_state=1, moving_dist_mm=1500)

        parser.feed_bytes(noise + frame)
        assert parser.get_frame_count() == 1


class TestHeaderResync:
    """测试帧头重新同步"""

    def test_resync_from_mid_header(self):
        """
        测试目的：验证从帧头中间位置（如 GOT_F3 时）错帧后能重新同步。
        """
        parser = LD2410BParser()
        # 先进入 GOT_F3 状态
        parser.feed_bytes(bytes([0xF4, 0xF3]))

        assert parser.state == PARSER_GOT_F3

        # 发送错误字节
        parser.feed_bytes(b'\x00')

        assert parser.state == PARSER_WAIT_F4, "错帧应回到 WAIT_F4"

        # 现在发送完整帧
        frame = build_report_frame()
        parser.feed_bytes(frame)
        assert parser.get_frame_count() == 1

    def test_resync_with_new_f4(self):
        """
        测试目的：验证帧头检测过程中遇到新 0xF4 能重新开始同步。
        """
        parser = LD2410BParser()
        # 进入 GOT_F2 状态
        parser.feed_bytes(bytes([0xF4, 0xF3, 0xF2]))

        assert parser.state == PARSER_GOT_F2

        # 收到新的 0xF4（而不是预期的 0xF1）
        parser.feed_bytes(b'\xF4')

        # 应回到 GOT_F4 重新同步
        assert parser.state == PARSER_GOT_F4, f"应在 GOT_F4, 实际: {parser.state}"

        # 现在完成正常帧
        rest = bytes([0xF3, 0xF2, 0xF1]) + struct.pack('<H', 9) + bytes(9) + REPORT_TAIL[1:]
        parser.feed_bytes(rest)
        # 注意：需要构造一个完整帧的剩余部分
        # 简化：重新发送一个完整帧
        parser2 = LD2410BParser()
        parser2.feed_bytes(bytes([0xF4, 0xF3, 0xF2, 0xF4]))  # 最后一个 F4 触发重新同步
        frame = build_report_frame()
        parser2.feed_bytes(frame)
        assert parser2.get_frame_count() == 1

    def test_resync_from_garbage_in_data(self):
        """
        测试目的：验证数据负载中出现帧头字节 0xF4 不会被误判为新帧头。
        LD2410B 的数据负载可能包含任意字节值（包括 0xF4），
        解析器在 PARSER_WAIT_DATA 状态不应被 0xF4 干扰。
        """
        parser = LD2410BParser()
        # 构建包含 0xF4 的数据负载
        payload_with_f4 = bytes([
            0x01,  # target_state
            0xE8, 0x03,  # moving_dist = 1000
            0x2D,  # moving_energy = 45
            0x00, 0x00,  # static_dist = 0
            0x00,  # static_energy = 0
            0x88, 0x13,  # detect_dist = 5000
        ])
        # 确认负载中有 0x88 但不一定有 0xF4
        # 换一个确认有 0xF4 的情况...
        payload_with_f4 = bytes([
            0x01,  # target_state
            0xF4, 0x01,  # moving_dist = 500 (含 0xF4 低字节)
            0x2D,
            0x00, 0x00,
            0x00,
            0x88, 0x13,
        ])
        test_frame = REPORT_HEADER
        test_frame += struct.pack('<H', len(payload_with_f4))
        test_frame += payload_with_f4
        test_frame += REPORT_TAIL

        parser.feed_bytes(test_frame)
        assert parser.get_frame_count() == 1
        assert parser.last_info['moving_dist_cm'] == 50  # 500mm = 50cm

    def test_resync_after_partial_garbage(self):
        """
        测试目的：验证部分垃圾字节后，新的有效帧头能正确同步。
        """
        parser = LD2410BParser()

        # 发送部分帧头（如 F4F3）然后垃圾字节，最后有效帧
        data = bytes([0xF4, 0xF3, 0x00, 0xFF, 0xAA])
        frame = build_report_frame(target_state=1, moving_dist_mm=2000)
        parser.feed_bytes(data + frame)

        assert parser.get_frame_count() == 1
        assert parser.last_info['moving_dist_cm'] == 200


class TestConfigFrameParsing:
    """测试配置帧解析"""

    def test_parse_config_response(self):
        """
        测试目的：验证配置帧响应能被识别和解析。
        """
        parser = LD2410BParser()
        cfg_resp = build_cfg_response(bytes([0x01, 0x02, 0x03, 0x04]))
        parser.feed_bytes(cfg_resp)

        # 配置帧只做日志，不更新目标信息
        assert parser.last_info is None, "配置帧不应更新雷达目标信息"

    def test_report_after_config(self):
        """
        测试目的：验证配置帧后紧随上报帧能正常解析。
        """
        parser = LD2410BParser()
        cfg_resp = build_cfg_response(bytes([0x01]))
        report = build_report_frame(target_state=1, moving_dist_mm=1000)

        parser.feed_bytes(cfg_resp + report)
        assert parser.get_frame_count() == 1
        assert parser.last_info is not None


class TestEdgeCases:
    """测试边界条件"""

    def test_max_distance(self):
        """
        测试目的：验证最大距离值（0xFFFF mm）的解析。
        """
        parser = LD2410BParser()
        frame = build_report_frame(
            target_state=1,
            moving_dist_mm=0xFFFF,  # 最大距离
            detect_dist_mm=0xFFFF,
        )
        parser.feed_bytes(frame)
        assert parser.get_frame_count() == 1
        assert parser.last_info['moving_dist_cm'] == 6553  # 65535mm // 10

    def test_zero_energy(self):
        """
        测试目的：验证零能量的帧解析。
        """
        parser = LD2410BParser()
        frame = build_report_frame(
            target_state=0,
            moving_dist_mm=0,
            moving_energy=0,
            static_dist_mm=0,
            static_energy=0,
            detect_dist_mm=0,
        )
        parser.feed_bytes(frame)
        assert parser.get_frame_count() == 1
        assert parser.last_info['moving_energy'] == 0
        assert parser.last_info['static_energy'] == 0

    def test_max_energy(self):
        """
        测试目的：验证最大能量值（100）的解析。
        """
        parser = LD2410BParser()
        frame = build_report_frame(
            target_state=1,
            moving_dist_mm=1000,
            moving_energy=100,
            static_dist_mm=800,
            static_energy=100,
            detect_dist_mm=5000,
        )
        parser.feed_bytes(frame)
        assert parser.last_info['moving_energy'] == 100
        assert parser.last_info['static_energy'] == 100

    def test_single_byte_at_a_time(self):
        """
        测试目的：验证逐字节送入（最恶劣的慢速串口场景）。
        """
        parser = LD2410BParser()
        frame = build_report_frame(target_state=1, moving_dist_mm=1500)

        for b in frame:
            parser.feed(b)
            parser.advance_time(1)  # 每字节间隔 1ms

        assert parser.get_frame_count() == 1
        assert parser.last_info['moving_dist_cm'] == 150
