#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USB通信模块 - 与HALO OIXELBAR音箱通信
"""

import time
import threading
from typing import Optional, Callable
from dataclasses import dataclass

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False
    print("[USB] pyserial未安装，将使用模拟模式")

from .config import get_config


@dataclass
class DeviceInfo:
    """设备信息"""
    port: str
    description: str
    hwid: str


class UsbError(Exception):
    """USB通信错误"""
    pass


class UsbCommunicator:
    """USB通信器 - 用于与HALO OIXELBAR音箱通信"""
    
    # HALO OIXELBAR可能的设备信息
    VENDOR_IDS = [0x1a86, 0x0403, 0x10c4]  # 常见USB转串口芯片厂商ID
    VENDOR_NAMES = ["CH340", "CP2102", "FTDI", "HALO"]
    
    def __init__(self, config=None):
        """
        初始化USB通信器
        
        Args:
            config: 配置对象
        """
        self.config = config or get_config()
        self.serial_port: Optional[serial.Serial] = None
        self.port: Optional[str] = None
        self.connected = False
        self._lock = threading.Lock()
        self._simulated = not HAS_SERIAL
        
        if not HAS_SERIAL:
            print("[USB] 模拟模式运行")
    
    @staticmethod
    def list_devices() -> list[DeviceInfo]:
        """
        列出所有可用的串口设备
        
        Returns:
            设备信息列表
        """
        if not HAS_SERIAL:
            return [
                DeviceInfo("COM3", "HALO OIXELBAR (SIMULATED)", "SIMULATED"),
                DeviceInfo("COM5", "Another Device", "OTHER")
            ]
        
        devices = []
        for port in serial.tools.list_ports.comports():
            devices.append(DeviceInfo(
                port=port.device,
                description=port.description,
                hwid=port.hwid
            ))
        return devices
    
    @staticmethod
    def find_halo_device() -> Optional[DeviceInfo]:
        """
        自动查找HALO OIXELBAR设备
        
        Returns:
            找到的设备信息，找不到返回None
        """
        devices = UsbCommunicator.list_devices()
        
        for device in devices:
            desc = device.description.lower()
            if any(name.lower() in desc for name in UsbCommunicator.VENDOR_NAMES):
                print(f"[USB] 找到可能的HALO设备: {device}")
                return device
        
        return None
    
    def connect(self, port: Optional[str] = None) -> bool:
        """
        连接到设备
        
        Args:
            port: 串口路径，例如 "COM3" 或 "/dev/ttyUSB0"
                  如果为空则自动查找
            
        Returns:
            是否连接成功
        """
        with self._lock:
            if self.connected:
                print("[USB] 已连接")
                return True
            
            if self._simulated:
                self.port = port or "SIMULATED"
                self.connected = True
                print(f"[USB] 模拟连接到: {self.port}")
                return True
            
            if not port:
                auto_detect = self.config.get('usb', 'auto_detect', fallback=True)
                if auto_detect:
                    device = self.find_halo_device()
                    if device:
                        port = device.port
                    else:
                        print("[USB] 未找到HALO设备")
                        return False
                else:
                    port = self.config.get('usb', 'device_id', fallback=None)
                    if not port:
                        print("[USB] 未指定设备端口")
                        return False
            
            baud_rate = self.config.get('usb', 'baud_rate', fallback=9600)
            timeout = self.config.get('usb', 'timeout', fallback=2)
            
            try:
                self.serial_port = serial.Serial(
                    port=port,
                    baudrate=baud_rate,
                    timeout=timeout,
                    write_timeout=timeout
                )
                self.port = port
                self.connected = True
                print(f"[USB] 已连接到: {port}")
                return True
            except Exception as e:
                print(f"[USB] 连接失败: {e}")
                return False
    
    def disconnect(self) -> None:
        """断开连接"""
        with self._lock:
            if self.connected and self.serial_port:
                self.serial_port.close()
                self.serial_port = None
                self.connected = False
                print("[USB] 已断开连接")
    
    def send_text(self, text: str) -> bool:
        """
        发送文本到设备
        
        Args:
            text: 要发送的文本
            
        Returns:
            是否发送成功
        """
        if not self.connected:
            if not self.connect():
                return False
        
        try:
            # 根据HALO OIXELBAR协议发送
            # 这里是示例协议，需要根据实际设备协议调整
            with self._lock:
                if self._simulated:
                    print(f"[USB] [SIMULATED] 发送文本: {text}")
                    return True
                
                # 发送前导码
                self.serial_port.write(b'\xAA\x55')
                
                # 发送数据长度
                text_bytes = text.encode('utf-8')
                self.serial_port.write(len(text_bytes).to_bytes(2, byteorder='little'))
                
                # 发送文本数据
                self.serial_port.write(text_bytes)
                
                # 发送校验和
                checksum = sum(text_bytes) & 0xFF
                self.serial_port.write(bytes([checksum]))
                
                self.serial_port.flush()
            
            return True
        except Exception as e:
            print(f"[USB] 发送失败: {e}")
            self.connected = False
            return False
    
    def send_lyric_line(self, text: str, line_index: int = 0, total_lines: int = 1) -> bool:
        """
        发送歌词行（带显示控制）
        
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
        
        # 构建显示命令
        # 示例格式: [LYRIC:LINE_INDEX:TOTAL_LINES]TEXT
        display_data = f"[LYRIC:{line_index}:{total_lines}]{text}"
        
        return self.send_text(display_data)
    
    def clear_display(self) -> bool:
        """
        清空显示
        
        Returns:
            是否成功
        """
        return self.send_text("[CLEAR]")
    
    def show_song_info(self, song_name: str, artist: str) -> bool:
        """
        显示歌曲信息
        
        Args:
            song_name: 歌曲名
            artist: 艺术家
            
        Returns:
            是否成功
        """
        info = f"[SONG]{song_name}|{artist}"
        return self.send_text(info)
    
    def receive_response(self, timeout: float = 1.0) -> Optional[str]:
        """
        接收设备响应
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            接收到的响应文本
        """
        if self._simulated:
            return "[OK]"
        
        if not self.connected:
            return None
        
        try:
            with self._lock:
                self.serial_port.timeout = timeout
                response = self.serial_port.readline()
                return response.decode('utf-8', errors='ignore').strip()
        except Exception as e:
            print(f"[USB] 接收失败: {e}")
            return None
    
    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()


# 全局通信器实例
_usb_instance = None

def get_usb_communicator() -> UsbCommunicator:
    """获取USB通信器单例"""
    global _usb_instance
    if _usb_instance is None:
        _usb_instance = UsbCommunicator()
    return _usb_instance
