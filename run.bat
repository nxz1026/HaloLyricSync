@echo off
REM HALO PIXELBAR 歌词同步器 - Windows启动脚本

REM 切换到脚本所在目录，确保相对路径正确
cd /d "%~dp0"

REM 切换终端到 UTF-8 代码页，避免 Python 输出中文/emoji 时乱码或抛 UnicodeEncodeError
chcp 65001 >nul

echo ========================================
echo HALO PIXELBAR 歌词同步器 (HaloLyricSync)
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.8或更高版本
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [提示] 创建虚拟环境...
    python -m venv .venv
)

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"

REM 用 venv 的 pip 安装依赖（不依赖 activate.bat）
echo [提示] 检查依赖...
"%VENV_PYTHON%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [错误] 安装依赖失败，请检查网络或手动执行: pip install -r requirements.txt
    pause
    exit /b 1
)

REM 验证关键包可导入
"%VENV_PYTHON%" -c "import hid; import psutil" 2>nul
if errorlevel 1 (
    echo [警告] 依赖验证未通过，尝试重新安装 hidapi...
    "%VENV_PYTHON%" -m pip install --force-reinstall hidapi
)

set "COMMAND=%1"

if "%COMMAND%"=="--help" goto :show_help
if "%COMMAND%"=="-h" goto :show_help
if "%COMMAND%"=="--list-devices" goto :list_devices

echo.
echo [提示] 启动歌词同步器...
echo [提示] 按 Ctrl+C 可随时停止
echo.
"%VENV_PYTHON%" src\main.py %*

goto :end

:show_help
echo 使用方法:
echo.
echo   run.bat               - 启动歌词同步器
echo   run.bat --help        - 显示帮助信息
echo   run.bat --list-devices - 列出HID设备
echo.
echo 示例:
echo   run.bat --status       - 检查 LX Music 状态
echo   run.bat --port COM3   - 指定设备路径启动
echo.
goto :end

:list_devices
"%VENV_PYTHON%" src\main.py --list-devices
goto :end

:end
if not defined COMMAND (
    pause
)
