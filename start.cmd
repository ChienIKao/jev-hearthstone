@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Please run setup.cmd first.
  pause
  exit /b 1
)
if not exist "data\cards.zhTW.json" (
  echo Please run setup.cmd to download card data first.
  pause
  exit /b 1
)
start "Laya Hearthstone" ".venv\Scripts\pythonw.exe" "%~dp0scripts\run.py" android_app
