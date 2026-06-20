"""tests.test_hid_packet — HID 协议包构建器测试"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.hid_packet_builder import (
    HidPacketBuilder, TextLayout, UIModel,
    build_text_packet, build_layout_packet, build_ui_packet,
)


class TestHidPacketBuilder:
    def test_text_packet_length(self):
        packet = build_text_packet("Hello")
        assert len(packet) == 64

    def test_text_packet_starts_with_header(self):
        packet = build_text_packet("A")
        assert packet[:5] == bytes([0x2E, 0xAA, 0xEC, 0xE8, 0x00])

    def test_layout_packet_length(self):
        packet = build_layout_packet(TextLayout.CENTER)
        assert len(packet) == 64

    def test_ui_packet_length(self):
        packet = build_ui_packet(UIModel.CLOCK)
        assert len(packet) == 64

    def test_checksum_known_value(self):
        # checksum("ABC") = 128 + (65+2) + (66+2) + (67+2) = 332 → %256 = 76
        result = HidPacketBuilder.checksum(b"ABC")
        assert result == 76

    def test_checksum_empty(self):
        result = HidPacketBuilder.checksum(b"")
        assert result == 128  # acc starts at 128

    def test_checksum_varied(self):
        c1 = HidPacketBuilder.checksum(b"test")
        c2 = HidPacketBuilder.checksum(b"Test")
        assert c1 != c2  # case-sensitive

    def test_to_hex(self):
        result = HidPacketBuilder.to_hex(bytes([0x2E, 0xAA]))
        assert result == "2eaa"


class TestTextLayout:
    def test_has_all_layouts(self):
        assert len(list(TextLayout)) == 6


class TestUIModel:
    def test_has_all_models(self):
        assert len(list(UIModel)) == 9
