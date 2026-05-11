# HALO OIXELBAR 歌词同步软件

自动获取网易云音乐歌词，同步显示到 HALO OIXELBAR 音箱上！

## ✨ 功能特点

- 🎵 **网易云音乐集成** - 自动获取当前播放歌曲和歌词
- 📜 **LRC歌词解析** - 支持标准LRC格式歌词，支持时间戳解析
- 🔌 **USB通信** - 与HALO OIXELBAR音箱通过USB连接通信
- ⚡ **实时同步** - 毫秒级歌词同步显示
- 🪟 **Windows优化** - 专为Windows系统设计，支持自动检测设备
- ⚙️ **可配置** - 支持歌词显示时长、滚动速度等参数调整
- 💾 **本地缓存** - 歌词自动缓存，减少API请求
- 🔍 **自动检测** - 自动识别歌曲切换和播放状态

## 📋 系统要求

- **操作系统**: Windows 10/11 (推荐)
- **Python**: 3.8 或更高版本
- **Node.js**: 16.0 或更高版本（用于运行API服务）
- **硬件**: HALO OIXELBAR 音箱 + USB数据线
- **播放器**: 网易云音乐（PC版）

## 🚀 快速开始

### 方法一：Windows一键运行

1. 下载或克隆本项目
2. 双击运行 `run.bat`
3. 程序会自动安装 NeteaseCloudMusicApi（如果未安装）
4. 开始使用！

### 方法二：手动安装

```bash
# 1. 克隆项目
git clone https://github.com/yourusername/HaloLrcSync.git
cd HaloLrcSync

# 2. 创建虚拟环境（推荐）
python -m venv .venv
# Windows激活
.venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行程序（会自动安装 NeteaseCloudMusicApi）
python src/main.py
```

## 📖 使用说明

### 快速启动（推荐）

```bash
# 一键启动（自动安装并运行API服务）
python src/main.py
```

### 管理 NeteaseCloudMusicApi

```bash
# 检查 API 服务器状态
python src/main.py --check-api

# 安装 NeteaseCloudMusicApi
python src/main.py --install-api

# 单独启动 API 服务器
python src/main.py --start-api

# 启动同步器但不同步启动 API
python src/main.py --no-auto-api
```

### 其他选项

```bash
# 列出可用的串口设备
python src/main.py --list-devices

# 指定设备端口
python src/main.py --port COM3

# 指定配置文件
python src/main.py --config my_config.json
```

## 📦 NeteaseCloudMusicApi 集成说明

本项目**内置**了 NeteaseCloudMusicApi 管理功能，可以自动：

### 1. 自动安装

首次运行时，程序会自动下载并安装 NeteaseCloudMusicApi：

```
[Sync] 正在启动 NeteaseCloudMusicApi...
[NeteaseApi] 开始安装 NeteaseCloudMusicApi...
[NeteaseApi] 获取最新版本信息...
[NeteaseApi] 安装 Node.js 依赖...
[成功] 安装完成!
[Sync] API 服务器启动成功
```

### 2. 自动启动

每次运行同步器时，会自动检查并启动 API 服务器。

### 3. 手动管理

如果需要手动管理 API 服务器，可以使用以下脚本：

```bash
# 查看 API 管理帮助
python src/api_server.py --help

# 输出:
# options:
#   --install    安装 NeteaseCloudMusicApi
#   --start      启动 API 服务器
#   --stop       停止 API 服务器
#   --status     查看服务器状态
#   --force      强制重新安装
```

### 4. API 服务器位置

安装目录：`~/.halo_lrc_sync/NeteaseCloudMusicApi/`

### 5. API 地址

- **本地地址**: http://localhost:3000
- **API文档**: http://localhost:3000/api.html

## 📁 项目结构

```
HaloLrcSync/
├── src/
│   ├── __init__.py         # 包信息
│   ├── main.py             # 主程序入口
│   ├── config.py           # 配置管理模块
│   ├── netease_api.py      # 网易云音乐API客户端
│   ├── api_server.py       # NeteaseCloudMusicApi管理器 ⭐新增
│   ├── lrc_parser.py       # 歌词解析器
│   └── usb_comm.py         # USB通信模块
├── docs/                   # 文档目录
├── resources/              # 资源文件
├── requirements.txt        # 依赖列表
├── run.bat                # Windows一键启动脚本
└── README.md             # 本文件
```

## ⚙️ 配置说明

程序首次运行时会创建配置文件：
`C:\Users\你的用户名\.halo_lrc_sync\config.json`

### 配置选项

```json
{
  "netease": {
    "host": "127.0.0.1",      // API服务器地址
    "port": 3000,              // API服务器端口（默认3000）
    "api_timeout": 5           // API超时时间（秒）
  },
  "lyrics": {
    "scroll_speed": 1,        // 滚动速度
    "display_duration": 3,    // 显示时长（秒）
    "scroll_duration": 0.5,   // 滚动动画时长（秒）
    "sync_offset_ms": 0,      // 同步偏移（毫秒）
    "max_chars_per_line": 20  // 每行最大字符数
  },
  "usb": {
    "device_id": "",          // 设备ID
    "baud_rate": 9600,        // 波特率
    "timeout": 2,             // 超时时间（秒）
    "auto_detect": true       // 自动检测设备
  },
  "app": {
    "log_level": "INFO",      // 日志级别
    "cache_dir": "cache",     // 缓存目录
    "auto_start": false,       // 开机启动
    "minimize_to_tray": false  // 最小化到托盘
  }
}
```

## 🔧 常见问题

### Q: 提示"未找到 Node.js"？

A: 请先安装 Node.js
- 下载地址: https://nodejs.org/
- 推荐安装 LTS 版本

### Q: API 服务器安装失败？

A: 可以手动安装：
```bash
# 克隆仓库
git clone https://github.com/Binaryify/NeteaseCloudMusicApi.git ~/.halo_lrc_sync/NeteaseCloudMusicApi

# 进入目录
cd ~/.halo_lrc_sync/NeteaseCloudMusicApi

# 安装依赖
npm install

# 启动服务器
node bin/www
```

### Q: API 服务器连接失败？

A: 检查以下几点：
1. 服务器是否正在运行（运行 `--check-api` 查看状态）
2. 端口是否被占用（默认 3000）
3. 防火墙是否阻止连接

### Q: 如何修改 API 服务器端口？

A: 修改配置文件中的 `netease.port` 为其他端口（如 8080）

### Q: 找不到设备怎么办？

A: 运行 `--list-devices` 查看可用设备，然后使用 `--port` 参数指定

### Q: 歌词不同步？

A: 调整 `sync_offset_ms` 参数，正值延迟显示，负值提前显示

## 📝 开发说明

### 添加新的音乐源

1. 创建新的 API 类继承基础类
2. 实现 `get_current_play_status()` 和 `get_lyrics()` 方法
3. 修改配置支持新的音乐源

### 自定义USB协议

修改 `src/usb_comm.py` 中的 `send_text()` 方法

### 测试

```bash
pip install pytest
pytest tests/
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License - 详见 LICENSE 文件

## ⚠️ 免责声明

- 本项目仅用于学习和研究目的
- 请勿用于商业用途
- 歌词版权归原作者所有

---

**Made with ❤️ for HALO OIXELBAR users**
