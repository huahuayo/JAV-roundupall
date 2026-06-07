@echo off
setlocal
cd /d "%~dp0"

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -r requirements.txt -q

echo Building desktop executable...
python packaging\build_app_icon.py
python packaging\build_exe.py

echo Copying browser extension ...
if exist "dist\extension" rmdir /s /q "dist\extension"
xcopy /E /I /Y "extension" "dist\extension" >nul

echo.
echo Done.
echo   Executable: dist\JAV一网打尽.exe
echo   Extension:  dist\extension
pause
