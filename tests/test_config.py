"""tests.test_config — 全局 Config 单例、reset 钩子与死配置清理验证"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_config, _reset_config_instance


class TestConfigSingleton:
    def test_singleton_returns_same_instance(self):
        _reset_config_instance()
        a = get_config()
        b = get_config()
        assert a is b

    def test_reset_creates_new_instance(self):
        _reset_config_instance()
        a = get_config()
        _reset_config_instance()
        b = get_config()
        assert a is not b

    def test_reset_is_idempotent(self):
        # 多次 reset 不会抛异常
        _reset_config_instance()
        _reset_config_instance()
        _reset_config_instance()
        cfg = get_config()
        assert cfg is not None


class TestDeadConfigRemoved:
    """P2-11: scroll_speed / display_duration / scroll_duration 已被清理"""

    def test_scroll_speed_removed(self):
        _reset_config_instance()
        cfg = get_config()
        assert cfg.get('lyrics', 'scroll_speed', default=None) is None

    def test_display_duration_removed(self):
        _reset_config_instance()
        cfg = get_config()
        assert cfg.get('lyrics', 'display_duration', default=None) is None

    def test_scroll_duration_removed(self):
        _reset_config_instance()
        cfg = get_config()
        assert cfg.get('lyrics', 'scroll_duration', default=None) is None

    def test_active_keys_preserved(self):
        _reset_config_instance()
        cfg = get_config()
        # 确认没误删有效配置
        assert cfg.get('source', 'type') == 'lxmusic'
        assert cfg.get('hid', 'color') == 'white'
        assert cfg.get('lyrics', 'max_chars_per_line') == 20
        assert cfg.get('lyrics', 'show_progress') is True