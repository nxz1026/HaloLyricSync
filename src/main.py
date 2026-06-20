#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HALO PIXELBAR 歌词同步主程序
通过 LX Music 开放 API 实时读取歌词,经 HID 协议同步到音箱

参考项目：
- HaloPixelToolBox (https://github.com/XFEstudio/HaloPixelToolBox)
"""

import sys
import time
import threading
import signal
from pathlib import Path

# Windows GBK 终端下打印 Unicode（含 emoji/特殊设备名字符）会抛 UnicodeEncodeError。
# 这里把 stdout/stderr 强制改回 UTF-8，并用 errors='replace' 兜底，避免 --list-devices / --status 崩溃。
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[attr-defined]
except Exception:
    pass

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.source import create_source
from src.lyrics_parser import parse_lrc, LyricsParser
from src.hid_comm import get_hid_communicator, HaloPixelCommunicator
from src.hid_packet_builder import TextLayout, UIModel


class TrayApp:
    """系统托盘图标（Windows 通知区域）。

    无右键菜单（用户要求），仅显示图标表示后台运行。
    双击恢复控制台窗口。
    依赖: pip install \"halo-lyric-sync[tray]\"
    """

    def __init__(self, synchronizer: "LyricSynchronizer"):
        self.sync = synchronizer
        self._icon = None

    def run(self):
        """启动托盘图标（阻塞）。"""
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            print("[Tray] pystray 未安装，跳过托盘图标")
            print("[Tray] 安装: pip install \"halo-lyric-sync[tray]\"")
            return

        # 生成一个 64x64 的简单图标（蓝色圆点）
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([8, 8, 56, 56], fill=(0, 120, 215, 255))

        # 无右键菜单 —— 用一个空的 Menu 对象
        menu = pystray.Menu()

        self._icon = pystray.Icon(
            "halo_lyric_sync",
            img,
            "HALO PixelBar 歌词同步器\n后台运行中",
            menu,
        )

        # 双击恢复窗口
        self._icon.on_activate = self._on_activate

        print("[Tray] 托盘图标已启动（双击恢复窗口）")
        # 隐藏控制台
        self._hide_console()
        self._icon.run()

    def _on_activate(self):
        """双击托盘图标 — 恢复控制台窗口。"""
        self._show_console()
        print("[Tray] 已恢复控制台窗口")

    def stop(self):
        """退出托盘图标。"""
        if self._icon:
            self._icon.stop()
            self._icon = None

    @staticmethod
    def _hide_console():
        """隐藏控制台窗口。"""
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            hwnd = kernel32.GetConsoleWindow()
            if hwnd:
                kernel32.ShowWindow(hwnd, 0)
        except Exception:
            pass

    @staticmethod
    def _show_console():
        """恢复控制台窗口。"""
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            hwnd = kernel32.GetConsoleWindow()
            if hwnd:
                kernel32.ShowWindow(hwnd, 5)  # SW_SHOW
        except Exception:
            pass


class LyricSynchronizer:
    """歌词同步器 - 使用可插拔歌词源 + HID通信"""

    def __init__(self, source=None):
        """
        初始化

        Args:
            source: 可选的歌词源实例，为 None 时从配置创建
        """
        self.config = get_config()
        self.reader = source or self._create_source_from_config()
        self.hid = get_hid_communicator()
        self.running = False
        self.current_song_id = None
        self.current_lyric = None
        self.current_position_ms = 0
        self.last_lyric_index = -1
        self.last_lyrics_text = ""
        self.scroll_mode = False
        self.clock_mode = False
        # 用于 LRC 时间同步
        self._parsed_lrc: LyricsParser | None = None
        self._last_song_key: str = ""
        # 切歌后, LX Music 会把"歌名-歌手"塞进 LRC 第 0 行; 需要 progress_ms >= 第 1 行 time_ms 才显示
        self._post_transition_min_progress_ms: int = 0
        self._stop_event = threading.Event()
        # 切歌过渡
        self._song_transition = False
        self._transition_start: float = 0.0
        self._transition_duration: float = 0.0
        self._current_progress_index = 0
        self._current_progress_total = 0

    def _create_source_from_config(self):
        """根据配置创建歌词源"""
        source_type = self.config.get('source', 'type', default='lxmusic')
        if source_type == 'lxmusic':
            return create_source('lxmusic',
                                api_url=self.config.get('source', 'lxmusic', 'api_url', default='') or None)
        elif source_type == 'cloudmusic':
            test_addr = self.config.get('source', 'cloudmusic', 'test_absolute_address', default=None)
            return create_source('cloudmusic', test_absolute_address=test_addr)
        else:
            print(f"[Main] 未知的 source type: {source_type}，使用默认 lxmusic")
            return create_source('lxmusic')
    
    def start(self):
        """启动同步器"""
        if self.running:
            print("[Sync] 已在运行中")
            return

        self.running = True
        self._stop_event.clear()
        print("[Sync] 开始歌词同步...")

        # 初始化歌词源
        print(f"[Sync] 初始化歌词源: {self.reader.name}...")
        if not self.reader.initialize():
            print(f"[Sync] {self.reader.name} 未运行或不可用")
            if hasattr(self.reader, 'last_error') and self.reader.last_error:
                print(f"[Sync] 原因: {self.reader.last_error}")
            return

        # 连接HID设备
        if not self.hid.connect():
            print("[Sync] HID设备连接失败，使用模拟模式")

        # 启动主循环线程
        sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        sync_thread.start()

        # 注册信号处理
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
    
    def stop(self):
        """停止同步器"""
        print("[Sync] 正在停止...")
        self.running = False
        self._stop_event.set()
        # 关闭歌词源(停止 SSE 线程等)
        if hasattr(self.reader, 'shutdown'):
            self.reader.shutdown()
        self.hid.clear_display()
        self.hid.disconnect()
        print("[Sync] 已停止")
    
    def _handle_interrupt(self, signum, frame):
        """处理中断信号"""
        print("\n[Sync] 收到中断信号")
        self.stop()
        sys.exit(0)
    
    def _sync_loop(self):
        """主同步循环"""
        show_startup = True
        no_lyrics_count = 0
        SAMPLE_RATE_S = 0.05  # 50ms
        
        while self.running:
            try:
                # 检查播放器是否还在运行
                if not self.reader.is_ready():
                    print(f"[Sync] {self.reader.name} 已关闭，等待重新启动...")
                    if self._stop_event.wait(2):
                        return
                    if self.reader.initialize():
                        print(f"[Sync] {self.reader.name} 已重新连接")
                        show_startup = True
                    continue

                # 读全量快照（含 LRC 全文 + 进度）
                snapshot = self.reader.get_full_snapshot() if hasattr(self.reader, 'get_full_snapshot') else None
                lrc_text = snapshot.lyric if snapshot else None
                progress_ms = snapshot.progress_ms if snapshot else 0
                song_key = f"{snapshot.song_name}::{snapshot.singer}" if snapshot else ""

                # 切歌检测
                if song_key and song_key != self._last_song_key:
                    self._last_song_key = song_key
                    # 切歌后清空去重缓存,确保新歌词第一行写入
                    self.last_lyrics_text = ""
                    self.last_lyric_index = -1
                    # 重载 LRC
                    if lrc_text:
                        try:
                            self._parsed_lrc = parse_lrc(lrc_text)
                            total = len(self._parsed_lrc.lines) if self._parsed_lrc else 0
                            print(f"[Sync] LRC 已加载: {total} 行")
                            # 计算过渡期最小进度(跳过 LRC 第 0 行疑似"歌名-歌手"过渡文本)
                            if self._parsed_lrc and len(self._parsed_lrc.lines) >= 2:
                                self._post_transition_min_progress_ms = self._parsed_lrc.lines[1].time_ms
                            else:
                                self._post_transition_min_progress_ms = 0
                        except Exception:
                            self._parsed_lrc = None
                            self._post_transition_min_progress_ms = 0
                    # 切歌过渡(无论是否显示歌曲信息, 都启用过渡期屏蔽 LX Music 切歌头发的“歌名-歌手”过渡文本)
                    transition_s = float(self.config.get('lyrics', 'song_info_duration_s', default=3))
                    if self.config.get('lyrics', 'display_song_info', default=True) and snapshot:
                        self._show_song_info(snapshot.song_name, snapshot.singer)
                    else:
                        # 仅设置过渡标志, 不发歌名到 HID
                        self._transition_start = time.monotonic()
                        self._transition_duration = max(transition_s, 1.0)
                        self._song_transition = True
                        self.last_lyrics_text = ""

                # 切歌过渡期：显示歌曲信息中,过期后由主循环退出
                if self._song_transition:
                    if time.monotonic() - self._transition_start >= self._transition_duration:
                        self._song_transition = False
                    display_text = None
                else:
                    # 从 LRC 按进度取当前行
                    display_text = None
                    if (
                        self._parsed_lrc
                        and len(self._parsed_lrc) > 0
                        and progress_ms > 0
                        and progress_ms >= self._post_transition_min_progress_ms
                        and not self._song_transition
                    ):
                        current_line = self._parsed_lrc.get_lyric_at_time(progress_ms)
                        if current_line and current_line.text:
                            display_text = current_line.text
                            self._current_progress_index = current_line.index
                            self._current_progress_total = len(self._parsed_lrc.lines)
                            if current_line.index != self.last_lyric_index:
                                self.last_lyric_index = current_line.index
                                print(f"[Lyric] ({current_line.index}) {current_line.text}")

                # fallback: lyricLineText（歌曲头或无 LRC 时）
                if not display_text and not self._song_transition:
                    raw_text = (self.reader.read_lyrics() or "").strip()
                    if raw_text:
                        display_text = raw_text

                if display_text:
                    self._display_lyric(display_text)
                    no_lyrics_count = 0
                    if show_startup:
                        print(f"\n{'='*60}")
                        print(f"[Sync] {self.reader.name} 歌词同步已启动!")
                        print(f"[Sync] 版本: {self.reader.version}")
                        print(f"{'='*60}\n")
                        show_startup = False
                else:
                    no_lyrics_count += 1
                    if no_lyrics_count > int(30 / SAMPLE_RATE_S):  # 30秒无歌词
                        self._switch_to_clock_ui()
                        no_lyrics_count = 0

                # 用 Event.wait 替代 time.sleep，立即响应退出
                if self._stop_event.wait(SAMPLE_RATE_S):
                    return
                
            except Exception as e:
                print(f"[Sync] 同步错误: {e}")
                if self._stop_event.wait(1):
                    return
    
    def _show_song_info(self, song_name: str, singer: str):
        """切歌时显示歌曲信息,过渡期由主循环计时（非阻塞）。"""
        if not song_name and not singer:
            return
        info = f"{song_name} - {singer}" if singer else song_name
        # 过渡期最少 1.0 秒(避免 song_info_duration_s=0 导致过渡闪退,跳出后 LRC (0) 行仍可能是“歌手-歌名”)
        duration = max(float(self.config.get('lyrics', 'song_info_duration_s', default=3)), 1.0)
        print(f"[Sync] 切换歌曲: {info}")
        self.hid.set_text_layout(TextLayout.CENTER)
        self.hid.send_text(f"{info}")
        # 记录过渡期起点+长度,由主循环检查 elapsed;不阻塞 _sync_loop
        self._transition_start = time.monotonic()
        self._transition_duration = duration
        self._song_transition = True
        # 强制下次写入新歌词(清空去重缓存)
        self.last_lyrics_text = ""

    def _display_lyric(self, text: str, line_index: int = 0, total_lines: int = 1):
        """
        显示歌词

        Args:
            text: 歌词文本
            line_index: 行索引（从 0 开始）
            total_lines: 总行数
        """
        if not text:
            return

        # 行号/进度指示（配置开关）
        show_progress = self.config.get('lyrics', 'show_progress', default=True)
        if show_progress and total_lines > 1:
            progress_suffix = f"[{line_index + 1}/{total_lines}]"
            text = text + progress_suffix

        # 截断过长的文本
        max_chars = self.config.get('lyrics', 'max_chars_per_line', default=20)
        text = text[:max_chars]

        # 去重:同一文本不重复发送(进度停滞/暂停时避免刷屏)
        if text == self.last_lyrics_text:
            return
        self.last_lyrics_text = text
        
        # 根据文本长度决定布局
        if len(text) > 15:
            # 长文本使用滚动模式
            if not self.scroll_mode:
                self.hid.set_text_layout(TextLayout.SCROLL_RIGHT_TO_LEFT)
                self.scroll_mode = True
                if self._stop_event.wait(0.3):
                    return
        else:
            # 短文本使用居中模式
            if self.scroll_mode:
                self.hid.set_text_layout(TextLayout.CENTER)
                self.scroll_mode = False
                if self._stop_event.wait(0.1):
                    return
        
        # 发送到HID设备
        success = self.hid.send_lyric_line(text)
        
        if not success:
            print("[Sync] 歌词发送失败")
    
    def _switch_to_clock_ui(self):
        """切换到时钟UI模式"""
        if self.clock_mode:
            return
        try:
            self.hid.set_ui_mode(UIModel.CLOCK)
            self.hid.set_text_layout(TextLayout.CENTER)
            self.scroll_mode = False
            self.clock_mode = True
            print("[Sync] 切换到时钟UI模式")
        except Exception as e:
            print(f"[Sync] 切换UI模式失败: {e}")
    
    def _clear_display(self):
        """清空显示"""
        self.hid.clear_display()
        self.current_lyric = None
        self.last_lyrics_text = ""


def list_devices():
    """列出所有HID设备"""
    print("=" * 60)
    print("HID设备列表")
    print("=" * 60)
    HaloPixelCommunicator.print_all_devices()


def check_status():
    """检查状态"""
    print("=" * 60)
    print("状态检查")
    print("=" * 60)

    config = get_config()
    source_type = config.get('source', 'type', default='lxmusic')
    print(f"当前歌词源: {source_type}")

    # 检查洛雪音乐
    source = create_source(source_type)
    if source.find_process():
        print(f"✅ {source.name}: 运行中 (PID: {source.process_id})")
        if source.version:
            print(f"  └── 版本: {source.version}")
        print("  └── 请确保已开启桌面歌词功能")
    else:
        print(f"❌ {source.name}: 未运行")
        print(f"   请确保已安装并运行{source.name}，且开启了桌面歌词功能")

    print()
    print("使用方法:")
    print(f"  1. 打开{source.name}")
    print("  2. 播放任意歌曲")
    print(f"  3. 开启{source.name}桌面歌词功能")
    print("  4. 运行本程序")
    print()
    print("切换歌词源:")
    print("  编辑 ~/.halo_lrc_sync/config.json 中的 source.type")


def hide_console():
    """隐藏控制台窗口（Windows），实现后台运行。"""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.GetConsoleWindow.restype = ctypes.c_void_p
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            kernel32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="HALO PIXELBAR 歌词同步器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python src/main.py                   # 启动同步器
  python src/main.py --minimized       # 后台运行（隐藏窗口）
  python src/main.py --status          # 检查状态
  python src/main.py --list-devices    # 列出HID设备
  python src/main.py --color red       # 指定颜色

前提条件:
  1. LX Music (洛雪音乐) 已安装并运行
  2. LX Music 已开启开放 API (设置 -> 开放 API)
  3. 电脑已连接 HALO PIXELBAR 音箱
  4. 以管理员权限运行（Windows)
        """
    )
    parser.add_argument("--version", action="version", version="halo-lyric-sync 1.1.0")
    parser.add_argument("--list-devices", action="store_true", help="列出可用的HID设备")
    parser.add_argument("--status", action="store_true", help="检查 LX Music 状态")
    parser.add_argument("--send", type=str, metavar="TEXT", help="发送自定义文本到设备并退出")
    parser.add_argument("--port", type=str, help="指定设备路径")
    parser.add_argument("--config", type=str, help="配置文件路径")
    parser.add_argument("--minimized", action="store_true",
                        help="后台运行（隐藏控制台窗口，无托盘图标）")
    parser.add_argument("--tray", action="store_true",
                        help="系统托盘常驻（隐藏窗口 + 托盘图标，双击恢复）")
    parser.add_argument("--color", type=str, default=None,
                        choices=["white", "red", "green", "blue", "yellow", "cyan", "magenta"],
                        help="歌词颜色（默认 white）")
    
    args = parser.parse_args()

    # --minimized 或 --tray 时隐藏窗口
    if args.minimized:
        hide_console()
    elif args.tray:
        # 先隐藏窗口，后续由 TrayApp.run() 控制
        hide_console()

    print("=" * 60)
    print("HALO PIXELBAR 歌词同步器")
    print("(内存读取 + HID协议)")
    if args.minimized:
        print("(后台模式)")
    if args.tray:
        print("(托盘模式 — 双击图标恢复窗口)")
    print("=" * 60)

    if args.list_devices:
        list_devices()
        return

    if args.status:
        check_status()
        return

    if args.send:
        from src.hid_comm import get_hid_communicator
        from src.hid_packet_builder import TextColor
        hid = get_hid_communicator()
        if not hid.connect():
            print("[FAIL] HID 设备连接失败")
            return
        send_color = TextColor[args.color.upper()] if args.color else None
        hid.send_text(args.send, color=send_color)
        print(f"[OK] 已发送: {args.send}")
        hid.disconnect()
        return

    # 初始化
    if args.config:
        get_config(args.config)

    # --color 覆盖配置
    if args.color:
        config = get_config()
        config.set('hid', 'color', value=args.color)

    synchronizer = LyricSynchronizer()

    if args.port:
        print(f"[Main] 使用指定设备: {args.port}")
        synchronizer.hid.connect(args.port)

    try:
        synchronizer.start()

        if args.tray:
            # 托盘模式：TrayApp.run() 阻塞，双击恢复窗口
            tray_app = TrayApp(synchronizer)
            tray_app.run()
        else:
            # 普通/后台模式：保持主线程运行
            synchronizer._stop_event.wait()
    except KeyboardInterrupt:
        print("\n[Main] 用户中断")
    finally:
        synchronizer.stop()
        if args.tray and 'tray_app' in locals():
            tray_app.stop()


if __name__ == "__main__":
    main()
