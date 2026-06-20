#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HID协议包构建器

参考项目：HaloPixelToolBox (https://github.com/XFEstudio/HaloPixelToolBox)
将C#实现移植到Python

协议说明：
- 设备：花再 Halo PixelBar (HID设备)
- 包长度：固定64字节
- 通信方式：HID Write
"""

import struct
from enum import Enum
from typing import List


class TextColor(Enum):
    """文本颜色枚举（对应包头第5字节）"""
    WHITE = 0
    RED = 1
    GREEN = 2
    BLUE = 3
    YELLOW = 4
    CYAN = 5
    MAGENTA = 6


class TextLayout(Enum):
    """文本布局枚举"""
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    STRETCH = "stretch"
    SCROLL_LEFT_TO_RIGHT = "scroll_left_to_right"
    SCROLL_RIGHT_TO_LEFT = "scroll_right_to_left"


class UIModel(Enum):
    """UI模式枚举"""
    CLOCK = "clock"
    GAME = "game"
    WORK = "work"
    READ = "read"
    CATS = "cats"
    DOGS = "dogs"
    MEMES = "memes"
    CYBER = "cyber"
    WAVES = "waves"


class HidPacketBuilder:
    """HID协议包构建器

    HALO PIXELBAR HID 协议说明：
    ==========================

    所有包固定 64 字节，通过 HID Write 发送（不加报告 ID 前缀）。

    1. 文本包 (命令类型 0x01)
    -----------------------
    字节偏移    长度    说明
    0x00       4       魔数: 0x2E 0xAA 0xEC 0xE8
    0x04       1       颜色: 0=白 1=红 2=绿 3=蓝 4=黄 5=青 6=品红
    0x05       2       总长度 (little-endian, 包含文本长度+文本+校验和)
    0x07       1       文本长度 (UTF-8 字节数)
    0x08       N       文本内容 (UTF-8 编码)
    0x08+N     1       校验和
    0x09+N     ...     填充 0x00 至 64 字节

    校验和算法: acc = 128; for each byte b: acc += b + 2; return acc % 256

    2. 布局包 (命令类型 0x01, 子命令 0x02)
    -----------------------------------
    字节偏移    长度    说明
    0x00       4       魔数: 0x2E 0xAA 0xEC 0xEF
    0x04       1       保留: 0x00
    0x05       1       包体长度: 0x09
    0x06       1       命令类型: 0x01
    0x07       3       固定: 0xF0 0xB4 0xC8
    0x0A       1       保留: 0x00
    0x0B       1       子命令: 0x02
    0x0C       1       保留: 0x00
    0x0D       4       布局字节 (见 LAYOUT_BYTES)
    0x11       ...     填充 0x00 至 64 字节

    3. UI 模式包 (命令类型 0x02)
    --------------------------
    字节偏移    长度    说明
    0x00       4       魔数: 0x2E 0xAA 0xEC 0xEF
    0x04       1       保留: 0x00
    0x05       1       包体长度: 0x09
    0x06       1       命令类型: 0x02
    0x07       3       固定: 0xF0 0xB4 0xC8
    0x0A       1       保留: 0x00
    0x0B       1       子命令: 0x01
    0x0C       5       UI 模式字节 (见 UI_MODEL_BYTES)
    0x11       ...     填充 0x00 至 64 字节

    参考: HaloPixelToolBox (https://github.com/XFEstudio/HaloPixelToolBox)
    """

    # 固定包长度
    PACKET_LENGTH = 64

    # 布局包头 (13字节)
    LAYOUT_HEADER = bytes([0x2E, 0xAA, 0xEC, 0xEF, 0x00, 0x09, 0x01, 0xF0, 0xB4, 0xC8, 0x00, 0x02, 0x00])
    
    # 布局字节 (4字节): [模式ID, 0xFF, 校验相关, 0x00]
    # 模式ID: 0x00=左对齐/左滚, 0x01=居中/右滚, 0x02=右对齐, 0x03=拉伸
    LAYOUT_BYTES = {
        TextLayout.LEFT: bytes([0x00, 0xFF, 0xFC, 0x00]),
        TextLayout.CENTER: bytes([0x01, 0xFF, 0xFD, 0x00]),
        TextLayout.RIGHT: bytes([0x02, 0xFF, 0xFE, 0x00]),
        TextLayout.STRETCH: bytes([0x03, 0xFF, 0xFF, 0x00]),
        TextLayout.SCROLL_LEFT_TO_RIGHT: bytes([0x00, 0xFF, 0xFD, 0x00]),
        TextLayout.SCROLL_RIGHT_TO_LEFT: bytes([0x01, 0xFF, 0xFE, 0x00]),
    }
    
    # UI模式字节映射
    UI_MODEL_BYTES = {
        UIModel.CLOCK: bytes([0x00, 0xFF, 0xFF, 0xFB, 0x00]),
        UIModel.GAME: bytes([0x01, 0xFF, 0xFF, 0xFC, 0x00]),
        UIModel.WORK: bytes([0x02, 0xFF, 0xFF, 0xFD, 0x00]),
        UIModel.READ: bytes([0x03, 0xFF, 0xFF, 0xFE, 0x00]),
        UIModel.CATS: bytes([0x04, 0xFF, 0xFF, 0xFF, 0x00]),
        UIModel.DOGS: bytes([0x05, 0xFF, 0xFF, 0x00, 0x00]),
        UIModel.MEMES: bytes([0x06, 0xFF, 0xFF, 0x01, 0x00]),
        UIModel.CYBER: bytes([0x07, 0xFF, 0xFF, 0x02, 0x00]),
        UIModel.WAVES: bytes([0x08, 0xFF, 0xFF, 0x03, 0x00]),
    }
    
    @staticmethod
    def checksum(text_bytes: bytes) -> int:
        """
        计算校验和
        
        算法（与C#一致）：
        int acc = 128;
        foreach (char ch in textBytes) {
            acc += ch + 2;
        }
        return acc % 256;
        
        Args:
            text_bytes: 文本字节
            
        Returns:
            校验和（0-255）
        """
        acc = 128
        for byte_val in text_bytes:
            acc += byte_val + 2
        return acc % 256
    
    @staticmethod
    def build_text(text: str, max_length: int = 50, color: TextColor = TextColor.WHITE) -> bytes:
        """
        构建文本数据包

        格式：
        - 包头: 0x2E, 0xAA, 0xEC, 0xE8, color (5字节, 最后1字节=颜色)
        - 总长度: 2字节 (little-endian)
        - 文本长度: 1字节
        - 文本内容: UTF-8编码
        - 校验和: 1字节

        Args:
            text: 文本内容
            max_length: 最大文本长度
            color: 文本颜色，默认白色

        Returns:
            64字节HID数据包
        """
        # 截断过长的文本
        if len(text) > max_length:
            text = text[:max_length]
        
        # 转换为UTF-8字节
        text_bytes = text.encode('utf-8')
        text_len = len(text_bytes)
        
        # 有效载荷长度 = 文本长度(1) + 文本(N) + 校验和(1)
        total_len = 1 + text_len + 1
        
        # 构建数据包
        packet = bytearray()
        
        # 1. 包头（含颜色字节）
        color_byte = color.value if isinstance(color, TextColor) else 0
        packet.extend(bytes([0x2E, 0xAA, 0xEC, 0xE8, color_byte]))
        
        # 2. 总长度 (2字节, little-endian)
        packet.extend(struct.pack('<H', total_len))
        
        # 3. 文本长度
        packet.append(text_len)
        
        # 4. 文本内容
        packet.extend(text_bytes)
        
        # 5. 校验和
        packet.append(HidPacketBuilder.checksum(text_bytes))
        
        # 补齐到64字节
        return HidPacketBuilder._pad_packet(bytes(packet))
    
    @staticmethod
    def build_layout(layout: TextLayout) -> bytes:
        """
        构建布局控制包
        
        Args:
            layout: 文本布局
            
        Returns:
            64字节HID数据包
        """
        # 基础包
        packet = bytearray(HidPacketBuilder.LAYOUT_HEADER)
        
        # 添加布局字节
        layout_bytes = HidPacketBuilder.LAYOUT_BYTES.get(layout, HidPacketBuilder.LAYOUT_BYTES[TextLayout.CENTER])
        packet.extend(layout_bytes)
        
        return HidPacketBuilder._pad_packet(bytes(packet))
    
    @staticmethod
    def build_ui_model(model: UIModel) -> bytes:
        """
        构建UI模式控制包
        
        Args:
            model: UI模式
            
        Returns:
            64字节HID数据包
        """
        # 构建包头
        packet = bytearray([0x2E, 0xAA, 0xEC, 0xEF, 0x00, 0x09, 0x02, 0xF0, 0xB4, 0xC8, 0x00, 0x01])
        
        # 添加UI模式字节
        ui_bytes = HidPacketBuilder.UI_MODEL_BYTES.get(model, HidPacketBuilder.UI_MODEL_BYTES[UIModel.CLOCK])
        packet.extend(ui_bytes)
        
        return HidPacketBuilder._pad_packet(bytes(packet))
    
    @staticmethod
    def _pad_packet(data: bytes) -> bytes:
        """
        补齐数据包到64字节
        
        Args:
            data: 原始数据
            
        Returns:
            64字节数据包
        """
        if len(data) >= HidPacketBuilder.PACKET_LENGTH:
            return data[:HidPacketBuilder.PACKET_LENGTH]
        
        # 补0到64字节
        return data + bytes(HidPacketBuilder.PACKET_LENGTH - len(data))
    
    @staticmethod
    def to_hex(packet: bytes) -> str:
        """
        将数据包转换为十六进制字符串（小写，无分隔符）
        
        Args:
            packet: 数据包
            
        Returns:
            十六进制字符串
        """
        return packet.hex()
    
    @staticmethod
    def from_hex(hex_str: str) -> bytes:
        """
        从十六进制字符串解析数据包
        
        Args:
            hex_str: 十六进制字符串
            
        Returns:
            数据包
        """
        return bytes.fromhex(hex_str)


def build_text_packet(text: str) -> bytes:
    """便捷函数：构建文本数据包"""
    return HidPacketBuilder.build_text(text)


def build_layout_packet(layout: TextLayout) -> bytes:
    """便捷函数：构建布局数据包"""
    return HidPacketBuilder.build_layout(layout)


def build_ui_packet(model: UIModel) -> bytes:
    """便捷函数：构建UI模式数据包"""
    return HidPacketBuilder.build_ui_model(model)
