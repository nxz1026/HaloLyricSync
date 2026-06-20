"""tests.test_lyrics_parser — LRC 歌词解析器测试"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lyrics_parser import parse_lrc, LyricsParser


LRC_SAMPLE = """[ti:测试歌曲]
[ar:测试歌手]
[al:测试专辑]
[00:01.00]第一句歌词
[00:05.50]第二句歌词
[00:10.00]第三句歌词
[00:15.00]
"""


class TestParseLrc:
    def test_parses_all_lines(self):
        parser = parse_lrc(LRC_SAMPLE)
        # 4 timestamps: 00:01.00, 00:05.50, 00:10.00, 00:15.00 (empty text)
        assert len(parser.lines) == 4

    def test_tags_parsed(self):
        parser = parse_lrc(LRC_SAMPLE)
        assert parser.title == "测试歌曲"
        assert parser.artist == "测试歌手"

    def test_get_lyric_at_time_first_line(self):
        parser = parse_lrc(LRC_SAMPLE)
        line = parser.get_lyric_at_time(500)  # 0.5s, should be first
        assert line is not None
        assert "第一句" in line.text

    def test_get_lyric_at_time_second_line(self):
        parser = parse_lrc(LRC_SAMPLE)
        line = parser.get_lyric_at_time(6000)  # 6s, should be second
        assert line is not None
        assert "第二句" in line.text

    def test_get_lyric_at_time_last_line(self):
        parser = parse_lrc(LRC_SAMPLE)
        line = parser.get_lyric_at_time(12000)  # 12s, should be third
        assert line is not None
        assert "第三句" in line.text

    def test_empty_lrc_returns_empty(self):
        parser = parse_lrc("")
        assert len(parser) == 0

    def test_no_timestamp_lines_ignored(self):
        parser = parse_lrc("这是一行没有时间戳的文本\n[00:01.00]有歌词")
        assert len(parser) == 1

    def test_duration_ms(self):
        parser = parse_lrc(LRC_SAMPLE)
        assert parser.duration_ms >= 15000


class TestLyricLine:
    def test_time_to_str(self):
        from src.lyrics_parser import LyricLine
        line = LyricLine(time_ms=65000, text="hello", index=0)
        assert line.time_to_str() == "01:05.00"

    def test_str_representation(self):
        from src.lyrics_parser import LyricLine
        line = LyricLine(time_ms=1000, text="hello", index=0)
        assert "[00:01.00]" in str(line)
