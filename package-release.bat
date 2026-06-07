@echo off
setlocal
cd /d "%~dp0"

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
python packaging\make_release.py
if errorlevel 1 (
    echo.
    echo Packaging failed.
    exit /b 1
)
echo.
echo Done. See the release\ folder for the zip file.
exit /b 0
