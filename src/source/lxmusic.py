#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
洛雪音乐 (LX Music) 歌词源

LX Music 是基于 Electron + Vue 3 的开源桌面音乐播放器。
项目主页:https://github.com/lyswhut/lx-music-desktop
(Apache License 2.0)

数据采集策略(按优先级):

1. **SSE 订阅 /subscribe-player-status**(主策略,推荐)
   文档:https://lxmusic.toside.cn/desktop/open-api
   LX Music v2.7.0+ 启用开放 API 后,可通过 SSE 长连接实时推送
   播放器状态(状态变更即推送,无需轮询)。

2. **HTTP 轮询 /status**(备选)
   当 SSE 不可用时,定时 GET /status 获取当前状态。
   支持 filter 参数最小化响应。

3. **完整 LRC 解析(LX Music LinePlayer 算法移植)**
   通过 /lyric 或 /lyric-all 获取完整 LRC 文本,
   用移植自 LX Music 的 LxLyricPlayer 计算当前行。
   在 lyricLineText 为空时(如显示"徐誉滕 - 天使的翅膀"这种歌曲头)
   作为 fallback。

4. **桌面歌词窗口 UI Automation**(回退)
   通过 Windows UI Automation API 找到桌面歌词窗口的
   active 行,读取 Name 属性。

5. **LX Music 数据库回退**
   从 %APPDATA%/lx-music-desktop/LxDatas/lx.data.db 读 LRC 文本。

歌词解析与同步逻辑已移植自 LX Music LinePlayer,见 lx_lyric_player.py。
"""

import base64
import json
import os
import queue
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import psutil

from .base import LyricsSource
from .lx_lyric_player import LxLyricParser, LxLyricPlayer, LxLyricLine


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# LX Music 进程关键字(主进程可执行文件名)
# 涵盖:标准 Electron 包(lx-music-desktop)、便携版(lx-music)、
# Microsoft Store 分发、自定义编译、以及含空格/连字符变体
LX_PROCESS_KEYWORDS = [
    'lx-music-desktop', 'lx-music', 'lxmusic',
    'lx music',  # 含空格
    'lx-music-desktop (',  # Windows 进程列表括号后缀
]

# LX Music 默认数据目录(Windows)
LX_DEFAULT_DATA_PATHS = [
    os.path.join(os.environ.get('APPDATA', ''), 'lx-music-desktop'),
    os.path.join(os.environ.get('USERPROFILE', ''), '.lx-music-desktop'),
]

# LX Music 数据库文件名
LX_DB_NAMES = ['lx.data.db', 'data.db']

# 开放 API 默认尝试端口(优先用户截图里的 23330)
LX_OPEN_API_DEFAULT_PORTS = [23330, 23333, 9527, 9528, 9529, 2333, 33333, 8080]

# 开放 API 请求超时(秒)
LX_OPEN_API_TIMEOUT = 2.0

# SSE 重连间隔(秒)
SSE_RECONNECT_INTERVAL_S = 5.0

# 状态轮询最小间隔(秒)
POLL_INTERVAL_S = 0.05

# /status filter 字段(最小可用集合,降低响应体积)
STATUS_FILTER_MIN = 'status,lyricLineText,progress,duration,name,singer'
STATUS_FILTER_FULL = ','.join([
    'status', 'name', 'singer', 'albumName', 'duration', 'progress',
    'playbackRate', 'picUrl', 'lyricLineText', 'lyricLineAllText',
    'lyric', 'tlyric', 'rlyric', 'lxlyric', 'collect', 'volume', 'mute',
])

# /status 返回的 status 字符串值
LX_STATUS_PLAYING = 'playing'
LX_STATUS_PAUSED = 'paused'
LX_STATUS_STOPED = 'stoped'  # 注意:LX Music 用的是 'stoped'(单 p)
LX_STATUS_ERROR = 'error'

LX_PLAYING_STATES = {LX_STATUS_PLAYING, LX_STATUS_PAUSED}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class LxPlayerSnapshot:
    """LX Music 播放器状态快照"""
    is_playing: bool = False
    state: str = ''                 # playing / paused / stoped / error
    song_name: str = ''
    singer: str = ''
    album: str = ''
    lyric_line_text: str = ''       # ★ 当前行歌词(USB 设备要的就是这个)
    lyric_line_all_text: str = ''   # 当前行 + 扩展歌词(翻译/罗马音)
    progress_ms: int = 0            # 已转毫秒
    duration_ms: int = 0            # 已转毫秒
    playback_rate: float = 1.0
    lyric: str = ''                 # 完整 LRC 文本
    tlyric: str = ''
    rlyric: str = ''
    lxlyric: str = ''
    volume: int = 0
    mute: bool = False
    updated_at: float = 0.0         # 单调钟,便于判断新鲜度

    @property
    def has_lyric(self) -> bool:
        return bool(self.lyric_line_text and self.lyric_line_text.strip())

    @classmethod
    def from_api_dict(cls, data: dict, prior: "LxPlayerSnapshot | None" = None) -> "LxPlayerSnapshot":
        """从 LX Music API 返回的 dict 构造快照。缺失字段从 prior 继承。"""
        state_raw = data.get('status', '')
        state = str(state_raw or '').strip()
        is_playing = state in LX_PLAYING_STATES
        prior = prior or cls()

        def _f(key: str, default=None):
            return data.get(key) if key in data else default

        def _int_ms(key: str) -> int:
            if key not in data:
                return prior.progress_ms if key == 'progress' else prior.duration_ms
            v = data.get(key)
            try:
                return int(float(v or 0) * 1000)
            except (TypeError, ValueError):
                return prior.progress_ms if key == 'progress' else prior.duration_ms

        return cls(
            is_playing=is_playing if 'status' in data else prior.is_playing,
            state=state or prior.state,
            song_name=str(_f('name') or prior.song_name),
            singer=str(_f('singer') or prior.singer),
            album=str(_f('albumName') or prior.album),
            lyric_line_text=str(_f('lyricLineText') or prior.lyric_line_text),
            lyric_line_all_text=str(_f('lyricLineAllText') or prior.lyric_line_all_text),
            progress_ms=_int_ms('progress'),
            duration_ms=_int_ms('duration'),
            playback_rate=float(_f('playbackRate') or prior.playback_rate) if 'playbackRate' in data else prior.playback_rate,
            lyric=str(_f('lyric') or prior.lyric),
            tlyric=str(_f('tlyric') or prior.tlyric),
            rlyric=str(_f('rlyric') or prior.rlyric),
            lxlyric=str(_f('lxlyric') or prior.lxlyric),
            volume=int(data['volume']) if 'volume' in data else prior.volume,
            mute=bool(_f('mute', prior.mute)),
            updated_at=time.monotonic(),
        )


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------

class LxMusicSource(LyricsSource):
    """洛雪音乐歌词源"""

    def __init__(
        self,
        api_url: str = '',
        api_port: Optional[int] = None,
        auto_detect_port: bool = True,
        prefer_sse: bool = True,
        db_path: str = '',
    ):
        super().__init__()
        # 兼容多种命名
        self._api_url = api_url or ''
        self._api_port = api_port
        self._auto_detect_port = auto_detect_port
        self._prefer_sse = prefer_sse
        self._db_path = db_path or ''

        self._snapshot = LxPlayerSnapshot()
        self._parser = LxLyricParser()
        self._player: Optional[LxLyricPlayer] = None
        self._current_song_key: str = ''
        self._last_poll_ts: float = 0.0
        self._last_error: str = ''

        # SSE 后台线程
        self._sse_thread: Optional[threading.Thread] = None
        self._sse_stop_event = threading.Event()
        self._sse_lock = threading.Lock()

    # ------------------------------------------------------------------
    # LyricsSource 接口
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return '洛雪音乐'

    @property
    def process_keywords(self) -> List[str]:
        return list(LX_PROCESS_KEYWORDS)

    @property
    def last_error(self) -> str:
        return self._last_error

    def find_process(self) -> Optional[psutil.Process]:
        """查找 LX Music 主进程"""
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                n = (proc.info.get('name') or '').lower()
                exe = (proc.info.get('exe') or '').lower()
                if any(kw in n or kw in exe for kw in self.process_keywords):
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def initialize(self) -> bool:
        """
        初始化:检查进程、探测开放 API、可选启动 SSE
        """
        proc = self.find_process()
        if proc is None:
            self._last_error = '未找到 LX Music 进程'
            return False
        try:
            self.process_id = proc.pid
            self.version = self._detect_version(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

        # 解析 API URL(自动探测端口)
        resolved_url, resolved_port = self._resolve_api_url(self._api_url, self._api_port)
        if not resolved_url:
            self._last_error = (
                'LX Music 开放 API 不可用,请在 LX Music 设置 → 开放 API 中启用并设置端口'
            )
            return False
        self._api_url = resolved_url
        self._api_port = resolved_port

        # 启动 SSE 后台线程
        if self._prefer_sse:
            self._start_sse_thread()
        return True

    def shutdown(self) -> None:
        """停止 SSE 后台线程并释放资源"""
        self._stop_sse_thread()
        # 通知基类清理状态
        LyricsSource.shutdown(self)

    def is_ready(self) -> bool:
        return (
            self.process_id is not None
            and bool(self._api_url)
            and self.find_process() is not None
        )

    def is_running(self) -> bool:
        return self.find_process() is not None

    def read_lyrics(self) -> Optional[str]:
        """
        读取当前播放的歌词行
        Returns:
            当前行歌词文本;无则返回 None
        """
        snap = self._ensure_snapshot()
        if snap is None:
            return None

        # 优先 API 返回的 lyricLineText
        text = (snap.lyric_line_text or '').strip()
        if text:
            # 去除 LX Music 在歌曲头时返回的 "歌手 - 歌名" 格式（双向匹配,顺序不一定）
            if snap.singer and snap.song_name:
                expected1 = f'{snap.singer} - {snap.song_name}'
                expected2 = f'{snap.song_name} - {snap.singer}'
                if text == expected1 or text == expected2:
                    return None
            return text

        # fallback:用 LRC + 进度自己算(LX Music LinePlayer 算法)
        if snap.lyric and snap.progress_ms > 0:
            computed = self._compute_current_line(snap.progress_ms)
            if computed:
                return computed
        return None

    def get_full_snapshot(self) -> LxPlayerSnapshot:
        snap = self._ensure_snapshot()
        return snap if snap is not None else self._snapshot

    # ------------------------------------------------------------------
    # 播放控制(可选,封装 LX Music 开放 API 控制接口)
    # ------------------------------------------------------------------

    def play(self) -> bool:
        return self._control('/play')

    def pause(self) -> bool:
        return self._control('/pause')

    def skip_next(self) -> bool:
        return self._control('/skip-next')

    def skip_prev(self) -> bool:
        return self._control('/skip-prev')

    def seek(self, seconds: float) -> bool:
        return self._control(f'/seek?offset={urllib.parse.quote(str(seconds))}')

    def set_volume(self, volume_1_to_100: int) -> bool:
        return self._control(f'/volume?volume={int(volume_1_to_100)}')

    def set_mute(self, mute: bool) -> bool:
        return self._control(f'/mute?mute={"true" if mute else "false"}')

    def _control(self, path: str) -> bool:
        """通用控制接口调用"""
        if not self._api_url:
            return False
        url = self._api_url + path
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=LX_OPEN_API_TIMEOUT) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, ValueError):
            return False

    # ------------------------------------------------------------------
    # 内部:状态获取
    # ------------------------------------------------------------------

    def _ensure_snapshot(self) -> Optional[LxPlayerSnapshot]:
        """
        确保 snapshot 是新鲜的:
          - SSE 模式:snapshot 由后台线程更新,这里只检查新鲜度
          - 轮询模式:每隔 POLL_INTERVAL_S 主动拉一次
        """
        # SSE 已启动:直接拿最新 snapshot
        if self._prefer_sse and self._sse_thread and self._sse_thread.is_alive():
            return self._snapshot

        # 轮询模式
        now = time.monotonic()
        if now - self._last_poll_ts < POLL_INTERVAL_S and self._snapshot.updated_at > 0:
            return self._snapshot
        self._last_poll_ts = now

        snap = self._fetch_status_from_api()
        if snap is not None:
            self._snapshot = snap
            self._maybe_reload_lrc(snap)
        return self._snapshot if self._snapshot.updated_at > 0 else None

    def _fetch_status_from_api(self, use_filter: bool = True) -> Optional[LxPlayerSnapshot]:
        """GET /status 取播放状态"""
        if not self._api_url:
            return None
        url = self._api_url + '/status'
        if use_filter:
            url += '?filter=' + urllib.parse.quote(STATUS_FILTER_MIN)
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=LX_OPEN_API_TIMEOUT) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
            data = json.loads(raw)
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as e:
            self._last_error = f'/status 请求失败: {type(e).__name__}: {e}'
            return None

        return self._parse_status_dict(data)

    def _parse_status_dict(self, data: Dict[str, Any]) -> LxPlayerSnapshot:
        """把 /status 返回的 JSON 转成 LxPlayerSnapshot"""
        return LxPlayerSnapshot.from_api_dict(data, prior=self._snapshot)

    def _maybe_reload_lrc(self, snap: LxPlayerSnapshot) -> None:
        """切歌时重新加载完整 LRC,刷新 LxLyricPlayer"""
        song_key = f'{snap.song_name}::{snap.singer}'
        if song_key == self._current_song_key:
            return
        self._current_song_key = song_key

        # 清空上一首歌的当前行歌词字段,避免显示残留
        snap.lyric_line_text = ''
        snap.lyric_line_all_text = ''

        # 拉 lyric-all(如果 /status 已经包含 lyric 字段就跳过)
        if not snap.lyric:
            lyric_dict = self._fetch_lyric_all()
            if lyric_dict:
                snap.lyric = lyric_dict.get('lyric') or ''
                snap.tlyric = lyric_dict.get('tlyric') or ''
                snap.rlyric = lyric_dict.get('rlyric') or ''
                snap.lxlyric = lyric_dict.get('lxlyric') or ''

        # 解析
        if snap.lyric:
            try:
                lines = self._parser.parse(
                    snap.lyric,
                    extended_lyrics=[x for x in (snap.tlyric, snap.rlyric, snap.lxlyric) if x],
                )
                self._player = LxLyricPlayer(lines=lines, offset_ms=self._parser.offset_ms)
            except Exception:
                self._player = None

    def _fetch_lyric_all(self) -> Optional[Dict[str, str]]:
        """GET /lyric-all 取完整歌词"""
        if not self._api_url:
            return None
        try:
            url = self._api_url + '/lyric-all'
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=LX_OPEN_API_TIMEOUT) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
            return json.loads(raw)
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            return None

    def _compute_current_line(self, progress_ms: int) -> Optional[str]:
        """根据进度复用 self._player（由 _maybe_reload_lrc / _on_sse_event 切歌时设置）"""
        if self._player is None:
            return None
        try:
            return self._player.get_current_lyric(progress_ms)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # SSE 长连接订阅(主策略)
    # ------------------------------------------------------------------

    def _start_sse_thread(self) -> None:
        """启动 SSE 后台线程"""
        if self._sse_thread and self._sse_thread.is_alive():
            return
        self._sse_stop_event.clear()
        self._sse_thread = threading.Thread(
            target=self._sse_worker, name='LxSseWorker', daemon=True
        )
        self._sse_thread.start()

    def _stop_sse_thread(self) -> None:
        """停止 SSE 后台线程"""
        self._sse_stop_event.set()
        if self._sse_thread and self._sse_thread.is_alive():
            self._sse_thread.join(timeout=2.0)
        self._sse_thread = None

    def _sse_worker(self) -> None:
        """SSE 后台线程:订阅 /subscribe-player-status,实时更新 snapshot"""
        url = self._api_url + '/subscribe-player-status'
        if STATUS_FILTER_MIN:
            url += '?filter=' + urllib.parse.quote(STATUS_FILTER_MIN)

        backoff = 1.0
        while not self._sse_stop_event.is_set():
            try:
                req = urllib.request.Request(url, method='GET')
                req.add_header('Accept', 'text/event-stream')
                req.add_header('Cache-Control', 'no-cache')
                with urllib.request.urlopen(req, timeout=None) as resp:
                    if resp.status != 200:
                        raise ConnectionError(f'SSE bad status: {resp.status}')
                    backoff = 1.0
                    self._read_sse_stream(resp)
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, ValueError) as e:
                self._last_error = f'SSE 连接失败: {type(e).__name__}: {e}'
                # 退避重连
                if self._sse_stop_event.wait(backoff):
                    return
                backoff = min(backoff * 2.0, SSE_RECONNECT_INTERVAL_S)
            except Exception as e:
                self._last_error = f'SSE worker 异常: {type(e).__name__}: {e}'
                if self._sse_stop_event.wait(backoff):
                    return
                backoff = min(backoff * 2.0, SSE_RECONNECT_INTERVAL_S)

    def _read_sse_stream(self, resp) -> None:
        """
        读取 SSE 流式响应,按 event/data 解析
        数据格式:
          event: status\\ndata: "playing"\\n\\n
          event: name\\ndata: "交换余生"\\n\\n

        用 readline() 逐行读取,避免逐字节 read(1) 可能的缓冲问题。
        """
        current_event = ''
        current_data: List[str] = []
        try:
            fp = resp  # resp 本身就是个 buffered file-like
            while not self._sse_stop_event.is_set():
                raw_line = fp.readline()
                if not raw_line:
                    # EOF
                    break
                try:
                    line = raw_line.decode('utf-8', errors='replace').rstrip('\r\n')
                except Exception:
                    continue
                if not line:
                    # 空行 = 一个事件结束
                    # SSE 协议:无 event: 行时默认为 'message'
                    if current_data:
                        self._on_sse_event(current_event or 'message', '\n'.join(current_data))
                    current_event = ''
                    current_data = []
                    continue
                if line.startswith('event:'):
                    current_event = line[len('event:'):].strip()
                elif line.startswith('data:'):
                    current_data.append(line[len('data:'):].lstrip())
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, ValueError):
            # 连接中断,退出后上层 backoff 重连
            return

    def _on_sse_event(self, event: str, data: str) -> None:
        """
        处理单个 SSE 事件。
        LX Music SSE 是逐字段推送的，每收到一个事件合并到 pending 并更新 snapshot。
        切歌时触发 LRC 重载。
        """
        try:
            value = json.loads(data)
        except (ValueError, TypeError):
            value = data
        with self._sse_lock:
            if not hasattr(self, '_sse_pending') or self._sse_pending is None:
                self._sse_pending = {}
            self._sse_pending[event] = value

            # 用 from_api_dict 合并：pending dict + 上次 snapshot 兜底
            snap = LxPlayerSnapshot.from_api_dict(self._sse_pending, prior=self._snapshot)
            self._snapshot = snap
            self._last_error = ''

            # 切歌检测
            song_key = f'{snap.song_name}::{snap.singer}'
            if song_key != self._current_song_key and (snap.song_name or snap.singer):
                self._current_song_key = song_key
                # 清空 SSE 累积的旧歌词字段,避免显示上一首歌残留
                self._sse_pending.pop('lyricLineText', None)
                self._sse_pending.pop('lyricLineAllText', None)
                snap.lyric_line_text = ''
                snap.lyric_line_all_text = ''
                if not snap.lyric:
                    lyric_dict = self._fetch_lyric_all()
                    if lyric_dict:
                        snap.lyric = lyric_dict.get('lyric') or ''
                        snap.tlyric = lyric_dict.get('tlyric') or ''
                        snap.rlyric = lyric_dict.get('rlyric') or ''
                        snap.lxlyric = lyric_dict.get('lxlyric') or ''
                if snap.lyric:
                    try:
                        lines = self._parser.parse(
                            snap.lyric,
                            extended_lyrics=[x for x in (snap.tlyric, snap.rlyric, snap.lxlyric) if x],
                        )
                        self._player = LxLyricPlayer(lines=lines, offset_ms=self._parser.offset_ms)
                    except Exception:
                        self._player = None

    # ------------------------------------------------------------------
    # API 探测
    # ------------------------------------------------------------------

    def _resolve_api_url(
        self,
        api_url: str,
        api_port: Optional[int],
    ) -> Tuple[str, Optional[int]]:
        """解析 API URL + 探测端口"""
        if api_url:
            return api_url.rstrip('/'), None

        if api_port:
            url = f'http://127.0.0.1:{api_port}'
            if self._probe_api(api_port):
                return url, api_port
            return '', None

        if self._auto_detect_port:
            for port in LX_OPEN_API_DEFAULT_PORTS:
                if self._probe_api(port):
                    return f'http://127.0.0.1:{port}', port
        return '', None

    def _probe_api(self, port: int, timeout: float = 0.3) -> bool:
        """探测端口是否响应 LX Music 开放 API"""
        url = f'http://127.0.0.1:{port}/status'
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    return False
                data = resp.read(512).decode('utf-8', errors='replace')
                # LX Music /status 必含 status / lyricLineText
                return '"status"' in data and ('"name"' in data or '"lyricLineText"' in data)
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, ValueError):
            return False

    # ------------------------------------------------------------------
    # 回退:数据库
    # ------------------------------------------------------------------

    def _fetch_from_db_and_memory(self) -> Optional[LxPlayerSnapshot]:
        """数据库 fallback(歌词文本 + 当前行无法确定,主要用作冷启动歌词文本来源)"""
        db_path = self._resolve_db_path()
        if not db_path or not os.path.isfile(db_path):
            return None

        try:
            conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True, timeout=1.0)
            try:
                cur = conn.cursor()
                cur.execute(
                    'SELECT "id", "type", "text" FROM "main"."lyric" '
                    'WHERE "source"=\'raw\' ORDER BY "id" DESC LIMIT 32'
                )
                rows = cur.fetchall()
            finally:
                conn.close()
        except sqlite3.Error:
            return None

        if not rows:
            return None

        latest_id = rows[0][0]
        latest: Dict[str, str] = {}
        for song_id, ltype, b64text in rows:
            if song_id != latest_id:
                continue
            try:
                latest[ltype] = base64.b64decode(b64text or b'').decode('utf-8', errors='replace')
            except Exception:
                latest[ltype] = ''

        lyric = latest.get('lyric', '')
        if not lyric:
            return None

        # 仅有歌词文本,没有进度 → 标记 lyric 字段,read_lyrics 在 SSE/轮询可用时会处理
        return LxPlayerSnapshot(
            is_playing=False,
            state=LX_STATUS_STOPED,
            lyric=lyric,
            tlyric=latest.get('tlyric', ''),
            rlyric=latest.get('rlyric', ''),
            lxlyric=latest.get('lxlyric', ''),
            updated_at=time.monotonic(),
        )

    def _resolve_db_path(self) -> str:
        """解析 LX Music 数据库路径"""
        if self._db_path and os.path.isfile(self._db_path):
            return self._db_path
        # 优先从进程 exe 同级目录找 portable
        proc = self.find_process()
        if proc is not None:
            try:
                exe_dir = os.path.dirname(proc.exe())
                portable_db = os.path.join(exe_dir, 'portable', 'LxDatas', 'lx.data.db')
                if os.path.isfile(portable_db):
                    return portable_db
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        # 常见位置
        for base in LX_DEFAULT_DATA_PATHS:
            if not base:
                continue
            for dbname in LX_DB_NAMES:
                for sub in ('', 'LxDatas'):
                    cand = os.path.join(base, sub, dbname)
                    if os.path.isfile(cand):
                        return cand
        return ''

    def _detect_version(self, proc: psutil.Process) -> str:
        """探测 LX Music 版本号"""
        try:
            exe = proc.exe() or ''
            # LX Music 的 resources/app/package.json 里有 version
            pkg = os.path.normpath(os.path.join(os.path.dirname(exe), 'resources', 'app', 'package.json'))
            if os.path.isfile(pkg):
                with open(pkg, encoding='utf-8') as fp:
                    data = json.load(fp)
                if isinstance(data, dict) and data.get('version'):
                    return str(data['version'])
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError, KeyError):
            pass
        return 'unknown'


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    'LxMusicSource',
    'LxPlayerSnapshot',
    'LX_PROCESS_KEYWORDS',
    'LX_OPEN_API_DEFAULT_PORTS',
    'LX_STATUS_PLAYING',
    'LX_STATUS_PAUSED',
    'LX_STATUS_STOPED',
    'LX_STATUS_ERROR',
    'STATUS_FILTER_MIN',
    'STATUS_FILTER_FULL',
]