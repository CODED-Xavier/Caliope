@echo off
title Build LocalRPG.exe
REM Makes the Windows program in the LocalRPG folder. Run Play.bat once first (it sets up Python).
cd /d "%~dp0backend"
if not exist .venv\Scripts\python.exe ( echo Run Play.bat once first. & pause & exit /b 1 )
.venv\Scripts\python.exe build_exe.py
pause
