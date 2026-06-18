#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐内存读取器
直接从网易云音乐进程中读取歌词数据，无需API

参考项目：HaloPixelToolBox (https://github.com/XFEstudio/HaloPixelToolBox)
"""

import ctypes
import ctypes.wintypes
import sys
from typing import Optional, List, Tuple

import psutil


# 网易云音乐版本对应的内存地址偏移
# 格式：版本 -> [模块基地址偏移, 指针偏移1, 指针偏移2, ...]
# 最终偏移通常是 0x0，表示歌词就在最后一级指针所指地址
VERSION_ADDRESS_MAP = {
    "3.1.32": (0x01DF44D0, 0x120, 0x8, 0x0),  # 基于 3.1.30，待验证
    "3.1.30": (0x01DF44D0, 0x120, 0x8, 0x0),
    "3.1.29": (0x01DEB4D0, 0x120, 0x8, 0x0),
    "3.1.28": (0x01DDF290, 0x120, 0x8, 0x0),
    "3.1.27": (0x01DDE290, 0xE0, 0x8, 0xE8, 0x38, 0x118, 0x8, 0x0),
    "3.1.26": (0x01DD5130, 0xE8, 0x38, 0x120, 0x18, 0x0),
    "3.1.25": (0x01DAFF60, 0xE0, 0x8, 0x128, 0x18, 0x0),
}

# 测试用的绝对地址（如果设置，将直接使用此地址而非通过指针链计算）
TEST_ABSOLUTE_ADDRESS = None  # 设置为 None 禁用，或设置为具体地址


class CloudMusicMemoryReader:
    """网易云音乐内存读取器"""

    def __init__(self):
        """初始化读取器"""
        self.process_id = None
        self.version = None
        self.lyrics_address = None
        self.offsets = None
        self._last_lyrics = ""
        self._initialized = False

    def initialize(self) -> bool:
        """
        初始化 - 查找进程、检测版本并解析地址

        Returns:
            初始化是否成功
        """
        # 查找网易云音乐进程
        process = self._find_process()
        if not process:
            print("[CloudMusic] 未找到网易云音乐进程")
            return False

        self.process_id = process.pid
        print(f"[CloudMusic] 找到进程: {process.name()} (PID: {self.process_id})")

        # 检测版本
        self.version = self._detect_version_from_exe(process)
        if self.version:
            print(f"[CloudMusic] 检测到版本: {self.version}")
        else:
            # 如果检测失败，尝试通过地址映射反推版本
            self.version = self._detect_version_by_probe()
            if self.version:
                print(f"[CloudMusic] 通过探测匹配版本: {self.version}")
            else:
                print(f"[CloudMusic] 无法检测版本，使用默认版本 3.1.30")
                self.version = "3.1.30"

        # 解析歌词地址（指针链）
        if not self._resolve_address():
            print("[CloudMusic] 歌词地址解析失败")
            return False

        self._initialized = True
        return True

    def _find_process(self):
        """查找网易云音乐进程"""
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                if proc.info['name'] and 'cloudmusic' in proc.info['name'].lower():
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def _detect_version_from_exe(self, process: psutil.Process) -> Optional[str]:
        """
        从 cloudmusic.exe 的文件版本信息中检测版本号

        Args:
            process: 网易云音乐进程

        Returns:
            版本号字符串，如 "3.1.30"
        """
        try:
            exe_path = process.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

        result = self._get_pe_file_version(exe_path)
        if result:
            major, minor, patch = result
            version_str = f"{major}.{minor}.{patch}"
            if version_str in VERSION_ADDRESS_MAP:
                return version_str
            # 版本不在映射表中，但仍返回以便用户知道实际版本
            return version_str
        return None

    def _get_pe_file_version(self, file_path: str) -> Optional[Tuple[int, int, int]]:
        """
        通过 Windows API 读取 PE 文件的版本号

        Args:
            file_path: 可执行文件路径

        Returns:
            (major, minor, patch) 或 None
        """
        try:
            # GetFileVersionInfoSizeW
            size = ctypes.windll.version.GetFileVersionInfoSizeW(file_path, None)
            if size == 0:
                return None

            buffer = ctypes.create_string_buffer(size)
            if not ctypes.windll.version.GetFileVersionInfoW(file_path, 0, size, buffer):
                return None

            # VerQueryValueW — 取根节点
            ptr = ctypes.c_void_p()
            length = ctypes.c_uint()

            if not ctypes.windll.version.VerQueryValueW(
                buffer, '\\', ctypes.byref(ptr), ctypes.byref(length)
            ):
                return None

            # VS_FIXEDFILEINFO
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
            print(f"[CloudMusic] 读取文件版本失败: {e}")
            return None

    def _detect_version_by_probe(self) -> Optional[str]:
        """
        通过尝试每个版本的内存地址来猜测版本

        Returns:
            最匹配的版本号，或 None
        """
        for version, offsets in VERSION_ADDRESS_MAP.items():
            base_offset = offsets[0]

            # cloudmusic.dll 基址 + 基地址偏移
            dll_base = self._get_module_base("cloudmusic.dll")
            if dll_base is None:
                continue

            candidate_addr = dll_base + base_offset
            # 尝试读一个字节，检查地址是否有效
            try:
                handle = ctypes.windll.kernel32.OpenProcess(
                    0x0010, False, self.process_id
                )
                if not handle:
                    continue
                try:
                    buf = ctypes.c_byte()
                    br = ctypes.c_size_t()
                    result = ctypes.windll.kernel32.ReadProcessMemory(
                        handle, ctypes.c_void_p(candidate_addr),
                        ctypes.byref(buf), ctypes.sizeof(buf), ctypes.byref(br)
                    )
                    if result and br.value > 0:
                        return version
                finally:
                    ctypes.windll.kernel32.CloseHandle(handle)
            except Exception:
                continue
        return None

    def _get_module_base(self, module_name: str) -> Optional[int]:
        """
        获取指定模块在目标进程中的加载基址

        Args:
            module_name: 模块名（如 "cloudmusic.dll"）

        Returns:
            模块基址，或 None
        """
        TH32CS_SNAPMODULE = 0x00000008
        MAX_PATH = 260

        class MODULEENTRY32(ctypes.Structure):
            _fields_ = [
                ('dwSize', ctypes.c_ulong),
                ('th32ModuleID', ctypes.c_ulong),
                ('th32ProcessID', ctypes.c_ulong),
                ('GlblcntUsage', ctypes.c_ulong),
                ('ProccntUsage', ctypes.c_ulong),
                ('modBaseAddr', ctypes.POINTER(ctypes.c_byte)),
                ('modBaseSize', ctypes.c_ulong),
                ('hModule', ctypes.c_void_p),
                ('szModule', ctypes.c_char * (MAX_PATH + 1)),
                ('szExePath', ctypes.c_char * MAX_PATH),
            ]

        kernel32 = ctypes.windll.kernel32
        hSnapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, self.process_id)
        if hSnapshot == -1:
            return None

        try:
            me32 = MODULEENTRY32()
            me32.dwSize = ctypes.sizeof(MODULEENTRY32)

            if not kernel32.Module32First(hSnapshot, ctypes.byref(me32)):
                return None

            while True:
                mod_name = me32.szModule.decode('utf-8', errors='ignore').lower()
                if module_name.lower() in mod_name:
                    return ctypes.cast(me32.modBaseAddr, ctypes.c_void_p).value

                if not kernel32.Module32Next(hSnapshot, ctypes.byref(me32)):
                    break
        finally:
            kernel32.CloseHandle(hSnapshot)

        return None

    def _read_pointer(self, address: int) -> Optional[int]:
        """
        读取指定内存地址的指针值（自动适配 32/64 位）

        Args:
            address: 要读取的内存地址

        Returns:
            指针值，读取失败返回 None
        """
        try:
            handle = ctypes.windll.kernel32.OpenProcess(
                0x0010,  # PROCESS_VM_READ
                False,
                self.process_id,
            )
            if not handle:
                return None

            try:
                # 读取 8 字节（兼容 64 位）
                buf = ctypes.c_uint64()
                br = ctypes.c_size_t()

                result = ctypes.windll.kernel32.ReadProcessMemory(
                    handle,
                    ctypes.c_void_p(address),
                    ctypes.byref(buf),
                    ctypes.sizeof(buf),
                    ctypes.byref(br),
                )

                if result and br.value >= 4:
                    return buf.value
                return None
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception as e:
            print(f"[CloudMusic] 读取指针失败 (地址 0x{address:X}): {e}")
            return None

    def _resolve_address(self) -> bool:
        """
        解析歌词内存地址 — 通过指针链逐级解引用

        VERSION_ADDRESS_MAP 的格式：
            (基地址偏移, 指针偏移1, 指针偏移2, ..., 最终偏移)

        遍历过程：
            addr = dll_base + 基地址偏移
            for 每个偏移 in [指针偏移1, 指针偏移2, ..., 最终偏移]:
                ptr = ReadProcessMemory(addr)   # 读指针
                addr = ptr + 偏移               # 加到下一级
            最终 addr 即为歌词字符串所在地址

        Returns:
            是否解析成功
        """
        # 如果设置了测试绝对地址，直接使用
        if TEST_ABSOLUTE_ADDRESS is not None:
            self.lyrics_address = TEST_ABSOLUTE_ADDRESS
            self.offsets = (TEST_ABSOLUTE_ADDRESS,)
            print(f"[CloudMusic] 使用测试绝对地址: 0x{TEST_ABSOLUTE_ADDRESS:X}")
            return True

        if not self.version:
            return False

        # 查找匹配的版本
        offsets = VERSION_ADDRESS_MAP.get(self.version)
        if offsets is None:
            print(f"[CloudMusic] 版本 {self.version} 无对应地址偏移")
            # 尝试最近版本
            fallback = "3.1.30"
            offsets = VERSION_ADDRESS_MAP.get(fallback)
            if offsets is None:
                return False
            print(f"[CloudMusic] 回退到版本 {fallback} 的偏移")
            self.version = fallback

        self.offsets = offsets

        # 获取 cloudmusic.dll 基址
        dll_base = self._get_module_base("cloudmusic.dll")
        if dll_base is None:
            print("[CloudMusic] 无法获取 cloudmusic.dll 基址，尝试备用方法...")
            # 备用：搜索网易云音乐主模块
            dll_base = self._get_module_base("cloudmusic.exe")
            if dll_base is None:
                print("[CloudMusic] 无法获取任意模块基址")
                return False

        print(f"[CloudMusic] cloudmusic.dll 基址: 0x{dll_base:X}")

        # 第一步：dll_base + 基地址偏移
        addr = dll_base + offsets[0]

        # 后续：逐级读指针 + 加偏移
        for i, offset in enumerate(offsets[1:], start=1):
            ptr = self._read_pointer(addr)
            if ptr is None:
                print(f"[CloudMusic] 指针链第 {i} 步读取失败 (地址 0x{addr:X})")
                return False
            addr = ptr + offset
            # 检查地址是否可能有效
            if addr <= 0x10000 or addr >= 0x7FFFFFFF0000:
                print(f"[CloudMusic] 指针链第 {i} 步得到异常地址 0x{addr:X}")
                return False

        self.lyrics_address = addr
        print(f"[CloudMusic] 歌词地址解析成功: 0x{addr:X}")
        return True

    def read_lyrics(self) -> Optional[str]:
        """
        从内存读取歌词

        Returns:
            歌词文本，读取失败返回 None
        """
        if not self._initialized or not self.process_id:
            return None

        try:
            lyrics = self._read_memory_string(self.lyrics_address)
            if lyrics and lyrics != self._last_lyrics:
                self._last_lyrics = lyrics
                return lyrics
        except Exception as e:
            # 检查进程是否还在
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
        读取内存中的 Unicode 字符串（Windows API）

        Args:
            address: 内存地址
            max_length: 最大字符数

        Returns:
            读取的字符串
        """
        if sys.platform != 'win32':
            print("[CloudMusic] 内存读取仅支持 Windows")
            return None

        try:
            handle = ctypes.windll.kernel32.OpenProcess(
                0x0010,  # PROCESS_VM_READ
                False,
                self.process_id,
            )
            if not handle:
                return None

            try:
                buffer = ctypes.create_string_buffer(max_length * 2)
                bytes_read = ctypes.c_size_t()

                result = ctypes.windll.kernel32.ReadProcessMemory(
                    handle,
                    ctypes.c_void_p(address),
                    buffer,
                    ctypes.sizeof(buffer),
                    ctypes.byref(bytes_read),
                )

                if result:
                    data = buffer.raw[:bytes_read.value]
                    # 找到 UTF-16 字符串结束符
                    null_pos = data.find(b'\x00\x00')
                    if null_pos > 0:
                        data = data[:null_pos]
                    try:
                        return data.decode('utf-16-le').strip('\x00')
                    except UnicodeDecodeError:
                        return None
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)

        except Exception as e:
            print(f"[CloudMusic] 内存读取失败: {e}")

        return None

    def is_ready(self) -> bool:
        """检查进程是否仍在运行"""
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
    查找网易云音乐版本（从文件信息中读取）

    Returns:
        版本字符串，如 "3.1.30"
    """
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            if proc.info['name'] and 'cloudmusic' in proc.info['name'].lower():
                reader = CloudMusicMemoryReader()
                reader.process_id = proc.pid
                version = reader._detect_version_from_exe(proc)
                if version:
                    return version
                # 如果读不到版本号，返回一个占位
                return "unknown"
        except Exception:
            continue
    return None


def get_supported_versions() -> List[str]:
    """获取支持的版本列表"""
    return list(VERSION_ADDRESS_MAP.keys())
