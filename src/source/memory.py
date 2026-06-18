#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内存读取基类

提供通用的 Windows 进程内存读取工具。
"""

import ctypes
import ctypes.wintypes
import struct
from typing import Optional, List, Tuple

import psutil


# Windows API 常量
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ_QUERY = PROCESS_VM_READ | PROCESS_QUERY_INFORMATION

TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
MAX_PATH = 260

kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
ntdll = ctypes.windll.ntdll


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


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('BaseAddress', ctypes.c_void_p),
        ('AllocationBase', ctypes.c_void_p),
        ('AllocationProtect', ctypes.c_ulong),
        ('RegionSize', ctypes.c_size_t),
        ('State', ctypes.c_ulong),
        ('Protect', ctypes.c_ulong),
        ('Type', ctypes.c_ulong),
    ]


class MemoryReader:
    """Windows 进程内存读取工具"""

    def __init__(self, pid: int):
        self.pid = pid
        self._handle = None

    @property
    def handle(self):
        if self._handle is None:
            self._handle = kernel32.OpenProcess(PROCESS_VM_READ_QUERY, False, self.pid)
        return self._handle

    def close(self):
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None

    def read_bytes(self, address: int, size: int) -> bytes:
        """读取指定地址的字节"""
        h = self.handle
        if not h:
            return b''
        buf = ctypes.create_string_buffer(size)
        br = ctypes.c_size_t()
        ok = kernel32.ReadProcessMemory(
            h, ctypes.c_uint64(address), buf, size, ctypes.byref(br),
        )
        return buf.raw[:br.value] if ok else b''

    def read_qword(self, address: int) -> int:
        """读取 8 字节无符号整数"""
        raw = self.read_bytes(address, 8)
        return struct.unpack('<Q', raw)[0] if len(raw) == 8 else 0

    def read_u32(self, address: int) -> int:
        """读取 4 字节无符号整数"""
        raw = self.read_bytes(address, 4)
        return struct.unpack_from('<I', raw)[0] if len(raw) == 4 else 0

    def read_utf16_string(self, address: int, max_chars: int = 512) -> str:
        """读取 UTF-16 LE 编码字符串"""
        raw = self.read_bytes(address, max_chars * 2)
        if not raw:
            return ''
        # 找字符串结尾
        null_pos = raw.find(b'\x00\x00')
        if null_pos >= 0:
            raw = raw[:null_pos]
        try:
            return raw.decode('utf-16-le', errors='replace').strip('\x00')
        except UnicodeDecodeError:
            return ''

    def read_utf8_string(self, address: int, max_bytes: int = 1024) -> str:
        """读取 UTF-8 编码字符串"""
        raw = self.read_bytes(address, max_bytes)
        if not raw:
            return ''
        null_pos = raw.find(b'\x00')
        if null_pos >= 0:
            raw = raw[:null_pos]
        try:
            return raw.decode('utf-8', errors='replace')
        except UnicodeDecodeError:
            return ''

    def get_module_base(self, module_name: str) -> Optional[Tuple[int, int]]:
        """
        获取指定模块的加载基址与 SizeOfImage

        Returns:
            (base_address, size_of_image) 或 None
        """
        module_name_l = module_name.lower()
        h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, self.pid)
        if h_snap == -1 or h_snap == 0:
            return None
        try:
            me32 = MODULEENTRY32()
            me32.dwSize = ctypes.sizeof(MODULEENTRY32)
            if not kernel32.Module32First(h_snap, ctypes.byref(me32)):
                return None
            while True:
                mod_name = me32.szModule.decode('utf-8', errors='ignore').lower()
                if module_name_l in mod_name:
                    base = ctypes.cast(me32.modBaseAddr, ctypes.c_void_p).value
                    return base, me32.modBaseSize
                if not kernel32.Module32Next(h_snap, ctypes.byref(me32)):
                    break
        finally:
            kernel32.CloseHandle(h_snap)
        return None

    def list_modules(self) -> List[Tuple[int, int, str]]:
        """
        枚举进程加载的所有模块

        Returns:
            [(base, size_of_image, name), ...]
        """
        result = []
        h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, self.pid)
        if h_snap == -1 or h_snap == 0:
            return result
        try:
            me32 = MODULEENTRY32()
            me32.dwSize = ctypes.sizeof(MODULEENTRY32)
            if not kernel32.Module32First(h_snap, ctypes.byref(me32)):
                return result
            while True:
                base = ctypes.cast(me32.modBaseAddr, ctypes.c_void_p).value
                name = me32.szModule.decode('utf-8', errors='ignore')
                result.append((base, me32.modBaseSize, name))
                if not kernel32.Module32Next(h_snap, ctypes.byref(me32)):
                    break
        finally:
            kernel32.CloseHandle(h_snap)
        return result

    def find_peb(self) -> int:
        """通过 NtQueryInformationProcess 读取 PEB 地址"""
        class PBI(ctypes.Structure):
            _fields_ = [
                ('Reserved1', ctypes.c_void_p),
                ('PebBaseAddress', ctypes.c_void_p),
                ('Reserved2', ctypes.c_void_p * 2),
                ('UniqueProcessId', ctypes.c_void_p),
                ('Reserved3', ctypes.c_void_p),
            ]
        h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, self.pid)
        if not h:
            return 0
        try:
            pbi = PBI()
            rl = ctypes.c_ulong()
            NtQueryInformationProcess = ntdll.NtQueryInformationProcess
            NtQueryInformationProcess.restype = ctypes.c_long
            NtQueryInformationProcess.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong),
            ]
            NtQueryInformationProcess(h, 0, ctypes.byref(pbi), ctypes.sizeof(pbi), ctypes.byref(rl))
            return pbi.PebBaseAddress or 0
        finally:
            kernel32.CloseHandle(h)

    def list_modules_peb(self) -> List[Tuple[int, int, str]]:
        """
        通过 PEB->Ldr->InMemoryOrderModuleList 枚举模块（64 位进程）

        用于 TH32CS_SNAPMODULE 在某些情况下失败时的备用方案。
        """
        result = []
        peb = self.find_peb()
        if not peb:
            return result
        # PEB.Ldr at +0x18
        ldr = self.read_qword(peb + 0x18)
        if not ldr:
            return result
        # PEB_LDR_DATA.InMemoryOrderModuleList at Ldr + 0x20
        head = self.read_qword(ldr + 0x20)
        if not head:
            return result

        seen = set()
        cur = head
        for _ in range(500):
            entry = cur - 0x10  # InMemoryOrderLinks is at entry + 0x10
            if entry in seen or entry <= 0:
                break
            seen.add(entry)
            base = self.read_qword(entry + 0x30)
            size = self.read_u32(entry + 0x40)
            # BaseDllName UNICODE_STRING at entry + 0x58
            name_buf = self.read_qword(entry + 0x60)
            if name_buf:
                name = self.read_utf16_string(name_buf, 128)
            else:
                name = ''
            if base:
                result.append((base, size, name))
            cur = self.read_qword(cur)
            if cur == head:
                break
        return result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()