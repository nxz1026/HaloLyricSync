#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐歌词地址自动扫描器

功能：
1. 自动扫描进程内存查找歌词字符串
2. 追踪指针链找出稳定地址
3. 输出可用于 memory_reader.py 的地址配置

使用方法：
    python address_scanner.py

前提条件：
    - Windows 系统
    - 网易云音乐运行中
    - 已开启桌面歌词
    - 播放一首歌曲
"""

import sys
import ctypes
import struct
from pathlib import Path
from typing import Optional, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


try:
    import psutil
except ImportError:
    print("[错误] 需要安装 psutil: pip install psutil")
    sys.exit(1)


PROCESS_ALL_ACCESS = 0x1F0FFF


class MemoryScanner:
    """内存扫描器"""

    def __init__(self, process_id: int):
        self.process_id = process_id
        self.process_handle = None

    def __enter__(self):
        if sys.platform != 'win32':
            raise OSError("仅支持 Windows 系统")

        kernel32 = ctypes.windll.kernel32
        self.process_handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, self.process_id)
        if not self.process_handle:
            raise OSError(f"无法打开进程 (PID: {self.process_id})")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.process_handle:
            ctypes.windll.kernel32.CloseHandle(self.process_handle)

    def read_memory(self, address: int, size: int) -> Optional[bytes]:
        """读取进程内存"""
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t()

        result = ctypes.windll.kernel32.ReadProcessMemory(
            self.process_handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(bytes_read)
        )

        if result and bytes_read.value > 0:
            return buffer.raw[:bytes_read.value]
        return None

    def read_pointer(self, address: int) -> Optional[int]:
        """读取指针值（32位或64位地址）"""
        if sys.maxsize > 2**32:
            data = self.read_memory(address, 8)
            if data:
                return struct.unpack('<Q', data)[0]
        else:
            data = self.read_memory(address, 4)
            if data:
                return struct.unpack('<I', data)[0]
        return None

    def read_string(self, address: int, max_length: int = 500) -> Optional[str]:
        """读取 Unicode 字符串"""
        data = self.read_memory(address, max_length * 2)
        if not data:
            return None

        null_pos = data.find(b'\x00\x00')
        if null_pos > 0:
            data = data[:null_pos]

        try:
            return data.decode('utf-16-le').strip('\x00')
        except:
            return None

    def get_module_base(self, module_name: str) -> Optional[int]:
        """获取模块基地址"""
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                if proc.pid == self.process_id:
                    for module in proc.memory_maps():
                        if module_name.lower() in module.path.lower():
                            return int(module.addr, 16)
            except:
                pass
        return None


def find_cloudmusic_process() -> Optional[psutil.Process]:
    """查找网易云音乐进程"""
    print("[扫描] 查找网易云音乐进程...")

    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            if proc.info['name'] and 'cloudmusic' in proc.info['name'].lower():
                version = "未知"
                try:
                    version = proc.version()
                except:
                    pass
                print(f"[找到] 进程: {proc.info['name']} (PID: {proc.pid})")
                print(f"[找到] 版本: {version}")
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return None


def scan_for_lyrics_string(scanner: MemoryScanner, lyrics_hint: str) -> List[Tuple[int, str]]:
    """
    扫描内存查找歌词字符串

    Args:
        scanner: 内存扫描器
        lyrics_hint: 歌词提示字符串

    Returns:
        匹配的地址列表
    """
    if not lyrics_hint:
        print("[错误] 请提供歌词提示")
        return []

    print(f"\n[扫描] 搜索歌词: \"{lyrics_hint}\"")
    print("[扫描] 这可能需要几秒钟...")

    matches = []
    hint_bytes = lyrics_hint.encode('utf-16-le')

    MEM_RANGE = 0x10000000
    STEP = 0x1000

    for base in range(0x10000, MEM_RANGE, STEP):
        try:
            data = scanner.read_memory(base, STEP)
            if not data:
                continue

            pos = 0
            while True:
                idx = data.find(hint_bytes, pos)
                if idx == -1:
                    break

                addr = base + idx
                try_str = scanner.read_string(addr, 200)
                if try_str and lyrics_hint in try_str:
                    matches.append((addr, try_str[:80]))
                    print(f"[发现] 地址: 0x{addr:08X} -> \"{try_str[:50]}...\"")

                pos = idx + 1

                if len(matches) >= 20:
                    print("[提示] 已找到足够多的候选地址，停止扫描")
                    return matches

        except:
            continue

    return matches


def find_pointer_chain(scanner: MemoryScanner, target_addr: int, dll_base: int) -> Optional[Tuple[int, List[int]]]:
    """
    尝试追踪指针链

    从目标地址向前搜索可能的指针引用
    """
    print(f"\n[追踪] 分析地址 0x{target_addr:08X} 的指针链...")

    search_range = 0x100000
    pointers = []

    for search_base in range(max(0x10000, dll_base - search_range), dll_base + 0x5000000, 0x1000):
        try:
            data = scanner.read_memory(search_base, 0x1000)
            if not data:
                continue

            for i in range(0, len(data) - 4, 4):
                ptr_value = struct.unpack('<I', data[i:i+4])[0]
                if abs(ptr_value - target_addr) < 0x100:
                    chain_addr = search_base + i
                    pointers.append(chain_addr)
                    print(f"[指针候选] 0x{chain_addr:08X} -> 0x{ptr_value:08X}")

                    if len(pointers) >= 10:
                        return (dll_base, pointers[:5])

        except:
            continue

    return None if not pointers else (dll_base, pointers[:5])


def find_static_address(scanner: MemoryScanner, string_addr: int, dll_base: int) -> Optional[Tuple[int, List[int]]]:
    """
    查找静态地址

    策略：
    1. 在 DLL 范围内搜索指向目标地址的指针
    2. 验证这些指针的稳定性
    """
    print(f"\n[分析] 在 DLL 范围内搜索指针引用...")

    static_pointers = []
    dll_size = 0x5000000

    STEP = 0x10000
    for base in range(dll_base, dll_base + dll_size, STEP):
        try:
            data = scanner.read_memory(base, min(STEP, 0x100000))
            if not data:
                continue

            for i in range(0, len(data) - 4, 4):
                try:
                    ptr = struct.unpack('<I', data[i:i+4])[0]
                    if dll_base <= ptr < dll_base + dll_size:
                        continue

                    if ptr == string_addr:
                        chain_addr = base + i
                        static_pointers.append(chain_addr)
                        print(f"[静态指针] 0x{chain_addr:08X} -> 0x{ptr:08X}")

                except:
                    continue

        except:
            continue

    if static_pointers:
        return (dll_base, static_pointers[:3])

    return None


def generate_address_code(version: str, base_addr: int, offsets: List[int]) -> str:
    """生成可用于 memory_reader.py 的代码"""
    offset_hex = ', '.join(f'0x{o:08X}' for o in offsets)
    return f'    "{version}": ({offset_hex}),'


def main():
    print()
    print("=" * 60)
    print("网易云音乐歌词地址自动扫描器")
    print("=" * 60)

    if sys.platform != 'win32':
        print("[错误] 此工具仅支持 Windows 系统")
        sys.exit(1)

    process = find_cloudmusic_process()
    if not process:
        print("\n[错误] 未找到网易云音乐进程")
        print("[提示] 请确保：")
        print("  1. 网易云音乐已安装并运行")
        print("  2. 正在播放歌曲")
        print("  3. 已开启桌面歌词功能")
        sys.exit(1)

    version = "未知"
    try:
        version = process.version()
        if version:
            major, minor, patch = version.split('.')[:3]
            version = f"{major}.{minor}.{patch}"
    except:
        pass

    try:
        dll_base = None
        try:
            # 尝试使用 memory_maps grouped
            for module in process.memory_maps(grouped=False):
                if hasattr(module, 'path') and 'cloudmusic.dll' in module.path.lower():
                    if hasattr(module, 'addr'):
                        dll_base = int(module.addr, 16)
                    elif hasattr(module, 'rss'):
                        # 某些版本的 psutil 返回不同结构
                        dll_base = int(getattr(module, 'addr', '0x1D00000'), 16)
                    print(f"[信息] cloudmusic.dll 基址: 0x{dll_base:08X}")
                    break
        except:
            pass
        
        if not dll_base:
            # 备用方法：查找进程模块
            import ctypes.wintypes
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
                    ('szExePath', ctypes.c_char * MAX_PATH)
                ]
            
            hSnapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, process.pid)
            if hSnapshot != -1:
                me32 = MODULEENTRY32()
                me32.dwSize = ctypes.sizeof(MODULEENTRY32)
                
                if ctypes.windll.kernel32.Module32First(hSnapshot, ctypes.byref(me32)):
                    while True:
                        module_name = me32.szModule.decode('utf-8', errors='ignore').lower()
                        if 'cloudmusic.dll' in module_name:
                            dll_base = ctypes.cast(me32.modBaseAddr, ctypes.c_void_p).value
                            print(f"[信息] cloudmusic.dll 基址: 0x{dll_base:08X}")
                            break
                        if not ctypes.windll.kernel32.Module32Next(hSnapshot, ctypes.byref(me32)):
                            break
                
                ctypes.windll.kernel32.CloseHandle(hSnapshot)
        
        if not dll_base:
            print("[警告] 未找到 cloudmusic.dll，尝试使用默认基址")
            dll_base = 0x1D00000

    except Exception as e:
        print(f"[错误] 获取模块信息失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print()
    print("=" * 60)
    print("扫描模式选择")
    print("=" * 60)
    print("1. 快速扫描 - 输入当前歌词文本进行扫描")
    print("2. 穷举扫描 - 扫描所有可能区域（较慢）")
    print()

    mode = input("请选择扫描模式 (1/2) [默认 1]: ").strip() or "1"

    lyrics_hint = ""
    if mode == "1":
        print()
        lyrics_hint = input("请输入当前显示的歌词文本: ").strip()
        if not lyrics_hint:
            print("[错误] 必须输入歌词文本")
            sys.exit(1)

    try:
        with MemoryScanner(process.pid) as scanner:
            print("\n" + "=" * 60)
            print("开始扫描...")
            print("=" * 60)

            if lyrics_hint:
                matches = scan_for_lyrics_string(scanner, lyrics_hint)

                if not matches:
                    print("\n[结果] 未找到匹配的歌词地址")
                    print("[提示] 尝试：")
                    print("  1. 确保歌词已正确显示")
                    print("  2. 使用更长的歌词片段")
                    print("  3. 尝试播放其他歌曲")
                else:
                    print(f"\n[结果] 找到 {len(matches)} 个候选地址")

                    print("\n" + "=" * 60)
                    print("分析指针链")
                    print("=" * 60)

                    for addr, content in matches[:3]:
                        result = find_static_address(scanner, addr, dll_base)
                        if result:
                            base, pointers = result
                            print(f"\n[成功] 找到静态指针!")
                            print(f"  DLL 基址: 0x{base:08X}")
                            print(f"  指针链: {[f'0x{p:08X}' for p in pointers]}")

                            offsets = pointers + [0x0]
                            print("\n" + "=" * 60)
                            print("可用的地址配置")
                            print("=" * 60)
                            print(f'\n将以下代码添加到 memory_reader.py 的 VERSION_ADDRESS_MAP:\n')
                            print(generate_address_code(version, base, offsets))
                            break
                    else:
                        print("\n[提示] 未找到稳定的静态指针")
                        print("[建议] 手动使用 Cheat Engine 进行分析")
            else:
                print("[提示] 穷举扫描功能开发中...")
                print("[提示] 请使用模式1并提供歌词文本")

    except OSError as e:
        print(f"[错误] {e}")
        print("[提示] 可能需要管理员权限运行")
    except Exception as e:
        print(f"[错误] 扫描失败: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 60)
    print("扫描完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
