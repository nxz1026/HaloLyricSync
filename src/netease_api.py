#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐API - 获取当前播放状态和歌词
支持多种方式获取网易云音乐播放状态
"""

import json
import time
import requests
from typing import Dict, Optional, Tuple
from pathlib import Path
from urllib.parse import quote

from .config import get_config


class NeteaseApiError(Exception):
    """网易云音乐API错误"""
    pass


class NeteaseApi:
    """网易云音乐API客户端"""
    
    def __init__(self, config=None):
        """
        初始化API客户端
        
        Args:
            config: 配置对象
        """
        self.config = config or get_config()
        self.host = self.config.get('netease', 'host', fallback='127.0.0.1')
        self.port = self.config.get('netease', 'port', fallback=50545)
        self.base_url = f"http://{self.host}:{self.port}"
        self.session = requests.Session()
        self.session.timeout = self.config.get('netease', 'api_timeout', fallback=5)
        self.last_song_id = None
        self.cache_dir = Path.home() / ".halo_lrc_sync" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def is_available(self) -> bool:
        """
        检查API是否可用
        
        Returns:
            API是否可用
        """
        try:
            response = self.session.get(f"{self.base_url}/ping", timeout=2)
            return response.status_code == 200
        except Exception:
            return False
    
    def get_current_play_status(self) -> Optional[Dict]:
        """
        获取当前播放状态
        
        Returns:
            播放状态字典，包含歌曲信息和播放进度
            示例: {
                "playing": True,
                "song_id": 123456,
                "song_name": "歌曲名",
                "artist": "歌手名",
                "album": "专辑名",
                "position_ms": 12345,
                "duration_ms": 240000
            }
        """
        try:
            # 方式1: 通过本地API获取（需要网易云音乐本地API服务）
            response = self.session.get(f"{self.base_url}/player/current")
            if response.status_code == 200:
                data = response.json()
                return self._parse_play_status(data)
        except Exception as e:
            print(f"[Netease] 本地API获取失败: {e}")
        
        # 如果本地API不可用，尝试其他方式
        return self._get_play_status_alternative()
    
    def _parse_play_status(self, data: Dict) -> Optional[Dict]:
        """
        解析播放状态数据
        
        Args:
            data: API返回的原始数据
            
        Returns:
            解析后的播放状态
        """
        if not data or "data" not in data:
            return None
        
        data = data["data"]
        
        return {
            "playing": data.get("playing", False),
            "song_id": data.get("id"),
            "song_name": data.get("name", ""),
            "artist": ", ".join([a.get("name", "") for a in data.get("ar", [])]),
            "album": data.get("al", {}).get("name", ""),
            "position_ms": data.get("progress", 0),
            "duration_ms": data.get("dt", 0)
        }
    
    def _get_play_status_alternative(self) -> Optional[Dict]:
        """
        备用方式获取播放状态（通过剪贴板或其他方式）
        
        Returns:
            播放状态或None
        """
        try:
            # 方式2: 尝试通过pywin32读取网易云音乐窗口标题（Windows）
            # 这里实现简化版本
            return None
        except Exception as e:
            print(f"[Netease] 备用获取方式失败: {e}")
            return None
    
    def get_lyrics(self, song_id: int) -> Optional[str]:
        """
        获取歌词
        
        Args:
            song_id: 歌曲ID
            
        Returns:
            LRC格式歌词文本
        """
        # 先检查缓存
        cache_path = self.cache_dir / f"{song_id}.lrc"
        if cache_path.exists():
            print(f"[Netease] 使用缓存歌词: {song_id}")
            return cache_path.read_text(encoding="utf-8")
        
        try:
            # 方式1: 通过本地API获取
            response = self.session.get(f"{self.base_url}/lyric?id={song_id}")
            if response.status_code == 200:
                data = response.json()
                lrc = data.get("lrc", {}).get("lyric", "")
                if lrc:
                    # 保存到缓存
                    cache_path.write_text(lrc, encoding="utf-8")
                    return lrc
        except Exception as e:
            print(f"[Netease] 本地API获取歌词失败: {e}")
        
        # 方式2: 通过公开API获取
        return self._get_lyrics_public(song_id)
    
    def _get_lyrics_public(self, song_id: int) -> Optional[str]:
        """
        通过公开API获取歌词
        
        Args:
            song_id: 歌曲ID
            
        Returns:
            歌词文本
        """
        try:
            # 示例：使用一个公开的歌词API（需要替换为实际可用的API）
            url = f"https://music-api.example.com/lyric?id={song_id}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                lrc = data.get("lrc", "")
                if lrc:
                    cache_path = self.cache_dir / f"{song_id}.lrc"
                    cache_path.write_text(lrc, encoding="utf-8")
                    return lrc
        except Exception as e:
            print(f"[Netease] 公开API获取歌词失败: {e}")
        
        return None
    
    def search_song(self, keyword: str, limit: int = 10) -> list:
        """
        搜索歌曲
        
        Args:
            keyword: 搜索关键词
            limit: 结果数量限制
            
        Returns:
            搜索结果列表
        """
        try:
            url = f"{self.base_url}/search?keywords={quote(keyword)}&limit={limit}"
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                songs = data.get("result", {}).get("songs", [])
                return songs
        except Exception as e:
            print(f"[Netease] 搜索歌曲失败: {e}")
        
        return []
    
    def wait_for_song_change(self, poll_interval: float = 1.0) -> Optional[Dict]:
        """
        等待歌曲变化
        
        Args:
            poll_interval: 轮询间隔（秒）
            
        Returns:
            新的播放状态
        """
        while True:
            status = self.get_current_play_status()
            if status and status["song_id"] != self.last_song_id:
                self.last_song_id = status["song_id"]
                return status
            time.sleep(poll_interval)


# 单例模式
_api_instance = None

def get_netease_api() -> NeteaseApi:
    """获取网易云音乐API单例"""
    global _api_instance
    if _api_instance is None:
        _api_instance = NeteaseApi()
    return _api_instance
