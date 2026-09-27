@echo off
rem SweetVox launcher: run the GUI as administrator (it writes Equalizer APO config)
chcp 65001 >nul
set "APP=%~dp0vocal_focus_gui.py"
set "PY="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PY set "PY=%%i"
if not defined PY for /f "delims=" %%i in ('where pyw 2^>nul') do if not defined PY set "PY=%%i"
if not defined PY (
  echo Python not found. Install Python 3.11+ from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%PY%' -ArgumentList ('\"' + '%APP%' + '\"')"
