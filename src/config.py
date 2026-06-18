#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
"""

import json
import os
from pathlib import Path


class Config:
    """配置管理器"""
    
    DEFAULT_CONFIG = {
        "lyrics": {
            "scroll_speed": 1,
            "display_duration": 3,
            "scroll_duration": 0.5,
            "sync_offset_ms": 0,
            "max_chars_per_line": 20
        },
        "source": {
            "type": "lxmusic",
            "lxmusic": {
                "api_url": "",
                "api_port": 23330,
                "auto_detect_port": True,
                "prefer_sse": True,
                "http_api_token": ""
            },
            "cloudmusic": {
                "test_absolute_address": None
            }
        },
        "hid": {
            "auto_detect": True,
            "device_keywords": ["halo", "pixel", "花再", "pixelbar"]
        },
        "app": {
            "log_level": "INFO",
            "cache_dir": "cache",
            "auto_start": False
        }
    }
    
    def __init__(self, config_path: str = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = Path.home() / ".halo_lrc_sync" / "config.json"
        
        self.config = self.DEFAULT_CONFIG.copy()
        self.load()
    
    def load(self) -> None:
        """加载配置文件"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    self._merge_config(self.config, user_config)
                print(f"[Config] 配置加载成功: {self.config_path}")
            except Exception as e:
                print(f"[Config] 配置加载失败: {e}, 使用默认配置")
        else:
            print(f"[Config] 配置文件不存在, 将创建默认配置")
            self.save()
    
    def save(self) -> None:
        """保存配置文件"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            print(f"[Config] 配置已保存: {self.config_path}")
        except Exception as e:
            print(f"[Config] 配置保存失败: {e}")
    
    def _merge_config(self, default: dict, user: dict) -> None:
        """
        合并用户配置和默认配置
        
        Args:
            default: 默认配置
            user: 用户配置
        """
        for key, value in user.items():
            if key in default:
                if isinstance(default[key], dict) and isinstance(value, dict):
                    self._merge_config(default[key], value)
                else:
                    default[key] = value
    
    def get(self, *keys, default=None):
        """
        获取配置项
        
        Args:
            *keys: 配置键路径，例如 'netease', 'host'
            default: 默认值
            
        Returns:
            配置值
        """
        result = self.config
        for key in keys:
            if isinstance(result, dict) and key in result:
                result = result[key]
            else:
                return default
        return result
    
    def set(self, *keys, value) -> None:
        """
        设置配置项
        
        Args:
            *keys: 配置键路径
            value: 要设置的值
        """
        if not keys:
            return
            
        current = self.config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value


# 全局配置实例
_config_instance = None

def get_config(config_path: str = None) -> Config:
    """获取全局配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance
