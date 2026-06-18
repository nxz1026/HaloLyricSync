#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
歌词源工厂

根据配置选择合适的歌词源实现。
"""

from typing import Optional

from .base import LyricsSource
from .lxmusic import LxMusicSource
from .cloudmusic import CloudMusicSource


# 支持的 source 类型
SOURCE_TYPES = ('lxmusic', 'cloudmusic')


def create_source(source_type: str = 'lxmusic', **kwargs) -> LyricsSource:
    """
    创建歌词源

    Args:
        source_type: 源类型，'lxmusic' 或 'cloudmusic'
        **kwargs: 传递给 source 构造函数的参数

    Returns:
        LyricsSource 实例
    """
    source_type = (source_type or 'lxmusic').lower()
    if source_type == 'lxmusic':
        return LxMusicSource(**kwargs)
    elif source_type == 'cloudmusic':
        return CloudMusicSource(**kwargs)
    else:
        raise ValueError(f"未知的歌词源类型: {source_type}（支持: {SOURCE_TYPES}）")


__all__ = [
    'LyricsSource',
    'LxMusicSource',
    'CloudMusicSource',
    'create_source',
    'SOURCE_TYPES',
]