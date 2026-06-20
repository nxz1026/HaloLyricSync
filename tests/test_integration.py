"""tests.test_integration — 集成测试和并发场景测试"""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.source.lxmusic import LxPlayerSnapshot, LxMusicSource
from src.lyrics_parser import parse_lrc, LyricsParser
from src.hid_packet_builder import HidPacketBuilder, TextLayout, UIModel, TextColor


class TestLrcParserIntegration:
    """LRC 解析器集成测试 - 复杂场景"""

    def test_multiple_timestamps_per_line(self):
        """测试行内多个时间标签"""
        lrc = """[00:00.00][00:05.50]同一句歌词
[00:10.00]另一句歌词"""
        parser = parse_lrc(lrc)
        assert len(parser.lines) == 3

    def test_various_time_formats(self):
        """测试各种时间格式"""
        lrc = """[0:01.50]格式1
[00:02:50]格式2
[01:03.00]格式3"""
        parser = parse_lrc(lrc)
        assert len(parser.lines) == 3
        assert parser.lines[0].time_ms == 1500
        assert parser.lines[1].time_ms == 2500
        assert parser.lines[2].time_ms == 63000

    def test_empty_lines_ignored(self):
        """测试空行被忽略"""
        lrc = """
[00:01.00]第一句

[00:02.00]第二句

"""
        parser = parse_lrc(lrc)
        assert len(parser.lines) == 2

    def test_get_lyric_at_boundary(self):
        """测试边界时间点"""
        lrc = """[00:01.00]第一句
[00:02.00]第二句
[00:03.00]第三句"""
        parser = parse_lrc(lrc)

        # 恰好在边界上
        line = parser.get_lyric_at_time(1000)
        assert line is not None
        assert "第一句" in line.text

        # 刚好在边界前
        line = parser.get_lyric_at_time(1999)
        assert line is not None
        assert "第一句" in line.text

        # 刚好在边界后
        line = parser.get_lyric_at_time(2000)
        assert line is not None
        assert "第二句" in line.text


class TestHidPacketIntegration:
    """HID 包构建集成测试"""

    def test_text_packet_with_color(self):
        """测试带颜色的文本包"""
        packet = HidPacketBuilder.build_text("Hello", color=TextColor.RED)
        assert len(packet) == 64
        assert packet[4] == TextColor.RED.value  # 颜色字节

    def test_text_packet_cjk_characters(self):
        """测试中文字符包"""
        packet = HidPacketBuilder.build_text("你好世界")
        assert len(packet) == 64

    def test_text_packet_truncation(self):
        """测试文本截断"""
        long_text = "A" * 100
        packet = HidPacketBuilder.build_text(long_text, max_length=20)
        assert len(packet) == 64

    def test_layout_packet_all_types(self):
        """测试所有布局类型"""
        for layout in TextLayout:
            packet = HidPacketBuilder.build_layout(layout)
            assert len(packet) == 64

    def test_ui_model_packet_all_types(self):
        """测试所有 UI 模式"""
        for model in UIModel:
            packet = HidPacketBuilder.build_ui_model(model)
            assert len(packet) == 64

    def test_checksum_consistency(self):
        """测试校验和一致性"""
        data = b"Test checksum data"
        c1 = HidPacketBuilder.checksum(data)
        c2 = HidPacketBuilder.checksum(data)
        assert c1 == c2

    def test_packet_hex_roundtrip(self):
        """测试十六进制往返转换"""
        original = HidPacketBuilder.build_text("Test")
        hex_str = HidPacketBuilder.to_hex(original)
        restored = HidPacketBuilder.from_hex(hex_str)
        assert original == restored


class TestSnapshotIntegration:
    """快照集成测试"""

    def test_snapshot_from_empty_dict(self):
        """测试空字典创建快照"""
        snap = LxPlayerSnapshot.from_api_dict({})
        assert snap.is_playing is False
        assert snap.song_name == ""

    def test_snapshot_preserves_prior_values(self):
        """测试保留前一个快照的值"""
        prior = LxPlayerSnapshot(song_name="Test Song", singer="Test Singer", progress_ms=5000)
        snap = LxPlayerSnapshot.from_api_dict({}, prior=prior)
        assert snap.song_name == "Test Song"
        assert snap.singer == "Test Singer"
        assert snap.progress_ms == 5000

    def test_snapshot_partial_update(self):
        """测试部分更新"""
        prior = LxPlayerSnapshot(song_name="Old Song", singer="Old Singer")
        data = {"name": "New Song"}
        snap = LxPlayerSnapshot.from_api_dict(data, prior=prior)
        assert snap.song_name == "New Song"
        assert snap.singer == "Old Singer"  # 保留旧值

    def test_snapshot_progress_conversion(self):
        """测试进度值转换为毫秒"""
        data = {"progress": 30.5, "duration": 240.0}
        snap = LxPlayerSnapshot.from_api_dict(data)
        assert snap.progress_ms == 30500
        assert snap.duration_ms == 240000

    def test_snapshot_playing_states(self):
        """测试播放状态"""
        for state in ["playing", "paused", "stoped", "error"]:
            data = {"status": state}
            snap = LxPlayerSnapshot.from_api_dict(data)
            assert snap.state == state
            assert snap.is_playing == (state in {"playing", "paused"})


class TestConcurrencyScenarios:
    """并发场景测试"""

    def test_concurrent_snapshot_access(self):
        """测试并发快照访问"""
        snapshot = LxPlayerSnapshot(song_name="Test", progress_ms=0)
        errors = []

        def reader():
            for _ in range(100):
                try:
                    _ = snapshot.song_name
                    _ = snapshot.progress_ms
                except Exception as e:
                    errors.append(e)

        def writer():
            for i in range(100):
                try:
                    snapshot.progress_ms = i * 1000
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        threads += [threading.Thread(target=writer) for _ in range(2)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_packet_building(self):
        """测试并发包构建"""
        errors = []
        results = []

        def build_packets():
            try:
                for i in range(50):
                    packet = HidPacketBuilder.build_text(f"Test {i}")
                    results.append(packet)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=build_packets) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 250

    def test_concurrent_lrc_parsing(self):
        """测试并发 LRC 解析"""
        lrc = """[00:01.00]第一句
[00:02.00]第二句
[00:03.00]第三句"""
        errors = []
        results = []

        def parse_lyrics():
            try:
                for _ in range(50):
                    parser = parse_lrc(lrc)
                    results.append(len(parser.lines))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=parse_lyrics) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(r == 3 for r in results)


class TestEdgeCases:
    """边界情况测试"""

    def test_very_long_lyrics(self):
        """测试超长歌词"""
        lines = [f"[{(i // 60):02d}:{(i % 60):02d}.00]Line {i}" for i in range(1000)]
        lrc = "\n".join(lines)
        parser = parse_lrc(lrc)
        assert len(parser.lines) == 1000

    def test_special_characters_in_lyrics(self):
        """测试歌词中的特殊字符"""
        lrc = """[00:01.00]Hello "World"
[00:02.00]Test <>&' chars
[00:03.00]Unicode: 你好 🎵"""
        parser = parse_lrc(lrc)
        assert len(parser.lines) == 3

    def test_empty_lrc_string(self):
        """测试空 LRC 字符串"""
        parser = parse_lrc("")
        assert len(parser.lines) == 0
        assert parser.get_lyric_at_time(1000) is None

    def test_whitespace_only_lrc(self):
        """测试仅包含空白的 LRC"""
        parser = parse_lrc("   \n\n   \t\t\n")
        assert len(parser.lines) == 0

    def test_malformed_timestamps(self):
        """测试格式错误的时间戳"""
        lrc = """[abc]无效时间
[00:01.00]有效时间
[99:99.99]边界时间"""
        parser = parse_lrc(lrc)
        assert len(parser.lines) == 2  # 只有有效的被解析
