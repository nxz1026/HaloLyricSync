#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USB HID通信模块 - 与HALO OIXELBAR音箱通信

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

from .config import get_config
from .hid_packet_builder import HidPacketBuilder, TextLayout, UIModel


# 尝试导入HID库
try:
    import hidapi
    HAS_HIDAPI = True
except ImportError:
    HAS_HIDAPI = False
    print("[HID] hidapi未安装，将使用模拟模式")
    print("[HID] 安装命令: pip install hidapi")


@dataclass
class HidDeviceInfo:
    """HID设备信息"""
    path: str
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


class HidError(Exception):
    """HID通信错误"""
    pass


class HaloPixelCommunicator:
    """HALO OIXELBAR HID通信器"""
    
    # 设备名称关键字
    DEVICE_KEYWORDS = ["halo", "pixel", "花再", "pixelbar"]
    
    # 设备最大输入/输出报告长度
    MAX_REPORT_LENGTH = 64
    
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
            hidapi.hid_init()
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
                path="simulated",
                vendor_id=0x1234,
                product_id=0x5678,
                serial_number="SIMULATED",
                manufacturer_string="HALO",
                product_string="花再 Halo PixelBar (模拟)",
                release_number=0x0100
            ))
            return devices
        
        try:
            # 枚举所有HID设备
            enumerated = hidapi.hid.enumerate()
            
            for dev in enumerated:
                # 获取设备属性（hidapi返回对象而非字典）
                def get_attr(obj, name):
                    """安全获取对象属性"""
                    for attr in [name, name.replace('_', ''), name.replace('_string', '')]:
                        if hasattr(obj, attr):
                            val = getattr(obj, attr)
                            if val is not None:
                                return val if isinstance(val, str) else str(val) if isinstance(val, int) else ""
                    return ""
                
                info = HidDeviceInfo(
                    path=get_attr(dev, "path"),
                    vendor_id=get_attr(dev, "vendor_id") or 0,
                    product_id=get_attr(dev, "product_id") or 0,
                    serial_number=get_attr(dev, "serial_number"),
                    manufacturer_string=get_attr(dev, "manufacturer_string"),
                    product_string=get_attr(dev, "product_string"),
                    release_number=int(get_attr(dev, "release_number") or "0") or 0
                )
                devices.append(info)
                
        except Exception as e:
            print(f"[HID] 枚举设备失败: {e}")
        
        return devices
    
    @staticmethod
    def find_halo_devices() -> List[HidDeviceInfo]:
        """
        查找所有HALO OIXELBAR设备
        
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
            print(f"    路径: {device.path}")
            print(f"    VID:PID: {device.vendor_id:04X}:{device.product_id:04X}")
            print(f"    序列号: {device.serial_number}")
            print(f"    厂商: {device.manufacturer_string}")
            print(f"    固件版本: {device.release_number:04X}")
    
    def connect(self, path: Optional[str] = None) -> bool:
        """
        连接到HALO设备
        
        Args:
            path: 设备路径，如果为空则自动查找第一个HALO设备
            
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
            
            # 查找设备
            if not path:
                halo_devices = self.find_halo_devices()
                if not halo_devices:
                    print("[HID] 未找到HALO OIXELBAR设备")
                    return False
                path = halo_devices[0].path
                self.device_info = halo_devices[0]
            else:
                # 根据路径查找设备信息
                for device in self.list_devices():
                    if device.path == path:
                        self.device_info = device
                        break
            
            # 打开设备
            try:
                self.device = hidapi.hid.open_path(path)
                
                if not self.device:
                    print(f"[HID] 无法打开设备: {path}")
                    return False
                
                # 设置非阻塞模式
                hidapi.hid.set_nonblocking(self.device, 1)
                
                self.connected = True
                device_name = self.device_info.name if self.device_info else "Unknown"
                print(f"[HID] 已连接到: {device_name}")
                return True
                
            except Exception as e:
                print(f"[HID] 连接失败: {e}")
                return False
    
    def disconnect(self) -> None:
        """断开连接"""
        with self._lock:
            if self.connected and self.device and not self._simulated:
                try:
                    hidapi.hid.close(self.device)
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
                # HID数据包第一个字节是报告ID，通常为0
                report = bytes([0x00]) + packet
                
                # 写入设备
                result = hidapi.hid.write(self.device, report)
                
                if result == -1:
                    print("[HID] 发送失败")
                    return False
                
                return True
                
        except Exception as e:
            print(f"[HID] 发送异常: {e}")
            self.connected = False
            return False
    
    def send_text(self, text: str, max_length: int = 50) -> bool:
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
        
        # 构建文本数据包
        packet = HidPacketBuilder.build_text(text)
        
        # 发送
        success = self._send_packet(packet)
        
        if success:
            print(f"[HID] 显示文本: {text}")
        
        return success
    
    def send_lyric_line(self, text: str, line_index: int = 0, total_lines: int = 1) -> bool:
        """
        发送歌词行到设备显示
        
        Args:
            text: 歌词文本
            line_index: 行索引
            total_lines: 总行数
            
        Returns:
            是否发送成功
        """
        # 截断过长的文本
        max_chars = self.config.get('lyrics', 'max_chars_per_line', fallback=20)
        text = text[:max_chars]
        
        return self.send_text(text)
    
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


if __name__ == "__main__":
    # 测试代码
    print("=" * 60)
    print("HALO OIXELBAR HID通信测试")
    print("=" * 60)
    
    # 列出所有设备
    HaloPixelCommunicator.print_all_devices()
    
    # 尝试连接
    communicator = HaloPixelCommunicator()
    
    print("\n" + "=" * 60)
    print("尝试连接到HALO设备...")
    print("=" * 60)
    
    if communicator.connect():
        print("\n[成功] 已连接到设备")
        
        # 测试发送
        print("\n测试发送文本:")
        communicator.send_text("Hello from Python!")
        
        print("\n测试布局:")
        communicator.set_text_layout(TextLayout.CENTER)
        
        print("\n测试UI模式:")
        communicator.set_ui_mode(UIModel.CLOCK)
        
        # 断开连接
        communicator.disconnect()
    else:
        print("\n[失败] 无法连接到设备")
        print("提示：")
        print("1. 请确保设备已连接")
        print("2. 可能需要管理员权限运行")
        print("3. 尝试: 以管理员身份运行命令提示符")
