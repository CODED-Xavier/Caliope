@echo off
title Caliope
REM Double-click to play. Sets everything up on the first run, then starts the app and opens it.
cd /d "%~dp0backend"

REM --- Python: the "py" launcher (Python install manager) first, then "python".
set "PYCMD="
py -3.12 --version >nul 2>nul && set "PYCMD=py -3.12"
if not defined PYCMD ( py -3 --version >nul 2>nul && set "PYCMD=py -3" )
if not defined PYCMD ( python --version >nul 2>nul && set "PYCMD=python" )
if not defined PYCMD (
    echo Python was not found. Install it from python.org ^(or run: py install 3.12^), then run Play.bat again.
    pause
    exit /b 1
)

REM --- Private Python environment for the app (created once).
if not exist .venv\Scripts\python.exe (
    echo Setting up for the first time. This takes a few minutes and needs internet...
    %PYCMD% -m venv .venv
    if errorlevel 1 ( echo Could not create the Python environment. & pause & exit /b 1 )
)

REM --- Install or update the packages when requirements.txt changed.
fc /b requirements.txt .venv\installed-requirements.txt >nul 2>nul
if errorlevel 1 (
    echo Installing Python packages...
    .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q --upgrade pip
    .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt
    if errorlevel 1 ( echo Package installation failed. Check your internet connection and try again. & pause & exit /b 1 )
    copy /y requirements.txt .venv\installed-requirements.txt >nul
)

REM --- Build the interface if needed, start LM Studio and the app, open the browser.
.venv\Scripts\python.exe launcher.py %*
if errorlevel 1 pause
