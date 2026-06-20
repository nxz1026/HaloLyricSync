#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USB HID通信模块 - 与HALO PIXELBAR音箱通信

使用HID协议与设备通信，参考HaloPixelToolBox项目实现

设备信息：
- 设备名称：花再 Halo PixelBar
- 设备类型：HID设备
- 包长度：64字节
- 权限要求：管理员权限
"""

import sys
import time
import threading
from typing import Optional, List
from dataclasses import dataclass

from src.config import get_config
from src.hid_packet_builder import HidPacketBuilder, TextLayout, UIModel, TextColor


# 尝试导入HID库
try:
    import hid
    HAS_HIDAPI = True
except ImportError as _e:
    HAS_HIDAPI = False
    print(f"[HID] hid库未安装 ({_e}),将使用模拟模式")
    print("[HID] 安装命令: pip install hid")
except Exception as _e:
    HAS_HIDAPI = False
    print(f"[HID] hid库导入异常 ({_e}),将使用模拟模式")
    print("[HID] 安装命令如需重装: pip install --force-reinstall hid")


@dataclass
class HidDeviceInfo:
    """HID设备信息"""
    path: bytes  # HID 库原始路径（bytes），通过 path_str 获取可读字符串
    vendor_id: int
    product_id: int
    serial_number: str
    manufacturer_string: str
    product_string: str
    release_number: int
    
    @property
    def name(self) -> str:
        """获取设备名称"""
        return self.product_string or "Unknown Device"

    @property
    def path_str(self) -> str:
        """获取可读的路径字符串"""
        if isinstance(self.path, bytes):
            return self.path.decode('utf-8', errors='replace')
        return str(self.path)


class HidError(Exception):
    """HID通信错误"""
    pass


class HaloPixelCommunicator:
    """HALO PIXELBAR HID通信器"""
    
    # 设备名称关键字
    DEVICE_KEYWORDS = ["halo", "pixel", "花再", "pixelbar"]
    
    # 设备最大输入/输出报告长度
    MAX_REPORT_LENGTH = 64

    # 写入测试包（HID probe 用）
    _WRITE_TEST_PKT = bytes([0x2E, 0xAA, 0xEC, 0xE8, 0x00, 0x06, 0x00, 0x04]) + bytes(64 - 8)
    
    def __init__(self, config=None):
        """
        初始化HID通信器
        
        Args:
            config: 配置对象
        """
        self.config = config or get_config()
        self.device = None
        self.device_info: Optional[HidDeviceInfo] = None
        self.connected = False
        self._lock = threading.Lock()
        self._simulated = not HAS_HIDAPI
        
        if not HAS_HIDAPI:
            print("[HID] 模拟模式运行")
        else:
            self._init_hid()
    
    def _init_hid(self) -> None:
        """初始化HID库"""
        try:
            # hid库不需要显式初始化
            print("[HID] HID库初始化成功")
        except Exception as e:
            print(f"[HID] HID库初始化失败: {e}")
            self._simulated = True
    
    @staticmethod
    def list_devices() -> List[HidDeviceInfo]:
        """
        列出所有HID设备
        
        Returns:
            HID设备信息列表
        """
        devices = []
        
        if not HAS_HIDAPI:
            # 模拟模式返回虚拟设备
            devices.append(HidDeviceInfo(
                path=b"simulated",
                vendor_id=0x1234,
                product_id=0x5678,
                serial_number="SIMULATED",
                manufacturer_string="HALO",
                product_string="花再 Halo PixelBar (模拟)",
                release_number=0x0100
            ))
            return devices
        
        try:
            enumerated = hid.enumerate()
            
            for dev in enumerated:
                # hid.enumerate() 返回字典列表
                # 保持路径为原始 bytes 类型，避免 decode/encode 来回转换丢失数据
                raw_path = dev.get('path', b'')
                if not isinstance(raw_path, bytes):
                    raw_path = str(raw_path).encode('utf-8')

                info = HidDeviceInfo(
                    path=raw_path,
                    vendor_id=dev.get('vendor_id', 0),
                    product_id=dev.get('product_id', 0),
                    serial_number=dev.get('serial_number', ''),
                    manufacturer_string=dev.get('manufacturer_string', ''),
                    product_string=dev.get('product_string', ''),
                    release_number=dev.get('release_number', 0)
                )
                devices.append(info)
                
        except Exception as e:
            print(f"[HID] 枚举设备失败: {e}")
        
        return devices
    
    @staticmethod
    def find_halo_devices() -> List[HidDeviceInfo]:
        """
        查找所有HALO PIXELBAR设备
        
        Returns:
            匹配的设备列表
        """
        all_devices = HaloPixelCommunicator.list_devices()
        halo_devices = []
        
        for device in all_devices:
            name = device.name.lower()
            if any(keyword in name for keyword in HaloPixelCommunicator.DEVICE_KEYWORDS):
                halo_devices.append(device)
                print(f"[HID] 找到HALO设备: {device.name}")
                print(f"       VID:PID = {device.vendor_id:04X}:{device.product_id:04X}")
        
        return halo_devices
    
    @staticmethod
    def print_all_devices() -> None:
        """打印所有HID设备信息"""
        print("=" * 60)
        print("所有HID设备：")
        print("=" * 60)
        
        devices = HaloPixelCommunicator.list_devices()
        
        if not devices:
            print("未找到任何HID设备")
            return
        
        for i, device in enumerate(devices, 1):
            print(f"\n[{i}] {device.name}")
            print(f"    路径: {device.path_str}")
            print(f"    VID:PID: {device.vendor_id:04X}:{device.product_id:04X}")
            print(f"    序列号: {device.serial_number}")
            print(f"    厂商: {device.manufacturer_string}")
            print(f"    固件版本: {device.release_number:04X}")
    
    def _probe_write(self) -> bool:
        """发送空文本测试 HID 写入是否可用"""
        if self._simulated or not self.device:
            return True
        try:
            return self.device.write(self._WRITE_TEST_PKT) >= 0
        except Exception:
            return False

    def connect(self, path: Optional[str] = None) -> bool:
        """
        连接到HALO设备
        
        Args:
            path: 设备路径，如果为空则自动查找可写入的HALO设备
            
        Returns:
            是否连接成功
        """
        with self._lock:
            if self.connected:
                print("[HID] 已连接")
                return True

            if self._simulated:
                self.device = "simulated"
                self.connected = True
                print("[HID] 模拟连接到设备")
                return True

            # 收集要尝试的设备路径列表
            candidates: List[HidDeviceInfo] = []
            if path:
                # 指定路径
                if isinstance(path, str):
                    ref_path = path.encode('utf-8')
                else:
                    ref_path = path
                for device in self.list_devices():
                    if device.path == ref_path:
                        candidates.append(device)
                        break
                if not candidates:
                    print(f"[HID] 未找到指定路径的设备")
                    return False
            else:
                candidates = self.find_halo_devices()
                if not candidates:
                    print("[HID] 未找到HALO PIXELBAR设备")
                    return False

            # 逐个设备尝试连接+写入验证
            last_error = ""
            for device_info in candidates:
                dev_path = device_info.path
                try:
                    dev = hid.device()
                    dev.open_path(dev_path)
                    dev.set_nonblocking(1)
                    # 用 test write 验证是否是可写入的接口
                    if dev.write(self._WRITE_TEST_PKT) < 0:
                        dev.close()
                        last_error = f"{device_info.name} 写入测试失败"
                        continue
                    # 连接成功
                    self.device = dev
                    self.device_info = device_info
                    self.connected = True
                    print(f"[HID] 已连接到: {device_info.name}")
                    return True
                except Exception as e:
                    last_error = str(e)
                    try:
                        dev.close()
                    except Exception:
                        pass
                    continue

            print(f"[HID] 连接失败: {last_error}")
            return False
    
    def disconnect(self) -> None:
        """断开连接"""
        with self._lock:
            if self.connected and self.device and not self._simulated:
                try:
                    self.device.close()
                except:
                    pass
                self.device = None
                self.connected = False
                print("[HID] 已断开连接")
            else:
                self.connected = False
    
    def _send_packet(self, packet: bytes) -> bool:
        """
        发送HID数据包
        
        Args:
            packet: 64字节数据包
            
        Returns:
            是否发送成功
        """
        if not self.connected:
            return False
        
        if self._simulated:
            print(f"[HID] [模拟] 发送: {HidPacketBuilder.to_hex(packet)[:32]}...")
            return True
        
        try:
            with self._lock:
                # 设备期望裸 64 字节包,不加报告 ID 前缀
                result = self.device.write(packet)
                        
                if result == -1:
                    print("[HID] 发送失败")
                    return False
                        
                return True
                
        except Exception as e:
            print(f"[HID] 发送异常: {e}")
            self.connected = False
            return False
    
    @staticmethod
    def _resolve_color(color_spec) -> TextColor:
        """将颜色配置（字符串/TextColor）解析为 TextColor。"""
        if isinstance(color_spec, TextColor):
            return color_spec
        name_to_color = {
            "white": TextColor.WHITE, "red": TextColor.RED,
            "green": TextColor.GREEN, "blue": TextColor.BLUE,
            "yellow": TextColor.YELLOW, "cyan": TextColor.CYAN,
            "magenta": TextColor.MAGENTA,
        }
        return name_to_color.get(str(color_spec).lower().strip(), TextColor.WHITE)

    def send_text(self, text: str, max_length: int = 50, color: Optional[TextColor] = None) -> bool:
        """
        发送文本到设备显示
        
        Args:
            text: 要显示的文本
            max_length: 最大文本长度
            
        Returns:
            是否发送成功
        """
        # 截断过长的文本
        text = text[:max_length]

        if color is None:
            color = self._resolve_color(self.config.get('hid', 'color', default='white'))

        # 构建文本数据包
        packet = HidPacketBuilder.build_text(text, max_length=max_length, color=color)
        
        # 发送
        success = self._send_packet(packet)
        
        if success:
            print(f"[HID] 显示文本: {text}")
        
        return success
    
    def send_lyric_line(self, text: str, line_index: int = 0, total_lines: int = 1,
                        color: Optional[TextColor] = None) -> bool:
        """
        发送歌词行到设备显示

        Args:
            text: 歌词文本
            line_index: 行索引
            total_lines: 总行数
            color: 文本颜色（可选，默认从配置读取）

        Returns:
            是否发送成功
        """
        # 截断过长的文本
        max_chars = self.config.get('lyrics', 'max_chars_per_line', default=20)
        text = text[:max_chars]

        return self.send_text(text, color=color)
    
    def set_text_layout(self, layout: TextLayout) -> bool:
        """
        设置文本布局
        
        Args:
            layout: 文本布局
            
        Returns:
            是否发送成功
        """
        packet = HidPacketBuilder.build_layout(layout)
        
        layout_names = {
            TextLayout.LEFT: "左对齐",
            TextLayout.CENTER: "居中",
            TextLayout.RIGHT: "右对齐",
            TextLayout.STRETCH: "拉伸",
            TextLayout.SCROLL_LEFT_TO_RIGHT: "左滚",
            TextLayout.SCROLL_RIGHT_TO_LEFT: "右滚"
        }
        
        success = self._send_packet(packet)
        
        if success:
            layout_name = layout_names.get(layout, layout.value)
            print(f"[HID] 设置布局: {layout_name}")
        
        return success
    
    def set_ui_mode(self, mode: UIModel) -> bool:
        """
        设置UI模式
        
        Args:
            mode: UI模式
            
        Returns:
            是否发送成功
        """
        packet = HidPacketBuilder.build_ui_model(mode)
        
        mode_names = {
            UIModel.CLOCK: "时钟",
            UIModel.GAME: "游戏",
            UIModel.WORK: "工作",
            UIModel.READ: "阅读",
            UIModel.CATS: "猫咪",
            UIModel.DOGS: "狗狗",
            UIModel.MEMES: "表情",
            UIModel.CYBER: "赛博",
            UIModel.WAVES: "波浪"
        }
        
        success = self._send_packet(packet)
        
        if success:
            mode_name = mode_names.get(mode, mode.value)
            print(f"[HID] 设置UI模式: {mode_name}")
        
        return success
    
    def clear_display(self) -> bool:
        """
        清空显示（发送空格）
        
        Returns:
            是否发送成功
        """
        return self.send_text(" ")
    
    def show_song_info(self, song_name: str, artist: str) -> bool:
        """
        显示歌曲信息
        
        Args:
            song_name: 歌曲名
            artist: 艺术家
            
        Returns:
            是否发送成功
        """
        # 格式化歌曲信息
        info = f"{song_name} - {artist}"
        return self.send_text(info)
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.connected
    
    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()


# 别名，保持向后兼容
UsbCommunicator = HaloPixelCommunicator

# 全局通信器实例
_hid_instance = None

def get_hid_communicator() -> HaloPixelCommunicator:
    """获取HID通信器单例"""
    global _hid_instance
    if _hid_instance is None:
        _hid_instance = HaloPixelCommunicator()
    return _hid_instance

# 向后兼容的函数名
def get_usb_communicator() -> HaloPixelCommunicator:
    """获取USB通信器单例（向后兼容）"""
    return get_hid_communicator()
