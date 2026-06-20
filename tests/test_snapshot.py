"""tests.test_snapshot — LxPlayerSnapshot 构造和 from_api_dict 测试"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.source.lxmusic import LxPlayerSnapshot, LX_STATUS_PLAYING, LX_STATUS_PAUSED


class TestLxPlayerSnapshot:
    def test_defaults(self):
        snap = LxPlayerSnapshot()
        assert snap.is_playing is False
        assert snap.song_name == ""
        assert snap.progress_ms == 0
        assert snap.duration_ms == 0
        assert snap.playback_rate == 1.0

    def test_has_lyric_true(self):
        snap = LxPlayerSnapshot(lyric_line_text="hello")
        assert snap.has_lyric is True

    def test_has_lyric_false_when_empty(self):
        snap = LxPlayerSnapshot(lyric_line_text="")
        assert snap.has_lyric is False

    def test_has_lyric_false_when_whitespace(self):
        snap = LxPlayerSnapshot(lyric_line_text="   ")
        assert snap.has_lyric is False


class TestFromApiDict:
    def test_full_data(self):
        data = {
            "status": "playing",
            "name": "晴天",
            "singer": "周杰伦",
            "progress": 30.0,
            "duration": 300.0,
        }
        snap = LxPlayerSnapshot.from_api_dict(data)
        assert snap.is_playing is True
        assert snap.state == "playing"
        assert snap.song_name == "晴天"
        assert snap.singer == "周杰伦"
        assert snap.progress_ms == 30000
        assert snap.duration_ms == 300000

    def test_empty_data_falls_back_to_prior(self):
        prior = LxPlayerSnapshot(song_name="保留", progress_ms=5000)
        snap = LxPlayerSnapshot.from_api_dict({}, prior=prior)
        assert snap.song_name == "保留"
        assert snap.progress_ms == 5000

    def test_partial_data(self):
        prior = LxPlayerSnapshot(singer="林俊杰")
        data = {"name": "不为谁而作的歌"}
        snap = LxPlayerSnapshot.from_api_dict(data, prior=prior)
        assert snap.song_name == "不为谁而作的歌"
        # singer should fall back to prior
        assert snap.singer == "林俊杰"

    def test_progress_zero_handled(self):
        data = {"status": "paused", "progress": 0.0}
        snap = LxPlayerSnapshot.from_api_dict(data)
        assert snap.progress_ms == 0
        assert snap.state == "paused"
