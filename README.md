# HALO PIXELBAR 歌词同步器

通过内存读取方式获取网易云音乐歌词，同步显示到 HALO PIXELBAR 音箱。

> 核心技术：内存读取 + HID协议，与工具 HaloPixelToolBox 完全一致

## 功能特点

- **内存读取** - 直接从网易云音乐进程中读取歌词，无需 API
- **HID协议** - 使用与官方 HaloPixelToolBox 相同的 HID 协议通信
- **实时同步** - 50ms 级歌词同步显示
- **多种布局** - 支持左对齐、居中、右对齐、滚动等显示模式
- **UI模式切换** - 支持时钟、游戏、工作等多种 UI 显示模式

## 系统要求

- **操作系统**: Windows 10/11
- **Python**: 3.8 或更高版本
- **网易云音乐**: 3.1.25 - 3.1.30 版本
- **硬件**: HALO OIXELBAR 音箱 + USB 数据线
- **权限**: 管理员权限（用于 HID 通信和内存读取）

## 快速开始

### Windows 一键运行

```bash
# 克隆项目
git clone https://github.com/nxz1026/HaloLrcSync.git
cd HaloLrcSync

# 双击运行 或 命令行运行
run.bat
```

### 手动运行

```bash
pip install -r requirements.txt
python src/main.py
```

> ⚠️ 必须以管理员身份运行

## 使用说明

### 前置条件

1. 以管理员身份运行程序
2. 打开网易云音乐并播放歌曲
3. 开启网易云音乐的桌面歌词功能
4. 通过 USB 连接 HALO OIXELBAR 音箱

### 命令行选项

```bash
python src/main.py              # 启动歌词同步
python src/main.py --status    # 检查网易云音乐状态
python src/main.py --list-devices  # 列出 HID 设备
```

## 技术架构

```
网易云音乐进程 (cloudmusic.exe)
        │
        │ ReadProcessMemory
        ▼
┌───────────────────────────────────────┐
│            HaloLrcSync                │
│  ┌─────────────┐    ┌──────────────┐ │
│  │memory_reader│───▶│hid_packet_    │ │
│  │ 内存读取器  │    │ builder       │ │
│  └─────────────┘    └──────────────┘ │
│  ┌─────────────┐    ┌──────────────┐ │
│  │lyrics_parser│    │hid_comm       │ │
│  │ 歌词解析器  │    │ HID通信模块   │ │
│  └─────────────┘    └──────────────┘ │
└───────────────────────────────────────┘
        │
        │ HID Write (64字节包)
        ▼
  HALO OIXELBAR 音箱
```

## 项目结构

```
HaloLrcSync/
├── src/
│   ├── main.py              # 主程序入口
│   ├── config.py            # 配置管理
│   ├── memory_reader.py     # 网易云音乐内存读取器
│   ├── lyrics_parser.py     # LRC 歌词解析器
│   ├── hid_packet_builder.py    # HID 协议包构建器
│   └── hid_comm.py          # HID 通信模块
├── docs/
│   ├── address_guide.md     # 内存地址查找指南
│   └── address_scanner.py  # 地址扫描辅助脚本
├── requirements.txt
├── run.bat
└── README.md
```

## HID 协议

### 数据包类型

| 类型 | 说明 |
|------|------|
| 文本包 | 显示文本内容（最长50字符） |
| 布局包 | 设置文本布局 |
| UI模式包 | 切换 UI 显示模式 |

### 支持的布局

| 布局 | 说明 |
|------|------|
| LEFT / RIGHT / CENTER | 左对齐 / 右对齐 / 居中 |
| STRETCH | 拉伸 |
| SCROLL_LEFT_TO_RIGHT | 从左向右滚动 |
| SCROLL_RIGHT_TO_LEFT | 从右向左滚动 |

### 支持的 UI 模式

| 模式 | 说明 |
|------|------|
| CLOCK | 时钟 |
| GAME | 游戏 |
| WORK | 工作 |
| READ | 阅读 |
| CATS / DOGS | 猫咪 / 狗狗 |
| MEMES | 表情 |
| CYBER / WAVES | 赛博 / 波浪 |

## 支持的网易云音乐版本

| 版本 | 状态 |
|------|------|
| 3.1.30 | ✅ 支持 |
| 3.1.29 | ✅ 支持 |
| 3.1.28 | ✅ 支持 |
| 3.1.27 | ✅ 支持 |
| 3.1.26 | ✅ 支持 |
| 3.1.25 | ✅ 支持 |

> 💡 网易云音乐更新后如无法使用：
> - 使用 `docs/address_scanner.py` 自动扫描新地址
> - 或参考 `docs/address_guide.md` 手动查找偏移

## 配置

配置文件位置：`%USERPROFILE%\.halo_lrc_sync\config.json`

```json
{
  "lyrics": {
    "scroll_speed": 1,
    "display_duration": 3,
    "max_chars_per_line": 20
  },
  "hid": {
    "auto_detect": true,
    "device_keywords": ["halo", "pixel", "花再", "pixelbar"]
  }
}
```

## 常见问题

**Q: 提示权限不足？**
> HID 设备通信需要管理员权限。右键点击 `run.bat`，选择"以管理员身份运行"。

**Q: 找不到 HID 设备？**
> 1. 确认设备已通过 USB 连接
> 2. 以管理员身份运行程序
> 3. 使用 `--list-devices` 检查设备识别情况

**Q: 歌词读取不到？**
> 1. 确认网易云音乐版本在支持列表中
> 2. 确认已开启网易云音乐的桌面歌词功能
> 3. 确认程序以管理员权限运行

## 参考项目

- `https://github.com/XFEstudio/HaloPixelToolBox` - C# 实现的歌词同步工具
- `https://github.com/libusb/hidapi` - HID 设备通信库

## 免责声明

本项目仅用于学习和研究目的，请勿用于商业用途。歌词版权归原作者所有。

## Author

**nxz1026**
- GitHub: `https://github.com/nxz1026`
