#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
歌词源抽象基类

定义统一的歌词源接口，支持多种播放器（网易云、洛雪音乐等）
"""

from abc import ABC, abstractmethod
from typing import Optional
import psutil


class LyricsSource(ABC):
    """歌词源抽象基类"""

    def __init__(self):
        self.process_id: Optional[int] = None
        self.version: Optional[str] = None
        self._initialized = False

    @property
    @abstractmethod
    def name(self) -> str:
        """播放器名称（用于日志展示）"""

    @property
    @abstractmethod
    def process_keywords(self) -> list:
        """进程名/可执行文件名关键字列表（用于查找进程）"""

    @abstractmethod
    def find_process(self) -> Optional[psutil.Process]:
        """查找播放器进程"""

    @abstractmethod
    def initialize(self) -> bool:
        """初始化（查找进程、解析地址等）"""

    @abstractmethod
    def read_lyrics(self) -> Optional[str]:
        """读取当前歌词"""

    @abstractmethod
    def is_ready(self) -> bool:
        """检查源是否就绪"""

    @property
    def is_running(self) -> bool:
        """检查播放器是否在运行"""
        return self.is_ready()

    def close(self) -> None:
        """清理资源（可由子类覆盖）"""
        self._initialized = False

    def shutdown(self) -> None:
        """关闭源并释放资源（与 close 同义，命名遵循 Python RAII 习惯）"""
        self.close()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} version={self.version} pid={self.process_id}>"