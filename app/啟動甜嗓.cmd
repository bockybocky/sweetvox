@echo off
rem 甜嗓 SweetVox（女聲前移／通透化）— 用管理員權限啟動，因為要寫 Equalizer APO 的設定檔
set PY=C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe
if not exist "%PY%" set PY=C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe
powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%PY%' -ArgumentList '\"E:\AI\workspace\vocal_focus\app\vocal_focus_gui.py\"'"
