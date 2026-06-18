#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HALO PIXELBAR 歌词同步主程序
直接从网易云音乐进程中读取歌词，无需API

参考项目：
- HaloPixelToolBox (https://github.com/XFEstudio/HaloPixelToolBox)
"""

import sys
import time
import threading
import signal
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.memory_reader import CloudMusicMemoryReader, find_cloudmusic_version, get_supported_versions
from src.lyrics_parser import parse_lrc
from src.hid_comm import get_hid_communicator, HaloPixelCommunicator
from src.hid_packet_builder import TextLayout, UIModel


class LyricSynchronizer:
    """歌词同步器 - 使用内存读取方式 + HID通信"""
    
    def __init__(self):
        """初始化"""
        self.config = get_config()
        self.reader = CloudMusicMemoryReader()
        self.hid = get_hid_communicator()
        self.running = False
        self.current_song_id = None
        self.current_lyric = None
        self.current_position_ms = 0
        self.last_lyric_index = -1
        self.last_lyrics_text = ""
        self.scroll_mode = False
        self.clock_mode = False
    
    def start(self):
        """启动同步器"""
        if self.running:
            print("[Sync] 已在运行中")
            return
        
        self.running = True
        print("[Sync] 开始歌词同步...")
        
        # 初始化网易云音乐内存读取器
        print("[Sync] 初始化网易云音乐内存读取器...")
        if not self.reader.initialize():
            print("[Sync] 网易云音乐未运行或版本不支持")
            print(f"[Sync] 支持的版本: {', '.join(get_supported_versions())}")
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
        
        while self.running:
            try:
                # 检查网易云音乐是否还在运行
                if not self.reader.is_ready():
                    print("[Sync] 网易云音乐已关闭，等待重新启动...")
                    time.sleep(2)
                    if self.reader.initialize():
                        print("[Sync] 网易云音乐已重新连接")
                        show_startup = True
                    continue
                
                # 读取歌词
                lyrics = self.reader.read_lyrics()
                
                if lyrics and lyrics != self.last_lyrics_text:
                    self.last_lyrics_text = lyrics
                    no_lyrics_count = 0
                    
                    if self.clock_mode:
                        self.clock_mode = False
                        self.scroll_mode = False
                        print("[Sync] 恢复歌词显示模式")
                    
                    if show_startup:
                        print(f"\n{'='*60}")
                        print("[Sync] 网易云歌词同步已启动!")
                        print(f"[Sync] 版本: {self.reader.version}")
                        print(f"{'='*60}\n")
                        show_startup = False
                    
                    self._process_lyrics(lyrics)
                else:
                    no_lyrics_count += 1
                    # 连续30秒无歌词变化，切换到时钟UI
                    if no_lyrics_count > 600:  # 30秒 * 20次
                        self._switch_to_clock_ui()
                        no_lyrics_count = 0
                
                time.sleep(0.05)  # 50ms刷新间隔
                
            except Exception as e:
                print(f"[Sync] 同步错误: {e}")
                time.sleep(1)
    
    def _process_lyrics(self, lyrics: str):
        """
        处理歌词文本
        
        Args:
            lyrics: 原始歌词文本
        """
        # 检查是否包含 LRC 时间戳（[mm:ss.xx] 格式）
        if self._looks_like_lrc(lyrics):
            try:
                parser = parse_lrc(lyrics)
                if len(parser) > 0:
                    current_line = parser[0]
                    self._display_lyric(current_line.text, current_line.index, len(parser))
                    return
            except Exception:
                pass

        # 直接显示原始歌词
        self._display_lyric(lyrics.strip(), 0, 1)

    @staticmethod
    def _looks_like_lrc(text: str) -> bool:
        """
        粗略判断文本是否为 LRC 格式（包含 [mm:ss.xx] 时间戳）

        Args:
            text: 待检测文本

        Returns:
            是否可能是 LRC 格式
        """
        import re
        return bool(re.search(r'\[\d{1,2}:\d{1,2}[.:]\d{1,3}\]', text))
    
    def _display_lyric(self, text: str, line_index: int = 0, total_lines: int = 1):
        """
        显示歌词
        
        Args:
            text: 歌词文本
            line_index: 行索引
            total_lines: 总行数
        """
        if not text:
            return
        
        print(f"[Lyric] {text}")
        
        # 截断过长的文本
        max_chars = self.config.get('lyrics', 'max_chars_per_line', fallback=20)
        text = text[:max_chars]
        
        # 根据文本长度决定布局
        if len(text) > 15:
            # 长文本使用滚动模式
            if not self.scroll_mode:
                self.hid.set_text_layout(TextLayout.SCROLL_RIGHT_TO_LEFT)
                self.scroll_mode = True
                time.sleep(0.3)
        else:
            # 短文本使用居中模式
            if self.scroll_mode:
                self.hid.set_text_layout(TextLayout.CENTER)
                self.scroll_mode = False
                time.sleep(0.1)
        
        # 发送到HID设备
        success = self.hid.send_lyric_line(text, line_index, total_lines)
        
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
    
    # 检查网易云音乐
    version = find_cloudmusic_version()
    if version:
        print(f"✅ 网易云音乐: 运行中 (版本: {version})")
        supported = get_supported_versions()
        if version in supported:
            print("  └── 版本支持: ✅")
        else:
            print("  └── 版本支持: ⚠️  可能需要更新地址偏移")
    else:
        print("❌ 网易云音乐: 未运行")
        print("   请确保已安装并运行网易云音乐，且开启了桌面歌词功能")
    
    print()
    print("支持的网易云音乐版本:")
    for v in get_supported_versions():
        print(f"  - {v}")
    
    print()
    print("使用方法:")
    print("  1. 打开网易云音乐")
    print("  2. 播放任意歌曲")
    print("  3. 开启桌面歌词功能")
    print("  4. 运行本程序")


def main():
    """主函数"""
    print("=" * 60)
    print("HALO PIXELBAR 歌词同步器")
    print("(内存读取 + HID协议)")
    print("=" * 60)
    
    import argparse
    
    parser = argparse.ArgumentParser(
        description="HALO PIXELBAR 歌词同步器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python src/main.py              # 启动同步器
  python src/main.py --status     # 检查状态
  python src/main.py --list-devices  # 列出HID设备

前提条件:
  1. 网易云音乐已安装并运行
  2. 网易云音乐开启了桌面歌词功能
  3. 电脑已连接 HALO PIXELBAR 音箱
  4. 以管理员权限运行（Windows)
        """
    )
    parser.add_argument("--list-devices", action="store_true", help="列出可用的HID设备")
    parser.add_argument("--status", action="store_true", help="检查网易云音乐状态")
    parser.add_argument("--port", type=str, help="指定设备路径")
    parser.add_argument("--config", type=str, help="配置文件路径")
    
    args = parser.parse_args()
    
    if args.list_devices:
        list_devices()
        return
    
    if args.status:
        check_status()
        return
    
    # 初始化
    if args.config:
        get_config(args.config)
    
    # 创建并启动同步器
    synchronizer = LyricSynchronizer()
    
    # 如果指定了设备路径
    if args.port:
        print(f"[Main] 使用指定设备: {args.port}")
        synchronizer.hid.connect(args.port)
    
    try:
        synchronizer.start()
        
        # 保持主线程运行
        while synchronizer.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[Main] 用户中断")
    finally:
        synchronizer.stop()


if __name__ == "__main__":
    main()
