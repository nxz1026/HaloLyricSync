#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
洛雪音乐 (LX Music) 歌词解析与同步播放器

移植自 LX Music 开源项目 (Apache 2.0 License):
https://github.com/lyswhut/lx-music-desktop

移植的核心模块:
  - LinePlayer._initLines      → LxLyricParser.parse
  - LinePlayer._initTag        → LxLyricParser._parse_tags
  - LinePlayer._findCurLineNum → LxLyricPlayer.find_current_line
  - parseExtendedLyric         → LxLyricParser._parse_extended

参考源码:
  - src/common/utils/lyric-font-player/line-player.js
  - src/common/utils/lyric-font-player/index.js

LRC 时间格式支持:
  [mm:ss.xx]            ← 标准 (例 [01:23.45])
  [mm:ss]               ← 无毫秒 (例 [01:23])
  [h:mm:ss]             ← 带小时 (例 [1:23:45])
  [hh:mm:ss]            ← 带小时+前导零
  [mm:ss:xx]            ← 部分老式 (例 [01:23:45])

行内支持多个时间标签:
  [00:00.00][00:05.50]同一句歌词
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Iterable


# === 正则表达式(与 LX Music JS 版完全一致) ===

# 时间字段:匹配行首的多个 [时间] 字段
TIME_FIELD_EXP = re.compile(r'^(?:\[[\d:.]+\])+')

# 单个时间标签:[mm:ss.xx] / [mm:ss] / [h:mm:ss] / [hh:mm:ss.xx]
TIME_EXP = re.compile(r'\d{1,3}(?::\d{1,3}){0,2}(?:\.\d{1,3})')

# 标签正则 [ti:Title]
TAG_REG = {
    'title': 'ti',
    'artist': 'ar',
    'album': 'al',
    'offset': 'offset',
    'by': 'by',
}

# 前导零处理(与 LX Music formatTimeLabel 一致)
T_RXP_1 = re.compile(r'^0+(\d+)')
T_RXP_2 = re.compile(r':0+(\d+)')
T_RXP_3 = re.compile(r'\.0+(\d+)')


def format_time_label(label: str) -> str:
    """
    规范化时间标签字符串(去掉前导零)
    '000:00:00' → '0:0:0'
    '00:01.50'  → '0:1.5'
    """
    label = T_RXP_1.sub(r'\1', label)
    label = T_RXP_2.sub(r':\1', label)
    label = T_RXP_3.sub(r'.\1', label)
    return label


def parse_time_to_ms(time_str: str) -> int:
    """
    把 h:m:s.ms 时间字符串转换为毫秒
    '0:0:5.5'   → 5500
    '1:23:45.6' → 5025600
    """
    parts = time_str.split(':')
    # 补齐到 3 段 (h:m:s)
    while len(parts) < 3:
        parts.insert(0, '0')
    # 处理 's.ms' → ['s', 'ms']
    if len(parts) >= 3 and '.' in parts[2]:
        sec_parts = parts[2].split('.', 1)
        parts = parts[:2] + sec_parts

    try:
        h = int(parts[0]) if parts[0] else 0
        m = int(parts[1]) if parts[1] else 0
        s = int(parts[2]) if parts[2] else 0
        ms = int(parts[3]) if len(parts) > 3 and parts[3] else 0
    except (ValueError, IndexError):
        return 0
    return h * 3600_000 + m * 60_000 + s * 1000 + ms


@dataclass
class LxLyricLine:
    """
    单行歌词(对应 LX Music LinePlayer.lines 中的元素)
    """
    time: int                       # 时间戳(毫秒)
    text: str                       # 主歌词文本
    extended_lyrics: List[str] = field(default_factory=list)  # 翻译/罗马音

    def __repr__(self) -> str:
        return f'LxLyricLine({self.time}ms, {self.text!r}, ext={len(self.extended_lyrics)})'


class LxLyricParser:
    """
    LX Music 风格 LRC 解析器

    与现有 LyricsParser 的差异:
      - 支持行内多个时间标签  [00:00.00][00:05.50]同一句
      - 处理各种格式前导零      [000:00:00] [001:23:45]
      - 翻译/罗马音按时间戳匹配  tlyric 关联到 lyric 的对应行
      - 时间标签本身允许 '.':      [00:01.50] [00:01:50]
    """

    def __init__(self):
        self.lines: List[LxLyricLine] = []
        self.tags: Dict[str, str] = {}
        self.offset_ms: int = 0

    # --- 公开 API ---

    def parse(
        self,
        lrc_text: str,
        extended_lyrics: Optional[Iterable[str]] = None,
    ) -> List[LxLyricLine]:
        """
        解析 LRC 文本

        Args:
            lrc_text: 主歌词 LRC 文本
            extended_lyrics: 翻译/罗马音 LRC 文本列表

        Returns:
            按时间戳排序的歌词行列表
        """
        self.lines = []
        self.tags = self._parse_tags(lrc_text or '')
        self.offset_ms = int(self.tags.get('offset') or 0) if str(self.tags.get('offset') or '').lstrip('-').isdigit() else 0

        lines_map: Dict[str, LxLyricLine] = {}
        self._parse_main_lyric(lrc_text or '', lines_map)

        # 处理翻译/罗马音
        for ext in (extended_lyrics or []):
            self._parse_extended(lines_map, ext)

        self.lines = sorted(lines_map.values(), key=lambda x: x.time)
        return self.lines

    # --- 内部方法 ---

    def _parse_tags(self, lrc_text: str) -> Dict[str, str]:
        """提取 LRC 头部标签 [ti:...], [ar:...], [al:...], [offset:...], [by:...]"""
        tags: Dict[str, str] = {}
        for tag_key, tag_name in TAG_REG.items():
            m = re.search(rf'\[{re.escape(tag_name)}:([^\]]*)\]', lrc_text, re.IGNORECASE)
            tags[tag_key] = m.group(1) if m else ''
        if tags.get('offset'):
            try:
                tags['offset'] = int(tags['offset'])
            except (ValueError, TypeError):
                tags['offset'] = 0
        else:
            tags['offset'] = 0
        return tags

    def _parse_main_lyric(self, lrc_text: str, lines_map: Dict[str, LxLyricLine]) -> None:
        """
        解析主歌词行,与 LX Music LinePlayer._initLines 中的主循环一致
        """
        for raw_line in lrc_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            m = TIME_FIELD_EXP.match(line)
            if not m:
                continue

            time_field = m.group(0)
            # 时间字段之后的内容作为歌词文本
            text = TIME_FIELD_EXP.sub('', line, count=1).strip()

            if not text:
                continue

            times = TIME_EXP.findall(time_field)
            if not times:
                continue

            for time in times:
                time_str = format_time_label(time)
                if time_str in lines_map:
                    # 同一时间戳的歌词追加到 extended_lyrics
                    lines_map[time_str].extended_lyrics.append(text)
                    continue
                ms = parse_time_to_ms(time_str)
                lines_map[time_str] = LxLyricLine(time=ms, text=text)

    def _parse_extended(self, lines_map: Dict[str, LxLyricLine], ext_text: str) -> None:
        """
        处理翻译/罗马音 LRC,通过时间戳关联到主歌词行
        """
        for raw_line in (ext_text or '').splitlines():
            line = raw_line.strip()
            m = TIME_FIELD_EXP.match(line)
            if not m:
                continue

            time_field = m.group(0)
            text = TIME_FIELD_EXP.sub('', line, count=1).strip()
            # LX Music 跳过纯注释行
            if not text or text == '//':
                continue

            times = TIME_EXP.findall(time_field)
            if not times:
                continue

            for time in times:
                time_str = format_time_label(time)
                target = lines_map.get(time_str)
                if target is not None:
                    target.extended_lyrics.append(text)


class LxLyricPlayer:
    """
    LX Music 风格歌词播放器(根据播放进度选择当前行)

    对应 LX Music LinePlayer._findCurLineNum 算法:
        if curTime <= 0  → 0
        找到第一个 time > curTime 的行,返回前一行 (0 行特判为 0)
        如果 curTime 大于所有时间,返回 length - 1
    """

    def __init__(self, lines: Optional[List[LxLyricLine]] = None, offset_ms: int = 0):
        self.lines: List[LxLyricLine] = lines or []
        self.offset_ms = offset_ms  # 来自 [offset:ms] + 用户额外偏移

    def set_lines(self, lines: List[LxLyricLine], offset_ms: int = 0) -> None:
        self.lines = lines
        self.offset_ms = offset_ms

    def find_current_line(self, cur_time_ms: int, start_index: int = 0) -> int:
        """
        找到当前时间对应的歌词行号
        与 LX Music LinePlayer._findCurLineNum 完全一致
        """
        if not self.lines:
            return -1
        if cur_time_ms <= 0:
            return 0
        length = len(self.lines)
        for i in range(start_index, length):
            if cur_time_ms <= self.lines[i].time:
                return 0 if i == 0 else i - 1
        return length - 1

    def get_current_lyric(self, cur_time_ms: int) -> str:
        """根据当前播放进度获取当前行文本(无扩展歌词)"""
        idx = self.find_current_line(cur_time_ms)
        if idx < 0 or idx >= len(self.lines):
            return ''
        return self.lines[idx].text

    def get_current_line(self, cur_time_ms: int) -> Optional[LxLyricLine]:
        """获取当前行对象(包含扩展歌词)"""
        idx = self.find_current_line(cur_time_ms)
        if idx < 0 or idx >= len(self.lines):
            return None
        return self.lines[idx]


__all__ = [
    'LxLyricLine',
    'LxLyricParser',
    'LxLyricPlayer',
    'format_time_label',
    'parse_time_to_ms',
]