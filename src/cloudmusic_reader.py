#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐内存读取器
直接从网易云音乐进程中读取歌词数据，无需API

参考项目：HaloPixelToolBox (https://github.com/XFEstudio/HaloPixelToolBox)
"""

import ctypes
import ctypes.wintypes
import struct
import sys
import time
from pathlib import Path
from typing import Optional, List


# 网易云音乐版本对应的内存地址偏移
# 格式：版本 -> [模块基地址偏移, 指针偏移1, 指针偏移2, ...]
VERSION_ADDRESS_MAP = {
    "3.1.30": (0x01DF44D0, 0x120, 0x8, 0x0),
    "3.1.29": (0x01DEB4D0, 0x120, 0x8, 0x0),
    "3.1.28": (0x01DDF290, 0x120, 0x8, 0x0),
    "3.1.27": (0x01DDE290, 0xE0, 0x8, 0xE8, 0x38, 0x118, 0x8, 0x0),
    "3.1.26": (0x01DD5130, 0xE8, 0x38, 0x120, 0x18, 0x0),
    "3.1.25": (0x01DAFF60, 0xE0, 0x8, 0x128, 0x18, 0x0),
}

class CloudMusicMemoryReader:
    """网易云音乐内存读取器"""
    
    def __init__(self):
        """初始化读取器"""
        self.process_handle = None
        self.process_id = None
        self.version = None
        self.lyrics_address = None
        self.offsets = None
        self._last_lyrics = ""
        self._initialized = False
    
    def initialize(self) -> bool:
        """
        初始化 - 查找进程并解析地址
        
        Returns:
            初始化是否成功
        """
        import psutil
        
        # 查找网易云音乐进程
        process = self._find_process()
        if not process:
            print("[CloudMusic] 未找到网易云音乐进程")
            return False
        
        self.process_id = process.pid
        print(f"[CloudMusic] 找到进程: {process.name()} (PID: {self.process_id})")
        
        # 获取版本信息
        try:
            version_info = process.version()
            self.version = self._parse_version(version_info)
            print(f"[CloudMusic] 版本: {self.version}")
        except Exception as e:
            print(f"[CloudMusic] 获取版本失败: {e}")
            return False
        
        # 解析歌词地址
        if not self._resolve_address():
            return False
        
        self._initialized = True
        return True
    
    def _find_process(self):
        """查找网易云音乐进程"""
        import psutil
        
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                if proc.info['name'] and 'cloudmusic' in proc.info['name'].lower():
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
    
    def _parse_version(self, version_str: str) -> Optional[str]:
        """解析版本字符串"""
        try:
            parts = version_str.split('.')
            if len(parts) >= 3:
                return f"{parts[0]}.{parts[1]}.{parts[2]}"
        except Exception:
            pass
        return None
    
    def _resolve_address(self) -> bool:
        """解析歌词内存地址"""
        if not self.version:
            return False
        
        # 查找匹配的版本
        for version, offsets in VERSION_ADDRESS_MAP.items():
            if version == self.version:
                self.offsets = offsets
                self.lyrics_address = offsets[0]
                print(f"[CloudMusic] 使用版本 {version} 的地址偏移")
                return True
        
        # 尝试查找最接近的版本
        print(f"[CloudMusic] 未找到精确匹配版本，尝试使用默认偏移")
        self.offsets = VERSION_ADDRESS_MAP.get("3.1.30", (0x01DF44D0, 0x120, 0x8, 0x0))
        self.lyrics_address = self.offsets[0]
        return True
    
    def read_lyrics(self) -> Optional[str]:
        """
        从内存读取歌词
        
        Returns:
            歌词文本，读取失败返回None
        """
        if not self._initialized or not self.process_id:
            return None
        
        try:
            lyrics = self._read_memory_string(self.lyrics_address)
            if lyrics and lyrics != self._last_lyrics:
                self._last_lyrics = lyrics
                return lyrics
        except Exception as e:
            # 尝试重新初始化
            if self.process_id:
                try:
                    psutil.Process(self.process_id)
                except psutil.NoSuchProcess:
                    print("[CloudMusic] 进程已退出，重新初始化...")
                    self._initialized = False
                    self.initialize()
        
        return self._last_lyrics if self._last_lyrics else None
    
    def _read_memory_string(self, address: int, max_length: int = 500) -> Optional[str]:
        """
        读取内存中的字符串（Windows API）
        
        Args:
            address: 内存地址
            max_length: 最大读取长度
            
        Returns:
            读取的字符串
        """
        if sys.platform != 'win32':
            print("[CloudMusic] 内存读取仅支持Windows")
            return None
        
        try:
            # 使用Windows API读取内存
            process_handle = ctypes.windll.kernel32.OpenProcess(
                0x0010,  # PROCESS_VM_READ
                False,
                self.process_id
            )
            
            if not process_handle:
                return None
            
            try:
                # 读取内存数据
                buffer = ctypes.create_string_buffer(max_length * 2)  # Unicode = 2 bytes per char
                bytes_read = ctypes.c_size_t()
                
                result = ctypes.windll.kernel32.ReadProcessMemory(
                    process_handle,
                    ctypes.c_void_p(address),
                    buffer,
                    ctypes.sizeof(buffer),
                    ctypes.byref(bytes_read)
                )
                
                if result:
                    # 转换为Unicode字符串
                    data = buffer.raw[:bytes_read.value]
                    # 找到字符串结束位置
                    null_pos = data.find(b'\x00\x00')
                    if null_pos > 0:
                        data = data[:null_pos]
                    try:
                        return data.decode('utf-16-le').strip('\x00')
                    except:
                        return None
            finally:
                ctypes.windll.kernel32.CloseHandle(process_handle)
                
        except Exception as e:
            print(f"[CloudMusic] 内存读取失败: {e}")
        
        return None
    
    def is_ready(self) -> bool:
        """检查是否就绪"""
        if not self._initialized:
            return False
        try:
            psutil.Process(self.process_id)
            return True
        except psutil.NoSuchProcess:
            self._initialized = False
            return False
    
    @property
    def is_running(self) -> bool:
        """检查网易云音乐是否在运行"""
        return self.is_ready()


def find_cloudmusic_version() -> Optional[str]:
    """
    查找网易云音乐版本
    
    Returns:
        版本字符串
    """
    import psutil
    
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            if proc.info['name'] and 'cloudmusic' in proc.info['name'].lower():
                return proc.version()
        except Exception:
            continue
    return None


def get_supported_versions() -> List[str]:
    """获取支持的版本列表"""
    return list(VERSION_ADDRESS_MAP.keys())
