#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐歌词源 - 内存读取方式

参考项目：HaloPixelToolBox (https://github.com/XFEstudio/HaloPixelToolBox)
"""

import ctypes
import sys
from typing import Optional, List
import psutil

from .base import LyricsSource
from .memory import MemoryReader


# 网易云音乐版本对应的内存地址偏移
# 格式：版本 -> (模块基地址偏移, 指针偏移1, 指针偏移2, ..., 最终偏移)
# 最终偏移通常是 0x0，表示歌词就在最后一级指针所指地址
CLOUDMUSIC_VERSION_ADDRESS_MAP = {
    "3.1.32": (0x01DF44D0, 0x120, 0x8, 0x0),
    "3.1.30": (0x01DF44D0, 0x120, 0x8, 0x0),
    "3.1.29": (0x01DEB4D0, 0x120, 0x8, 0x0),
    "3.1.28": (0x01DDF290, 0x120, 0x8, 0x0),
    "3.1.27": (0x01DDE290, 0xE0, 0x8, 0xE8, 0x38, 0x118, 0x8, 0x0),
    "3.1.26": (0x01DD5130, 0xE8, 0x38, 0x120, 0x18, 0x0),
    "3.1.25": (0x01DAFF60, 0xE0, 0x8, 0x128, 0x18, 0x0),
}

# 测试用的绝对地址
CLOUDMUSIC_TEST_ABSOLUTE_ADDRESS = None


class CloudMusicSource(LyricsSource):
    """网易云音乐歌词源（内存读取）"""

    def __init__(self, test_absolute_address: Optional[int] = None):
        super().__init__()
        self.test_absolute_address = test_absolute_address
        self._last_lyrics = ""
        self._offsets = None
        self._lyrics_address = None

    @property
    def name(self) -> str:
        return "网易云音乐"

    @property
    def process_keywords(self) -> list:
        return ["cloudmusic"]

    def find_process(self) -> Optional[psutil.Process]:
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                if proc.info['name'] and any(k in proc.info['name'].lower() for k in self.process_keywords):
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def initialize(self) -> bool:
        process = self.find_process()
        if not process:
            print(f"[{self.name}] 未找到进程")
            return False

        self.process_id = process.pid
        print(f"[{self.name}] 找到进程: {process.name()} (PID: {self.process_id})")

        self.version = self._detect_version(process)
        if self.version:
            print(f"[{self.name}] 检测到版本: {self.version}")
        else:
            print(f"[{self.name}] 无法检测版本，使用默认版本 3.1.30")
            self.version = "3.1.30"

        if not self._resolve_address():
            print(f"[{self.name}] 歌词地址解析失败")
            return False

        self._initialized = True
        return True

    def _detect_version(self, process: psutil.Process) -> Optional[str]:
        """从文件版本信息检测版本号"""
        try:
            exe_path = process.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
        result = self._get_pe_file_version(exe_path)
        if not result:
            return None
        major, minor, patch = result
        version_str = f"{major}.{minor}.{patch}"
        return version_str

    def _get_pe_file_version(self, file_path: str):
        """读取 PE 文件版本号"""
        try:
            size = ctypes.windll.version.GetFileVersionInfoSizeW(file_path, None)
            if size == 0:
                return None
            buffer = ctypes.create_string_buffer(size)
            if not ctypes.windll.version.GetFileVersionInfoW(file_path, 0, size, buffer):
                return None
            ptr = ctypes.c_void_p()
            length = ctypes.c_uint()
            if not ctypes.windll.version.VerQueryValueW(
                buffer, '\\', ctypes.byref(ptr), ctypes.byref(length)
            ):
                return None

            class VS_FIXEDFILEINFO(ctypes.Structure):
                _fields_ = [
                    ('dwSignature', ctypes.c_ulong),
                    ('dwStrucVersion', ctypes.c_ulong),
                    ('dwFileVersionMS', ctypes.c_ulong),
                    ('dwFileVersionLS', ctypes.c_ulong),
                    ('dwProductVersionMS', ctypes.c_ulong),
                    ('dwProductVersionLS', ctypes.c_ulong),
                    ('dwFileFlagsMask', ctypes.c_ulong),
                    ('dwFileFlags', ctypes.c_ulong),
                    ('dwFileOS', ctypes.c_ulong),
                    ('dwFileType', ctypes.c_ulong),
                    ('dwFileSubtype', ctypes.c_ulong),
                    ('dwFileDateMS', ctypes.c_ulong),
                    ('dwFileDateLS', ctypes.c_ulong),
                ]
            info = ctypes.cast(ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
            if info.dwSignature != 0xFEEF04BD:
                return None
            major = (info.dwFileVersionMS >> 16) & 0xFFFF
            minor = info.dwFileVersionMS & 0xFFFF
            patch = (info.dwFileVersionLS >> 16) & 0xFFFF
            return (major, minor, patch)
        except Exception as e:
            print(f"[{self.name}] 读取文件版本失败: {e}")
            return None

    def _resolve_address(self) -> bool:
        """解析歌词内存地址（指针链）"""
        if self.test_absolute_address is not None:
            self._lyrics_address = self.test_absolute_address
            self._offsets = (self.test_absolute_address,)
            print(f"[{self.name}] 使用测试绝对地址: 0x{self.test_absolute_address:X}")
            return True

        offsets = CLOUDMUSIC_VERSION_ADDRESS_MAP.get(self.version)
        if offsets is None:
            print(f"[{self.name}] 版本 {self.version} 无对应地址偏移，回退到 3.1.30")
            self.version = "3.1.30"
            offsets = CLOUDMUSIC_VERSION_ADDRESS_MAP.get(self.version)
            if offsets is None:
                return False

        self._offsets = offsets
        with MemoryReader(self.process_id) as mr:
            dll_base_info = mr.get_module_base("cloudmusic.dll")
            if dll_base_info is None:
                print(f"[{self.name}] 无法获取 cloudmusic.dll 基址，尝试 cloudmusic.exe")
                dll_base_info = mr.get_module_base("cloudmusic.exe")
                if dll_base_info is None:
                    print(f"[{self.name}] 无法获取任何模块基址")
                    return False
            dll_base, _ = dll_base_info

            print(f"[{self.name}] cloudmusic.dll 基址: 0x{dll_base:X}")
            addr = dll_base + offsets[0]
            for i, off in enumerate(offsets[1:], start=1):
                ptr = mr.read_qword(addr)
                if not ptr:
                    print(f"[{self.name}] 指针链第 {i} 步读取失败 (地址 0x{addr:X})")
                    return False
                addr = ptr + off
                if addr <= 0x10000 or addr >= 0x7FFFFFFF0000:
                    print(f"[{self.name}] 指针链第 {i} 步得到异常地址 0x{addr:X}")
                    return False
            self._lyrics_address = addr
            print(f"[{self.name}] 歌词地址解析成功: 0x{addr:X}")
            return True

    def read_lyrics(self) -> Optional[str]:
        if not self._initialized or not self._lyrics_address:
            return None
        try:
            with MemoryReader(self.process_id) as mr:
                text = mr.read_utf16_string(self._lyrics_address, 512)
            if text and text != self._last_lyrics:
                self._last_lyrics = text
                return text
        except Exception as e:
            print(f"[{self.name}] 读取歌词失败: {e}")
            try:
                psutil.Process(self.process_id)
            except psutil.NoSuchProcess:
                self._initialized = False
                self.initialize()
        return self._last_lyrics or None

    def is_ready(self) -> bool:
        if not self._initialized:
            return False
        try:
            psutil.Process(self.process_id)
            return True
        except psutil.NoSuchProcess:
            self._initialized = False
            return False

    def get_supported_versions(self) -> List[str]:
        return list(CLOUDMUSIC_VERSION_ADDRESS_MAP.keys())