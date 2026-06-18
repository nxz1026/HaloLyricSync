# HALO PIXELBAR 歌词同步器

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue?logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey?logo=windows)](https://github.com/nxz1026/HaloLrcSync)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE.txt)

通过**内存读取**方式获取网易云音乐歌词，实时同步显示到 **HALO PIXELBAR** 音箱。

> 核心技术：`ReadProcessMemory` + `HID 协议`，与 [HaloPixelToolBox](https://github.com/XFEstudio/HaloPixelToolBox) 完全一致。

---

## ✨ 功能特点

| 特性 | 说明 |
|------|------|
| **内存读取** | 直接从 `cloudmusic.exe` 进程内存中读取歌词，无需任何 API |
| **HID 协议** | 使用与官方工具相同的 HID 协议通信，64 字节数据包 |
| **实时同步** | 50 ms 级刷新间隔，歌词几乎无延迟 |
| **多种布局** | 左对齐 / 居中 / 右对齐 / 拉伸 / 左滚动 / 右滚动 |
| **UI 模式** | 时钟 / 游戏 / 工作 / 阅读 / 猫咪 / 狗狗 / 表情 / 赛博 / 波浪 |
| **智能检测** | 自动检测网易云音乐进程，30 秒无歌词自动切换时钟模式 |

## 📋 系统要求

- **操作系统**: Windows 10 / 11（管理员权限）
- **Python**: 3.8 或更高版本
- **网易云音乐**: 3.1.25 ~ 3.1.32 版本
- **硬件**: HALO PIXELBAR 音箱 + USB 数据线

> ⚠️ **必须以管理员身份运行**，否则 HID 通信和进程内存读取会失败。

---

## 🚀 快速开始

### 一键运行

```bash
git clone https://github.com/nxz1026/HaloLrcSync.git
cd HaloLrcSync
run.bat
```

### 手动运行

```bash
pip install -r requirements.txt
python src/main.py
```

---

## 📖 使用说明

### 前置条件

1. **以管理员身份运行** 命令提示符 / PowerShell
2. 打开网易云音乐，播放任意歌曲
3. **开启桌面歌词功能**（必须！歌词数据才会加载到内存）
4. 通过 USB 连接 HALO PIXELBAR 音箱

### 命令行选项

```bash
python src/main.py                  # 启动歌词同步
python src/main.py --status         # 检查网易云音乐状态
python src/main.py --list-devices   # 列出所有 HID 设备
python src/main.py --port COM3      # 指定设备路径
python src/main.py --config path    # 指定配置文件路径
```

### 运行脚本选项

```bash
run.bat                               # 启动同步
run.bat --help                        # 查看帮助
run.bat --list-devices                # 列出 HID 设备
run.bat --status                      # 检查状态
```

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────┐
│              网易云音乐 (cloudmusic.exe)              │
│                   正在播放歌曲...                      │
└──────────────────────┬──────────────────────────────┘
                       │ ReadProcessMemory
                       ▼
┌─────────────────────────────────────────────────────┐
│                   HaloLrcSync                        │
│                                                      │
│  ┌─────────────────┐       ┌──────────────────────┐ │
│  │  memory_reader   │       │   hid_packet_builder  │ │
│  │  · 进程查找      │──────▶│   · 64字节HID包构建   │ │
│  │  · 版本检测      │       │   · 文本包/布局包     │ │
│  │  · PE文件版本    │       │   · UI模式包          │ │
│  │  · 指针链解引用  │       │   · 校验和计算        │ │
│  └─────────────────┘       └──────────┬───────────┘ │
│         ▲                              │             │
│         │                              ▼             │
│  ┌─────────────────┐       ┌──────────────────────┐ │
│  │  lyrics_parser   │       │      hid_comm         │ │
│  │  · LRC格式解析   │       │   · HID设备枚举      │ │
│  │  · 标签提取      │       │   · 设备连接/断开    │ │
│  │  · 二分查找      │       │   · 数据发送          │ │
│  └─────────────────┘       └──────────┬───────────┘ │
│                                        │             │
│  ┌─────────────────┐                   │             │
│  │     config       │                   │             │
│  │  · JSON配置      │                   │             │
│  │  · 用户/默认合并  │                   │             │
│  └─────────────────┘                   │             │
└────────────────────────────────────────┼─────────────┘
                                         │ HID Write
                                         ▼
┌─────────────────────────────────────────────────────┐
│               HALO PIXELBAR 音箱                     │
│               实时显示歌词文本                        │
└─────────────────────────────────────────────────────┘
```

### 数据流

```
网易云音乐进程
    │ ReadProcessMemory (Windows API)
    ▼
memory_reader.py ─── 读取原始歌词字符串
    │
    ▼
lyrics_parser.py ─── 解析 LRC 格式（如有时间戳）
    │
    ▼
hid_packet_builder.py ─── 打包为 64 字节 HID 包
    │
    ▼
hid_comm.py ─── 通过 hidapi 写入 USB 设备
    │
    ▼
HALO PIXELBAR ─── 显示歌词
```

---

## 📁 项目结构

```
HaloLrcSync/
├── src/
│   ├── main.py                  # 主程序入口 / LyricSynchronizer
│   ├── config.py                # JSON 配置管理
│   ├── memory_reader.py         # 网易云音乐内存读取（指针链解引用）
│   ├── lyrics_parser.py         # LRC 歌词格式解析器
│   ├── hid_packet_builder.py    # HID 协议包构建器
│   └── hid_comm.py              # USB HID 通信模块
├── docs/
│   ├── address_guide.md         # 内存地址查找指南（Cheat Engine）
│   ├── address_scanner.py       # 自动地址扫描工具
│   └── 如何查看指针扫描结果.md   # 指针扫描教程
├── requirements.txt             # 依赖：psutil, hid
├── run.bat                      # Windows 一键启动脚本
└── README.md
```

---

## 🔧 HID 协议

### 数据包类型

| 类型 | 说明 |
|------|------|
| **文本包** | 显示文本内容（最长 50 字符） |
| **布局包** | 设置文本对齐与滚动方式 |
| **UI 模式包** | 切换音箱的 UI 显示主题 |

### 支持的布局

| 布局 | 枚举值 | 说明 |
|------|--------|------|
| LEFT | `TextLayout.LEFT` | 左对齐 |
| CENTER | `TextLayout.CENTER` | 居中 |
| RIGHT | `TextLayout.RIGHT` | 右对齐 |
| STRETCH | `TextLayout.STRETCH` | 拉伸填充 |
| SCROLL_LEFT_TO_RIGHT | `TextLayout.SCROLL_LEFT_TO_RIGHT` | 从左向右滚动 |
| SCROLL_RIGHT_TO_LEFT | `TextLayout.SCROLL_RIGHT_TO_LEFT` | 从右向左滚动 |

### 支持的 UI 模式

| 模式 | 枚举值 | 说明 |
|------|--------|------|
| 时钟 | `UIModel.CLOCK` | 时钟显示 |
| 游戏 | `UIModel.GAME` | 游戏主题 |
| 工作 | `UIModel.WORK` | 工作主题 |
| 阅读 | `UIModel.READ` | 阅读主题 |
| 猫咪 | `UIModel.CATS` | 猫咪主题 |
| 狗狗 | `UIModel.DOGS` | 狗狗主题 |
| 表情 | `UIModel.MEMES` | 表情主题 |
| 赛博 | `UIModel.CYBER` | 赛博朋克主题 |
| 波浪 | `UIModel.WAVES` | 波浪主题 |

---

## 📝 配置

配置文件位置：`%USERPROFILE%\.halo_lrc_sync\config.json`

```json
{
  "lyrics": {
    "scroll_speed": 1,
    "display_duration": 3,
    "scroll_duration": 0.5,
    "sync_offset_ms": 0,
    "max_chars_per_line": 20
  },
  "hid": {
    "auto_detect": true,
    "device_keywords": ["halo", "pixel", "花再", "pixelbar"]
  },
  "app": {
    "log_level": "INFO",
    "cache_dir": "cache",
    "auto_start": false
  }
}
```

---

## 🔄 支持的网易云音乐版本

| 版本 | 状态 | 偏移配置 |
|------|------|----------|
| 3.1.32 | ✅ 支持（基于 3.1.30，待验证） | `0x01DF44D0 → 0x120 → 0x8 → 0x0` |
| 3.1.30 | ✅ 支持 | `0x01DF44D0 → 0x120 → 0x8 → 0x0` |
| 3.1.29 | ✅ 支持 | `0x01DEB4D0 → 0x120 → 0x8 → 0x0` |
| 3.1.28 | ✅ 支持 | `0x01DDF290 → 0x120 → 0x8 → 0x0` |
| 3.1.27 | ✅ 支持 | `0x01DDE290 → 0xE0 → 0x8 → 0xE8 → 0x38 → 0x118 → 0x8 → 0x0` |
| 3.1.26 | ✅ 支持 | `0x01DD5130 → 0xE8 → 0x38 → 0x120 → 0x18 → 0x0` |
| 3.1.25 | ✅ 支持 | `0x01DAFF60 → 0xE0 → 0x8 → 0x128 → 0x18 → 0x0` |

> 💡 网易云音乐更新后如无法使用，使用 `docs/address_scanner.py` 自动扫描新地址，
> 或参考 `docs/address_guide.md` 手动查找偏移。

---

## 🐛 常见问题

<details>
<summary><b>提示权限不足？</b></summary>

HID 设备通信和进程内存读取都需要**管理员权限**。右键点击 `run.bat` 或命令提示符，选择 **"以管理员身份运行"**。
</details>

<details>
<summary><b>找不到 HID 设备？</b></summary>

1. 确认音箱已通过 USB 连接电脑
2. **以管理员身份运行** 程序
3. 使用 `--list-devices` 检查设备识别情况
4. 检查设备管理器中是否有未知的 HID 设备
</details>

<details>
<summary><b>歌词读取不到？</b></summary>

1. 确认网易云音乐版本在支持列表中（见上表）
2. **必须开启** 网易云音乐的 **桌面歌词** 功能
3. 确认程序以管理员权限运行
4. 使用 `--status` 检查状态
5. 尝试换一首歌（某些本地歌曲可能不加载歌词到内存）
</details>

<details>
<summary><b>网易云音乐更新后无法使用？</b></summary>

每次更新后歌词的内存地址可能变化。请使用 `docs/address_scanner.py` 自动扫描，或按 `docs/address_guide.md` 手动用 Cheat Engine 查找新偏移。
</details>

---

## 🧪 开发相关

### 添加新版本支持

内存地址存储在 `src/memory_reader.py` 的 `VERSION_ADDRESS_MAP` 字典中：

```python
VERSION_ADDRESS_MAP = {
    "3.2.0": (0x新基址偏移, 0x偏移1, 0x偏移2, ..., 0x0),
}
```

找到新地址的详细步骤见 `docs/address_guide.md`。

### 依赖

```bash
pip install psutil hid
```

- [`psutil`](https://github.com/giampaolo/psutil) — 进程查找与管理
- [`hid`](https://github.com/libusb/hidapi) — HID 设备通信（Python bindings for hidapi）

---

## 🙏 参考项目

- [HaloPixelToolBox](https://github.com/XFEstudio/HaloPixelToolBox) — C# 实现的歌词同步工具，本项目参考其 HID 协议实现
- [hidapi](https://github.com/libusb/hidapi) — 跨平台 HID 设备通信库

## 📄 免责声明

本项目仅用于**学习和研究目的**，请勿用于商业用途。歌词版权归原作者所有。

## 👤 Author

**nxz1026**
- GitHub: [https://github.com/nxz1026](https://github.com/nxz1026)
