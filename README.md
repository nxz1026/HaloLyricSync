# HALO PIXELBAR 歌词同步器

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue?logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey?logo=windows)](https://github.com/nxz1026/HaloLyricSync)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE.txt)

通过 **LX Music (洛雪音乐) 开放 API** 实时读取歌词，同步显示到 **HALO PIXELBAR** 音箱。

> 核心技术：`SSE 长连接` + `HTTP 轮询` + `HID 协议`，与 [HaloPixelToolBox](https://github.com/XFEstudio/HaloPixelToolBox) HID 协议兼容。

---

## 功能特点

| 特性 | 说明 |
|------|------|
| **LX Music 集成** | 通过开放 API 读取歌词，SSE 长连接实时推送 |
| **多策略回退** | SSE -> HTTP 轮询 -> LRC 解析 -> 数据库读取 |
| **HID 协议** | 与官方工具相同的 64 字节 HID 协议通信 |
| **实时同步** | 50ms 刷新间隔，歌词无延迟 |
| **多种布局** | 左对齐 / 居中 / 右对齐 / 拉伸 / 左滚动 / 右滚动 |
| **UI 模式** | 时钟 / 游戏 / 工作 / 阅读 / 猫咪 / 狗狗 / 表情 / 赛博 / 波浪 |
| **自定义文本** | `--send TEXT` 发送任意文本到设备 |
| **播放控制** | 通过 LX Music API 控制播放/暂停/切歌/音量 |

---

## 系统要求

- **操作系统**: Windows 10 / 11（管理员权限）
- **Python**: 3.8+
- **LX Music**: v2.7.0+（需开启开放 API）
- **硬件**: HALO PIXELBAR 音箱 + USB 数据线

---

## 快速开始

```bash
pip install -r requirements.txt
python src/main.py
```

### 前置条件

1. 安装并打开 **LX Music (洛雪音乐)**
2. LX Music 设置 -> 开放 API -> **启用开放 API**（默认端口 23330）
3. 播放任意歌曲
4. **以管理员权限运行**（HID 通信需要）

### 命令行选项

```bash
python src/main.py                  # 启动歌词同步
python src/main.py --status         # 检查 LX Music 状态
python src/main.py --list-devices   # 列出 HID 设备
python src/main.py --send "文本"    # 发送自定义文本到设备
python src/main.py --port PATH      # 指定设备路径
python src/main.py --config PATH    # 指定配置文件
```

---

## 技术架构

### 歌词源

```
LX Music (洛雪音乐)
    |
    |--- SSE /subscribe-player-status (主策略, 实时推送)
    |--- HTTP GET /status            (备选, 轮询)
    |--- GET /lyric-all              (LRC 解析回退)
    |--- SQLite 数据库               (冷启动回退)
    |
    v
LxMusicSource.read_lyrics()  -->  HID 协议打包  -->  HALO PIXELBAR
```

### 数据流

```
LX Music 开放 API
    | SSE / HTTP
    v
LxMusicSource ---- 获取播放状态 + 歌词文本
    |
    v
main.py _sync_loop ---- 50ms 轮询, 歌词变化时推送
    |
    v
hid_comm.py ---- 通过 hidapi 写入 USB HID 设备
    |
    v
HALO PIXELBAR ---- 显示歌词
```

### 项目结构

```
HaloLyricSync/
├── src/
│   ├── main.py                  # 主程序 / LyricSynchronizer
│   ├── config.py                # JSON 配置管理
│   ├── memory_reader.py         # 旧 API 兼容层
│   ├── hid_comm.py              # USB HID 通信模块
│   ├── hid_packet_builder.py    # HID 协议包构建器
│   ├── lyrics_parser.py         # LRC 歌词格式解析器
│   └── source/
│       ├── __init__.py          # 模块导出
│       ├── base.py              # LyricsSource 抽象基类
│       ├── lxmusic.py           # LX Music 歌词源(SSE+HTTP+数据库)
│       ├── cloudmusic.py        # 网易云音乐内存读取源(旧方案)
│       ├── factory.py           # create_source 工厂
│       ├── lx_lyric_player.py   # LX Music LinePlayer 算法移植
│       └── memory.py            # Windows 进程内存读取工具
├── requirements.txt
├── run.bat
└── README.md
```

---

## HID 协议

### 数据包类型

| 类型 | 说明 |
|------|------|
| 文本包 | 显示文本内容（最长 20 字符） |
| 布局包 | 设置文本对齐与滚动方式 |
| UI 模式包 | 切换音箱的 UI 显示主题 |

### 支持的布局

| 布局 | 说明 |
|------|------|
| LEFT | 左对齐 |
| CENTER | 居中 |
| RIGHT | 右对齐 |
| STRETCH | 拉伸填充 |
| SCROLL_LEFT_TO_RIGHT | 从左向右滚动 |
| SCROLL_RIGHT_TO_LEFT | 从右向左滚动 |

### 支持的 UI 模式

时钟 / 游戏 / 工作 / 阅读 / 猫咪 / 狗狗 / 表情 / 赛博 / 波浪

---

## 配置

`%USERPROFILE%\.halo_lrc_sync\config.json`

```json
{
  "source": {
    "type": "lxmusic",
    "lxmusic": {
      "api_url": "",
      "api_port": 23330,
      "auto_detect_port": true,
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

---

## 常见问题

**找不到 HID 设备？**
1. 确认音箱已通过 USB 连接
2. **以管理员身份运行** 程序
3. 使用 `--list-devices` 检查

**歌词读取不到？**
1. 确认 LX Music 已开启开放 API（设置 -> 开放 API）
2. 确认有歌曲正在播放
3. 使用 `--status` 检查连接状态

**LX Music 开放 API 未启用？**
1. 打开 LX Music 设置
2. 找到 "开放 API" 选项并启用
3. 记下端口号（默认 23330）

---

## 依赖

- [`psutil`](https://github.com/giampaolo/psutil) — 进程查找与管理
- [`hid`](https://github.com/libusb/hidapi) — HID 设备通信

---

## 参考项目

- [HaloPixelToolBox](https://github.com/XFEstudio/HaloPixelToolBox) — C# HID 协议参考实现
- [lx-music-desktop](https://github.com/lyswhut/lx-music-desktop) — 洛雪音乐播放器 (Apache 2.0)

## Author

**nxz1026** - [GitHub](https://github.com/nxz1026)
