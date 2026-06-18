#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
歌词源模块 - 支持多种播放器

支持的源:
  - lxmusic   : 洛雪音乐 (默认, LX Music)
  - cloudmusic: 网易云音乐 (旧版保留,迁入分支未完成 3.1.35 支持)

使用方法:
    from src.source import create_source
    source = create_source('lxmusic')
    if source.initialize():
        lyric = source.read_lyrics()
"""

from .base import LyricsSource
from .lxmusic import LxMusicSource, LxPlayerSnapshot
from .cloudmusic import CloudMusicSource
from .lx_lyric_player import (
    LxLyricLine,
    LxLyricParser,
    LxLyricPlayer,
    format_time_label,
    parse_time_to_ms,
)
from .factory import create_source, SOURCE_TYPES

__all__ = [
    'LyricsSource',
    'LxMusicSource',
    'LxPlayerSnapshot',
    'CloudMusicSource',
    'LxLyricLine',
    'LxLyricParser',
    'LxLyricPlayer',
    'create_source',
    'SOURCE_TYPES',
]