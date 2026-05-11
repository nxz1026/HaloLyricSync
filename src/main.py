#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HALO OIXELBAR 歌词同步主程序
自动获取网易云音乐歌词并同步显示到音箱
支持自动启动 NeteaseCloudMusicApi
"""

import sys
import time
import threading
import signal
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_config
from src.netease_api import get_netease_api
from src.lrc_parser import parse_lrc
from src.usb_comm import get_usb_communicator


class LyricSynchronizer:
    """歌词同步器"""
    
    def __init__(self):
        """初始化"""
        self.config = get_config()
        self.netease = get_netease_api()
        self.usb = get_usb_communicator()
        self.running = False
        self.current_song_id = None
        self.current_lyric = None
        self.current_position_ms = 0
        self.last_lyric_index = -1
        self.song_start_time = 0
        self._lock = threading.Lock()
        self._api_server = None
    
    def start(self, auto_start_api: bool = True):
        """
        启动同步器
        
        Args:
            auto_start_api: 是否自动启动 NeteaseCloudMusicApi
        """
        if self.running:
            print("[Sync] 已在运行中")
            return
        
        self.running = True
        print("[Sync] 开始歌词同步...")
        
        if auto_start_api:
            self._start_api_server()
        
        if not self.usb.connect():
            print("[Sync] USB设备连接失败，使用模拟模式")
        
        sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        sync_thread.start()
        
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
    
    def _start_api_server(self):
        """启动 NeteaseCloudMusicApi 服务器"""
        try:
            from src.api_server import get_api_server
            self._api_server = get_api_server()
            
            if not self._api_server.is_server_running():
                print("[Sync] 正在启动 NeteaseCloudMusicApi...")
                if self._api_server.start():
                    print("[Sync] API 服务器启动成功")
                else:
                    print("[Sync] API 服务器启动失败，请手动启动或检查 Node.js 是否安装")
            else:
                print("[Sync] API 服务器已在运行")
                
        except ImportError:
            print("[Sync] 未找到 api_server 模块，跳过自动启动")
        except Exception as e:
            print(f"[Sync] API 服务器启动异常: {e}")
    
    def stop(self):
        """停止同步器"""
        print("[Sync] 正在停止...")
        self.running = False
        self.usb.clear_display()
        self.usb.disconnect()
        
        if self._api_server:
            self._api_server.stop()
        
        print("[Sync] 已停止")
    
    def _handle_interrupt(self, signum, frame):
        """处理中断信号"""
        print("\n[Sync] 收到中断信号")
        self.stop()
        sys.exit(0)
    
    def _sync_loop(self):
        """主同步循环"""
        while self.running:
            try:
                status = self.netease.get_current_play_status()
                
                if not status:
                    time.sleep(1)
                    continue
                
                if status["song_id"] != self.current_song_id:
                    if status["song_id"]:
                        self._load_new_song(status)
                    else:
                        self._clear_display()
                    time.sleep(0.5)
                    continue
                
                if not status["playing"]:
                    time.sleep(0.5)
                    continue
                
                self._sync_lyrics(status)
                
            except Exception as e:
                print(f"[Sync] 同步错误: {e}")
                time.sleep(1)
    
    def _load_new_song(self, status: dict):
        """加载新歌曲"""
        with self._lock:
            song_id = status["song_id"]
            song_name = status.get("song_name", "")
            artist = status.get("artist", "")
            
            print(f"[Sync] 新歌曲: {song_name} - {artist}")
            
            lrc_text = self.netease.get_lyrics(song_id)
            if lrc_text:
                self.current_lyric = parse_lrc(lrc_text)
                print(f"[Sync] 歌词加载成功，共 {len(self.current_lyric)} 行")
            else:
                self.current_lyric = None
                print("[Sync] 无法获取歌词")
            
            self.current_song_id = song_id
            self.last_lyric_index = -1
            self.current_position_ms = 0
            self.song_start_time = time.time() * 1000 - status.get("position_ms", 0)
            
            self.usb.show_song_info(song_name, artist)
            time.sleep(2)
    
    def _sync_lyrics(self, status: dict):
        """同步歌词显示"""
        if not self.current_lyric:
            return
        
        position_ms = status.get("position_ms", 0)
        lyric_line = self.current_lyric.get_lyric_at_time(position_ms)
        
        if not lyric_line:
            return
        
        if lyric_line.index != self.last_lyric_index:
            self.last_lyric_index = lyric_line.index
            self._display_lyric(lyric_line)
    
    def _display_lyric(self, lyric_line):
        """显示歌词"""
        if not lyric_line.text:
            return
        
        print(f"[Lyric] [{lyric_line.time_to_str()}] {lyric_line.text}")
        
        success = self.usb.send_lyric_line(
            text=lyric_line.text,
            line_index=lyric_line.index,
            total_lines=len(self.current_lyric) if self.current_lyric else 1
        )
        
        if not success:
            print("[Sync] 歌词发送失败")
    
    def _clear_display(self):
        """清空显示"""
        self.usb.clear_display()
        self.current_song_id = None
        self.current_lyric = None
        self.last_lyric_index = -1


def list_devices():
    """列出所有USB设备"""
    print("可用的串口设备:")
    devices = get_usb_communicator().list_devices()
    
    if not devices:
        print("  未找到设备")
        return
    
    for i, device in enumerate(devices, 1):
        print(f"  {i}. {device.port} - {device.description}")
        print(f"     HWID: {device.hwid}")


def check_api_server():
    """检查 API 服务器状态"""
    try:
        from src.api_server import get_api_server
        server = get_api_server()
        
        print("NeteaseCloudMusicApi 状态:")
        print(f"  - 已安装: {'是' if server.is_installed() else '否'}")
        print(f"  - 运行中: {'是' if server.is_server_running() else '否'}")
        
        if not server.is_installed():
            print("\n提示: 运行 python src/main.py --install-api 自动安装")
        elif not server.is_server_running():
            print("\n提示: 运行 python src/main.py --start-api 启动服务器")
            
    except ImportError:
        print("[错误] 未找到 api_server 模块")
    except Exception as e:
        print(f"[错误] {e}")


def install_api_server():
    """安装 NeteaseCloudMusicApi"""
    try:
        from src.api_server import get_api_server
        server = get_api_server()
        
        print("[提示] 开始安装 NeteaseCloudMusicApi...")
        print("[提示] 这可能需要几分钟时间，请耐心等待...")
        
        if server.download_and_install():
            print("[成功] 安装完成!")
        else:
            print("[失败] 安装失败，请检查日志")
            
    except ImportError:
        print("[错误] 未找到 api_server 模块")
    except Exception as e:
        print(f"[错误] {e}")


def start_api_server():
    """启动 API 服务器"""
    try:
        from src.api_server import get_api_server
        server = get_api_server()
        
        if server.start():
            print("[成功] API 服务器已启动")
            print("[提示] 服务器地址: http://localhost:3000")
        else:
            print("[失败] 服务器启动失败")
            
    except ImportError:
        print("[错误] 未找到 api_server 模块")
    except Exception as e:
        print(f"[错误] {e}")


def stop_api_server():
    """停止 API 服务器"""
    try:
        from src.api_server import get_api_server
        server = get_api_server()
        
        if server.stop():
            print("[成功] API 服务器已停止")
            
    except ImportError:
        print("[错误] 未找到 api_server 模块")
    except Exception as e:
        print(f"[错误] {e}")


def main():
    """主函数"""
    print("=" * 60)
    print("HALO OIXELBAR 歌词同步器")
    print("=" * 60)
    
    import argparse
    
    parser = argparse.ArgumentParser(description="HALO OIXELBAR 歌词同步器")
    parser.add_argument("--list-devices", action="store_true", help="列出可用的串口设备")
    parser.add_argument("--check-api", action="store_true", help="检查 API 服务器状态")
    parser.add_argument("--install-api", action="store_true", help="安装 NeteaseCloudMusicApi")
    parser.add_argument("--start-api", action="store_true", help="启动 NeteaseCloudMusicApi")
    parser.add_argument("--stop-api", action="store_true", help="停止 NeteaseCloudMusicApi")
    parser.add_argument("--no-auto-api", action="store_true", help="不同步启动 API 服务器")
    parser.add_argument("--port", type=str, help="指定串口设备")
    parser.add_argument("--config", type=str, help="配置文件路径")
    
    args = parser.parse_args()
    
    if args.list_devices:
        list_devices()
        return
    
    if args.check_api:
        check_api_server()
        return
    
    if args.install_api:
        install_api_server()
        return
    
    if args.start_api:
        start_api_server()
        return
    
    if args.stop_api:
        stop_api_server()
        return
    
    if args.config:
        get_config(args.config)
    
    synchronizer = LyricSynchronizer()
    
    if args.port:
        print(f"[Main] 使用指定端口: {args.port}")
        get_usb_communicator().connect(args.port)
    
    try:
        auto_start_api = not args.no_auto_api
        synchronizer.start(auto_start_api=auto_start_api)
        
        while synchronizer.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[Main] 用户中断")
    finally:
        synchronizer.stop()


if __name__ == "__main__":
    main()
