# HALO PIXELBAR 歌词同步器

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue?logo=python)]()
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey?logo=windows)]()
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE.txt)
[![Tests](https://img.shields.io/badge/Tests-28_✔️-success.svg)](tests/)

通过 **LX Music 开放 API** 实时读取歌词，同步显示到 **HALO PIXELBAR** 音箱。

---

## 特性

| 特性 | 说明 |
|------|------|
| LX Music 集成 | SSE 长连接 + HTTP 轮询 + SQLite 回退，四层策略保证歌词读取 |
| **LRC 时间同步** | ✅ 完整 LRC 解析 + `get_lyric_at_time()` 二分查找按进度翻行 |
| **切歌信息过渡** | ✅ 切歌时显示 "🎵 晴天 - 周杰伦" 3 秒后恢复歌词 |
| **行号/进度指示** | ✅ 歌词末尾显示 `[3/12]` 当前行/总数 |
| **歌词颜色** | ✅ 7 色可选（白/红/绿/蓝/黄/青/品红） |
| **后台运行** | ✅ `--minimized` 隐藏控制台窗口 |
| 多种布局 | 左对齐 / 居中 / 右对齐 / 拉伸 / 左右滚动 |
| UI 模式 | 时钟 / 游戏 / 工作 / 阅读 / 猫咪 / 狗狗 / 赛博 / 波浪 |
| 自定义文本 | `--send TEXT` 发送任意文字到设备 |
| 播放控制 | LX Music API 控制播放 / 暂停 / 切歌 / 音量 |

## 快速开始

### 方法一：预编译 exe（推荐）

1. **下载** — 从 [Releases](https://github.com/nxz1026/HaloLyricSync/releases) 下载 `HaloPixelBar_Windows.zip`
2. **解压** — 右键 → 解压到当前文件夹
3. **运行** — 右键 `HaloPixelBar.exe` → **以管理员身份运行**

### 方法二：源码运行

需要 Python 3.8+。

```bash
pip install -r requirements.txt
python src/main.py
```

### 前置条件

1. LX Music **设置 → 开放 API → 启用**（默认端口 23330）
2. HALO PIXELBAR 通过 USB 连接电脑
3. **以管理员身份运行**（HID 通信需要）

### 命令

```bash
HaloPixelBar.exe --help                  # 查看帮助
HaloPixelBar.exe                         # 启动同步器
HaloPixelBar.exe --minimized             # 后台运行（隐藏窗口）
HaloPixelBar.exe --send "文本"           # 显示自定义文本
HaloPixelBar.exe --color red             # 指定歌词颜色
HaloPixelBar.exe --status                # 检查 LX Music 连接状态
HaloPixelBar.exe --list-devices          # 列出所有 HID 设备
```

## 新增功能

### ④ 切歌信息过渡

切歌时自动显示 **"🎵 歌名 - 歌手"** 停留 3 秒后恢复歌词同步。

配置 `config.json`：
```json
{
  "lyrics": {
    "display_song_info": true,
    "song_info_duration_s": 3
  }
}
```

### ⑤ 行号/进度指示

歌词末尾追加 `[当前行/总行数]`：
```
故事的小黄花[4/12]
```
自动扣减 `max_chars_per_line` 空间。配置 `lyrics.show_progress` 开关。

### ⑥ 后台运行

```bash
HaloPixelBar.exe --minimized
```
隐藏控制台窗口，纯后台运行。通过命令行发送文本或后续 Webhook 控制。

### ⑧ 歌词颜色

```bash
HaloPixelBar.exe --color red       # 命令行指定
# 或配置文件设置
```

| 颜色 | `--color` 值 |
|------|-------------|
| 白色（默认） | `white` |
| 红色 | `red` |
| 绿色 | `green` |
| 蓝色 | `blue` |
| 黄色 | `yellow` |
| 青色 | `cyan` |
| 品红 | `magenta` |

## 架构

```
LX Music 开放 API
    │ SSE / HTTP
    ▼
LxMusicSource ──→ 获取播放状态 + 歌词
    │
    ├─ LRC 解析 → get_lyric_at_time(progress_ms) → 按进度翻行
    │
    ▼
hid_comm.py   ──→ 64 字节 HID 包写入 USB（含颜色字节）
    │
    ▼
HALO PIXELBAR ──→ 显示歌词
```

### 项目结构

```
HaloLyricSync/
├── src/
│   ├── main.py               # 主程序（含同步器/切歌过渡/进度指示）
│   ├── config.py              # JSON 配置管理（深拷贝防共享引用）
│   ├── hid_comm.py            # USB HID 通信（含颜色支持）
│   ├── hid_packet_builder.py  # HID 协议包构建（TextColor 枚举）
│   ├── lyrics_parser.py       # LRC 歌词解析器（二分查找）
│   ├── memory_reader.py       # 内存读取（预留）
│   └── source/
│       ├── base.py            # 歌词源抽象基类
│       ├── lxmusic.py         # LX Music 歌词源（SSE + HTTP + DB 回退）
│       ├── factory.py         # 源工厂函数
│       └── lx_lyric_player.py # LinePlayer 算法移植
├── tests/                     # pytest 测试套件（28 用例）
│   ├── test_lyrics_parser.py  # LRC 解析/二分查找/标签解析
│   ├── test_hid_packet.py     # HID 包构建/校验和/颜色
│   └── test_snapshot.py       # from_api_dict/空数据回退
├── pyproject.toml             # 项目元数据
├── requirements.txt
└── run.bat
```

## 配置

`%USERPROFILE%\.halo_lrc_sync\config.json`

```json
{
  "lyrics": {
    "scroll_speed": 1,
    "display_duration": 3,
    "scroll_duration": 0.5,
    "sync_offset_ms": 0,
    "max_chars_per_line": 20,
    "show_progress": true,
    "display_song_info": true,
    "song_info_duration_s": 3
  },
  "source": {
    "type": "lxmusic",
    "lxmusic": {
      "api_port": 23330,
      "prefer_sse": true
    }
  },
  "hid": {
    "auto_detect": true,
    "device_keywords": ["halo", "pixel", "花再", "pixelbar"],
    "color": "white"
  }
}
```

## HID 协议包

| 包类型 | 说明 |
|--------|------|
| 文本包 | 64 字节裸包，含颜色字节（第5字节），显示最长 20 字符 |
| 布局包 | 设置对齐与滚动方式 |
| UI 模式包 | 切换设备显示主题 |

> 协议与 [HaloPixelToolBox](https://github.com/XFEstudio/HaloPixelToolBox) 兼容。颜色字节：0=白 1=红 2=绿 3=蓝 4=黄 5=青 6=品红

## FAQ

**找不到设备？** → 确认 USB 连接 → 管理员运行 → `--list-devices`

**没歌词？** → 确认 LX Music 开放 API 已启用 → 确认正在播放 → `--status`

**歌词不翻页？** → 确认 LX Music 开放 API 已启用完整状态返回（需 `lyricLineText` + `progress`）

**后台怎么恢复窗口？** → `HaloPixelBar.exe` 再次运行会提示已在运行

**乱码？** → 确认歌曲编码为 UTF-8

## 依赖

- [`psutil`](https://github.com/giampaolo/psutil) — 进程管理
- [`hidapi`](https://github.com/libusb/hidapi) — HID 通信（编译扩展，静态链接）

## 参考

- [HaloPixelToolBox](https://github.com/XFEstudio/HaloPixelToolBox) — C# HID 协议实现
- [lx-music-desktop](https://github.com/lyswhut/lx-music-desktop) — 洛雪音乐播放器
