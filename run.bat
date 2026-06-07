@echo off
setlocal
cd /d "%~dp0"
echo [JAV Manager] 源码版启动 (python main.py)
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
python main.py
if errorlevel 1 (
    echo.
    echo 程序异常退出，请查看上方错误信息。
    pause
)
