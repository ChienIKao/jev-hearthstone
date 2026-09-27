@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\bootstrap.py
if errorlevel 1 goto failed
echo Setup complete. Open start.cmd to launch Laya Hearthstone.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.12 with the Python Launcher and check your network connection.
pause
exit /b 1
