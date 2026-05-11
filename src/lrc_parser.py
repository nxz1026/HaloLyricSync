#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
歌词解析器 - 支持标准LRC格式解析
"""

import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class LyricLine:
    """歌词行数据结构"""
    time_ms: int  # 时间戳（毫秒）
    text: str     # 歌词文本
    index: int    # 行索引
    
    def __str__(self) -> str:
        return f"[{self.time_to_str()}] {self.text}"
    
    def time_to_str(self) -> str:
        """时间戳转字符串格式 [mm:ss.xx]"""
        total_seconds = self.time_ms / 1000
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:05.2f}"


class LrcParser:
    """LRC歌词解析器"""
    
    # LRC时间戳正则表达式 [mm:ss.xx] 或 [mm:ss:xx]
    TIME_PATTERN = re.compile(r'\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]')
    
    # 标签正则表达式 [tag:value]
    TAG_PATTERN = re.compile(r'\[([a-z]+):([^\]]*)\]', re.IGNORECASE)
    
    def __init__(self):
        self.lines: List[LyricLine] = []
        self.tags: Dict[str, str] = {}
        self.content: str = ""
    
    def parse(self, lrc_content: str) -> 'LrcParser':
        """
        解析LRC歌词内容
        
        Args:
            lrc_content: LRC格式歌词文本
            
        Returns:
            解析器自身，支持链式调用
        """
        self.content = lrc_content
        self.lines = []
        self.tags = {}
        
        lines = lrc_content.splitlines()
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # 解析标签
            tag_match = self.TAG_PATTERN.match(line)
            if tag_match and not self.TIME_PATTERN.match(line):
                tag_name = tag_match.group(1).lower()
                tag_value = tag_match.group(2).strip()
                self.tags[tag_name] = tag_value
                continue
            
            # 解析歌词行
            self._parse_lyric_line(line, line_num)
        
        # 按时间排序
        self.lines.sort(key=lambda x: x.time_ms)
        
        # 重新分配索引
        for idx, lyric_line in enumerate(self.lines):
            lyric_line.index = idx
        
        return self
    
    def _parse_lyric_line(self, line: str, line_num: int) -> None:
        """
        解析单行歌词
        
        Args:
            line: 歌词行
            line_num: 行号
        """
        # 查找所有时间戳
        time_matches = list(self.TIME_PATTERN.finditer(line))
        
        if not time_matches:
            return
        
        # 提取歌词文本（最后一个时间戳之后的内容）
        last_match = time_matches[-1]
        text = line[last_match.end():].strip()
        
        # 解析每个时间戳
        for match in time_matches:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            
            # 解析毫秒部分
            centiseconds_str = match.group(3) or "00"
            # 支持 [mm:ss.xx] 或 [mm:ss:xx]
            if len(centiseconds_str) == 3:
                # 直接是毫秒
                centiseconds = int(centiseconds_str)
            else:
                # 百分秒转毫秒
                centiseconds = int(centiseconds_str.ljust(3, '0')[:3])
            
            time_ms = minutes * 60 * 1000 + seconds * 1000 + centiseconds
            
            self.lines.append(LyricLine(
                time_ms=time_ms,
                text=text,
                index=len(self.lines)
            ))
    
    def get_lyric_at_time(self, time_ms: int) -> Optional[LyricLine]:
        """
        获取指定时间对应的歌词
        
        Args:
            time_ms: 时间戳（毫秒）
            
        Returns:
            对应时间的歌词行，如果没有返回None
        """
        if not self.lines:
            return None
        
        # 二分查找
        left, right = 0, len(self.lines) - 1
        result_idx = 0
        
        while left <= right:
            mid = (left + right) // 2
            if self.lines[mid].time_ms <= time_ms:
                result_idx = mid
                left = mid + 1
            else:
                right = mid - 1
        
        return self.lines[result_idx] if self.lines else None
    
    def get_lyric_by_index(self, index: int) -> Optional[LyricLine]:
        """
        根据索引获取歌词
        
        Args:
            index: 歌词索引
            
        Returns:
            歌词行
        """
        if 0 <= index < len(self.lines):
            return self.lines[index]
        return None
    
    def get_tag(self, tag_name: str, default: str = "") -> str:
        """
        获取LRC标签值
        
        Args:
            tag_name: 标签名
            default: 默认值
            
        Returns:
            标签值
        """
        return self.tags.get(tag_name.lower(), default)
    
    @property
    def title(self) -> str:
        """歌曲标题"""
        return self.get_tag("ti", self.get_tag("title"))
    
    @property
    def artist(self) -> str:
        """艺术家"""
        return self.get_tag("ar", self.get_tag("artist"))
    
    @property
    def album(self) -> str:
        """专辑"""
        return self.get_tag("al", self.get_tag("album"))
    
    @property
    def duration_ms(self) -> int:
        """歌曲时长（毫秒）"""
        if not self.lines:
            return 0
        return self.lines[-1].time_ms + 10000  # 最后一行+10秒
    
    def __len__(self) -> int:
        """歌词行数"""
        return len(self.lines)
    
    def __getitem__(self, index: int) -> LyricLine:
        """索引访问"""
        return self.lines[index]
    
    def __str__(self) -> str:
        """字符串表示"""
        result = []
        for key, value in self.tags.items():
            result.append(f"[{key}:{value}]")
        for line in self.lines:
            result.append(str(line))
        return "\n".join(result)


def parse_lrc(lrc_content: str) -> LrcParser:
    """
    便捷函数 - 解析LRC歌词
    
    Args:
        lrc_content: LRC歌词文本
        
    Returns:
        解析器对象
    """
    return LrcParser().parse(lrc_content)
