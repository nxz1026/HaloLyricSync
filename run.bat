@echo off
REM HALO OIXELBAR 歌词同步器 - Windows启动脚本

echo ========================================
echo HALO OIXELBAR 歌词同步器
echo ========================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.8或更高版本
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 检查Node.js是否安装
node --version >nul 2>&1
if errorlevel 1 (
    echo [警告] 未找到Node.js，部分功能可能不可用
    echo 下载地址: https://nodejs.org/
    echo.
)

REM 检查虚拟环境是否存在
if not exist ".venv" (
    echo [提示] 创建虚拟环境...
    python -m venv .venv
)

REM 激活虚拟环境
call .venv\Scripts\activate.bat

REM 安装依赖
echo [提示] 检查依赖...
pip install -r requirements.txt -q

REM 解析命令行参数
set "COMMAND=%1"

if "%COMMAND%"=="--help" goto :show_help
if "%COMMAND%"=="-h" goto :show_help
if "%COMMAND%"=="--install-api" goto :install_api
if "%COMMAND%"=="--start-api" goto :start_api
if "%COMMAND%"=="--check-api" goto :check_api
if "%COMMAND%"=="--list-devices" goto :list_devices

REM 默认运行主程序
echo.
echo [提示] 启动歌词同步器...
echo [提示] 按 Ctrl+C 可随时停止
echo.
python src\main.py %*

goto :end

:show_help
echo 使用方法:
echo.
echo   run.bat                  - 启动歌词同步器
echo   run.bat --help           - 显示帮助信息
echo   run.bat --install-api    - 安装 NeteaseCloudMusicApi
echo   run.bat --start-api     - 启动 API 服务器
echo   run.bat --check-api     - 检查 API 服务器状态
echo   run.bat --list-devices   - 列出可用串口设备
echo.
echo 示例:
echo   run.bat --port COM3      - 指定串口设备启动
echo   run.bat --install-api    - 先安装API再启动
echo.

:end
if not defined COMMAND (
    pause
)
