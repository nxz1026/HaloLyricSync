# HALO PIXELBAR 歌词同步器

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue?logo=python)]()
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey?logo=windows)]()
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE.txt)

通过 **LX Music 开放 API** 实时读取歌词，同步显示到 **HALO PIXELBAR** 音箱。

---

## 特性

| 特性 | 说明 |
|------|------|
| LX Music 集成 | SSE 长连接 + HTTP 轮询 + SQLite 回退，四层策略保证歌词读取 |
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
HaloPixelBar.exe --help              # 查看帮助
HaloPixelBar.exe --send "文本"      # 显示自定义文本
HaloPixelBar.exe --status            # 检查 LX Music 连接状态
HaloPixelBar.exe --list-devices      # 列出所有 HID 设备
```

## 架构

```
LX Music 开放 API
    │ SSE / HTTP
    ▼
LxMusicSource ──→ 获取播放状态 + 歌词
    │
    ▼
hid_comm.py   ──→ 64 字节 HID 包写入 USB
    │
    ▼
HALO PIXELBAR ──→ 显示歌词
```

### 项目结构

```
HaloLyricSync/
├── src/
│   ├── main.py               # 主程序
│   ├── config.py              # JSON 配置管理
│   ├── hid_comm.py            # USB HID 通信
│   ├── hid_packet_builder.py  # HID 协议包构建
│   ├── lyrics_parser.py       # LRC 歌词解析器
│   └── source/
│       ├── base.py            # 歌词源抽象基类
│       ├── lxmusic.py         # LX Music 歌词源（主）
│       ├── factory.py         # 源工厂函数
│       └── lx_lyric_player.py # LinePlayer 算法移植
├── requirements.txt
├── run.bat
├── HaloPixelBar_Windows.zip  # 预编译 exe 包
└── dist/
    └── HaloPixelBar.exe      # 单文件 exe (PyInstaller)
```

## 配置

`%USERPROFILE%\.halo_lrc_sync\config.json`

```json
{
  "source": {
    "type": "lxmusic",
    "lxmusic": {
      "api_port": 23330,
      "prefer_sse": true
    }
  },
  "lyrics": {
    "max_chars_per_line": 20
  },
  "hid": {
    "auto_detect": true,
    "device_keywords": ["halo", "pixel"]
  }
}
```

## HID 协议包

| 包类型 | 说明 |
|--------|------|
| 文本包 | 64 字节裸包，显示最长 20 字符 |
| 布局包 | 设置对齐与滚动方式 |
| UI 模式包 | 切换设备显示主题 |

> 协议与 [HaloPixelToolBox](https://github.com/XFEstudio/HaloPixelToolBox) 兼容。

## FAQ

**找不到设备？** → 确认 USB 连接 → 管理员运行 → `--list-devices`

**没歌词？** → 确认 LX Music 开放 API 已启用 → 确认正在播放 → `--status`

**乱码？** → 确认歌曲编码为 UTF-8

## 依赖

- [`psutil`](https://github.com/giampaolo/psutil) — 进程管理
- [`hidapi`](https://github.com/libusb/hidapi) — HID 通信（编译扩展，静态链接）

## 参考

- [HaloPixelToolBox](https://github.com/XFEstudio/HaloPixelToolBox) — C# HID 协议实现
- [lx-music-desktop](https://github.com/lyswhut/lx-music-desktop) — 洛雪音乐播放器
