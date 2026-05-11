#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐API管理器
自动下载、启动和停止 NeteaseCloudMusicApi 服务
"""

import os
import sys
import json
import time
import subprocess
import requests
from pathlib import Path
from urllib.request import urlretrieve
import zipfile
import shutil

try:
    from src.config import get_config
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.config import get_config


class NeteaseApiServer:
    """网易云音乐API服务器管理器"""
    
    GITHUB_REPO = "Binaryify/NeteaseCloudMusicApi"
    RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    API_BASE_URL = "http://localhost:3000"
    
    def __init__(self, config=None):
        """初始化"""
        self.config = config or get_config()
        self.server_process = None
        self.install_dir = Path.home() / ".halo_lrc_sync" / "NeteaseCloudMusicApi"
        
    def is_server_running(self) -> bool:
        """检查服务器是否运行"""
        try:
            response = requests.get(f"{self.API_BASE_URL}/ping", timeout=2)
            return response.status_code == 200
        except Exception:
            return False
    
    def is_installed(self) -> bool:
        """检查是否已安装"""
        return self.install_dir.exists() and (self.install_dir / "node_modules").exists()
    
    def download_and_install(self, force: bool = False) -> bool:
        """
        下载并安装 NeteaseCloudMusicApi
        
        Args:
            force: 是否强制重新安装
            
        Returns:
            安装是否成功
        """
        if self.is_installed() and not force:
            print("[NeteaseApi] NeteaseCloudMusicApi 已安装")
            return True
        
        print("[NeteaseApi] 开始安装 NeteaseCloudMusicApi...")
        
        try:
            # 创建安装目录
            if force and self.install_dir.exists():
                shutil.rmtree(self.install_dir)
            self.install_dir.parent.mkdir(parents=True, exist_ok=True)
            
            # 下载最新版本
            print("[NeteaseApi] 获取最新版本信息...")
            response = requests.get(self.RELEASES_URL, timeout=10)
            if response.status_code != 200:
                print("[NeteaseApi] 获取版本信息失败，尝试使用 master 分支")
                self._install_from_git()
                return True
            
            release_info = response.json()
            version = release_info.get("tag_name", "latest")
            print(f"[NeteaseApi] 最新版本: {version}")
            
            # 查找源码下载链接
            source_url = None
            for asset in release_info.get("assets", []):
                if "source.zip" in asset.get("name", ""):
                    source_url = asset.get("browser_download_url")
                    break
            
            if not source_url:
                # 如果没有预编译版本，使用 git 克隆
                self._install_from_git()
                return True
            
            # 下载源码
            print("[NeteaseApi] 下载源码包...")
            zip_path = self.install_dir.parent / "netease_source.zip"
            urlretrieve(source_url, zip_path)
            
            # 解压
            print("[NeteaseApi] 解压源码...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # 解压到临时目录
                temp_dir = self.install_dir.parent / "temp_extract"
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                zip_ref.extractall(temp_dir)
                
                # 移动内容到安装目录
                extracted_contents = list(temp_dir.iterdir())
                if extracted_contents:
                    first_dir = extracted_contents[0]
                    if first_dir.is_dir() and first_dir.name.startswith("NeteaseCloudMusicApi"):
                        shutil.move(str(first_dir), str(self.install_dir))
                    else:
                        self.install_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(first_dir), str(self.install_dir / "src"))
            
            # 清理临时文件
            shutil.rmtree(temp_dir, ignore_errors=True)
            if zip_path.exists():
                zip_path.unlink()
            
            # 安装依赖
            print("[NeteaseApi] 安装 Node.js 依赖...")
            if not self._install_dependencies():
                return False
            
            print("[NeteaseApi] 安装完成!")
            return True
            
        except Exception as e:
            print(f"[NeteaseApi] 安装失败: {e}")
            return False
    
    def _install_from_git(self) -> bool:
        """从 Git 克隆安装"""
        print("[NeteaseApi] 从 Git 克隆源码...")
        
        try:
            # 检查 git 是否可用
            subprocess.run(["git", "--version"], capture_output=True, check=True)
            
            self.install_dir.mkdir(parents=True, exist_ok=True)
            
            # 克隆仓库
            result = subprocess.run(
                ["git", "clone", "https://github.com/Binaryify/NeteaseCloudMusicApi.git", str(self.install_dir)],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"[NeteaseApi] Git 克隆失败: {result.stderr}")
                return False
            
            # 安装依赖
            return self._install_dependencies()
            
        except Exception as e:
            print(f"[NeteaseApi] Git 克隆失败: {e}")
            return False
    
    def _install_dependencies(self) -> bool:
        """安装 Node.js 依赖"""
        try:
            # 检查 Node.js
            result = subprocess.run(["node", "--version"], capture_output=True, check=True)
            print(f"[NeteaseApi] Node.js 版本: {result.stdout.strip()}")
            
            # 安装依赖
            print("[NeteaseApi] 运行 npm install...")
            result = subprocess.run(
                ["npm", "install"],
                cwd=str(self.install_dir),
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode != 0:
                print(f"[NeteaseApi] npm install 失败: {result.stderr}")
                return False
            
            return True
            
        except subprocess.TimeoutExpired:
            print("[NeteaseApi] npm install 超时")
            return False
        except FileNotFoundError:
            print("[NeteaseApi] 未找到 Node.js 或 npm，请先安装 Node.js")
            print("   下载地址: https://nodejs.org/")
            return False
        except Exception as e:
            print(f"[NeteaseApi] 安装依赖失败: {e}")
            return False
    
    def start(self) -> bool:
        """
        启动 API 服务器
        
        Returns:
            启动是否成功
        """
        if self.is_server_running():
            print("[NeteaseApi] API 服务器已在运行")
            return True
        
        if not self.is_installed():
            print("[NeteaseApi] NeteaseCloudMusicApi 未安装，正在安装...")
            if not self.download_and_install():
                return False
        
        try:
            print("[NeteaseApi] 启动 API 服务器...")
            
            # 在后台启动服务器
            self.server_process = subprocess.Popen(
                ["node", "bin/www"],
                cwd=str(self.install_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 等待服务器启动
            print("[NeteaseApi] 等待服务器启动...")
            for i in range(30):  # 最多等待30秒
                time.sleep(1)
                if self.is_server_running():
                    print("[NeteaseApi] API 服务器启动成功!")
                    return True
                print(f"[NeteaseApi] 等待中... ({i+1}/30)")
            
            print("[NeteaseApi] API 服务器启动超时")
            return False
            
        except Exception as e:
            print(f"[NeteaseApi] 启动服务器失败: {e}")
            return False
    
    def stop(self) -> bool:
        """
        停止 API 服务器
        
        Returns:
            停止是否成功
        """
        if self.server_process:
            print("[NeteaseApi] 停止 API 服务器...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            self.server_process = None
            print("[NeteaseApi] API 服务器已停止")
            return True
        return False
    
    def get_current_song(self) -> dict:
        """
        获取当前播放歌曲（需要配合播放器使用）
        
        Returns:
            当前歌曲信息
        """
        try:
            # 获取播放列表
            response = requests.get(f"{self.API_BASE_URL}/user/playlist", params={"uid": 1}, timeout=5)
            if response.status_code == 200:
                return {"playing": True, "data": response.json()}
        except Exception as e:
            print(f"[NeteaseApi] 获取播放状态失败: {e}")
        return None
    
    def get_lyrics(self, song_id: int) -> dict:
        """
        获取歌词
        
        Args:
            song_id: 歌曲ID
            
        Returns:
            歌词数据
        """
        try:
            response = requests.get(f"{self.API_BASE_URL}/lyric", params={"id": song_id}, timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"[NeteaseApi] 获取歌词失败: {e}")
        return None
    
    def search_song(self, keyword: str, limit: int = 10) -> list:
        """
        搜索歌曲
        
        Args:
            keyword: 搜索关键词
            limit: 结果数量限制
            
        Returns:
            搜索结果列表
        """
        try:
            response = requests.get(
                f"{self.API_BASE_URL}/search",
                params={"keywords": keyword, "limit": limit},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("result", {}).get("songs", [])
        except Exception as e:
            print(f"[NeteaseApi] 搜索失败: {e}")
        return []


# 全局实例
_server_instance = None

def get_api_server() -> NeteaseApiServer:
    """获取 API 服务器实例"""
    global _server_instance
    if _server_instance is None:
        _server_instance = NeteaseApiServer()
    return _server_instance


if __name__ == "__main__":
    # 测试脚本
    print("=" * 60)
    print("NeteaseCloudMusicApi 管理器")
    print("=" * 60)
    
    server = NeteaseApiServer()
    
    import argparse
    parser = argparse.ArgumentParser(description="NeteaseCloudMusicApi 管理器")
    parser.add_argument("--install", action="store_true", help="安装 NeteaseCloudMusicApi")
    parser.add_argument("--start", action="store_true", help="启动 API 服务器")
    parser.add_argument("--stop", action="store_true", help="停止 API 服务器")
    parser.add_argument("--status", action="store_true", help="查看服务器状态")
    parser.add_argument("--force", action="store_true", help="强制重新安装")
    args = parser.parse_args()
    
    if args.status:
        print(f"[状态] 服务器运行中: {server.is_server_running()}")
        print(f"[状态] 已安装: {server.is_installed()}")
    
    if args.install:
        server.download_and_install(force=args.force)
    
    if args.start:
        server.start()
    
    if args.stop:
        server.stop()
    
    if not any([args.install, args.start, args.stop, args.status]):
        parser.print_help()
