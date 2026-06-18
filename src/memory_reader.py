#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
歌词内存读取器（兼容层）

⚠️ 本模块已被重构为 src.source 架构。本文件仅保留旧 API 兼容。

默认源：洛雪音乐（LX Music）
旧 API：CloudMusicMemoryReader 已重命名为 CloudMusicSource，请使用 src.source。

参考项目：HaloPixelToolBox (https://github.com/XFEstudio/HaloPixelToolBox)
"""

from src.source import (
    LxMusicSource as _LxMusicSource,
    CloudMusicSource as _CloudMusicSource,
    create_source,
)
from src.source import cloudmusic as _cm_module


# 版本地址表（保留为兼容旧 API）
VERSION_ADDRESS_MAP = getattr(_cm_module, 'CLOUDMUSIC_VERSION_ADDRESS_MAP', {})
TEST_ABSOLUTE_ADDRESS = None


# 兼容旧类名
class CloudMusicMemoryReader(_CloudMusicSource):
    """网易云音乐内存读取器（兼容旧 API）"""


class LxMusicMemoryReader(_LxMusicSource):
    """洛雪音乐读取器"""


def find_cloudmusic_version():
    """兼容旧函数 - 创建临时 reader 检测网易云版本"""
    import psutil
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            if proc.info.get('name') and 'cloudmusic' in proc.info['name'].lower():
                reader = CloudMusicMemoryReader()
                reader.process_id = proc.pid
                version = reader._detect_version(proc)
                if version:
                    return version
                return 'unknown'
        except Exception:
            continue
    return None


def get_supported_versions():
    """兼容旧函数 - 获取网易云支持的版本列表"""
    return list(VERSION_ADDRESS_MAP.keys())


__all__ = [
    'CloudMusicMemoryReader',
    'LxMusicMemoryReader',
    'find_cloudmusic_version',
    'get_supported_versions',
    'VERSION_ADDRESS_MAP',
    'TEST_ABSOLUTE_ADDRESS',
    'create_source',
]