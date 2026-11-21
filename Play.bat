@echo off
title Caliope
REM Double-click to play. Sets everything up on the first run, then starts the app and opens it.
REM The desktop shortcut runs this through Caliope.vbs with --quiet: no black window, a loading screen instead.
cd /d "%~dp0backend"
set "QUIET="
if /i "%~1"=="--quiet" set "QUIET=1"
if not exist data mkdir data
set "SPLASH=%~dp0backend\data\splash.txt"
> "%SPLASH%" echo 3;Starting...

REM --- Python: the "py" launcher (Python install manager) first, then "python".
set "PYCMD="
py -3.12 --version >nul 2>nul && set "PYCMD=py -3.12"
if not defined PYCMD ( py -3 --version >nul 2>nul && set "PYCMD=py -3" )
if not defined PYCMD ( python --version >nul 2>nul && set "PYCMD=python" )
if not defined PYCMD (
    set "FAIL=Python was not found. Install it from python.org - or run: py install 3.12 - then start Caliope again."
    goto :fail
)

REM --- The loading screen (pythonw: no window of its own). Without tkinter it just doesn't appear.
set "PYW=pythonw"
if "%PYCMD%"=="py -3.12" set "PYW=pyw -3.12"
if "%PYCMD%"=="py -3" set "PYW=pyw -3"
if exist .venv\Scripts\pythonw.exe set "PYW=.venv\Scripts\pythonw.exe"
start "" %PYW% splash.py

REM --- Private Python environment for the app (created once).
if not exist .venv\Scripts\python.exe (
    echo Setting up for the first time. This takes a few minutes and needs internet...
    > "%SPLASH%" echo 8;Setting up for the first time. This takes a few minutes and needs internet...
    %PYCMD% -m venv .venv
    if errorlevel 1 ( set "FAIL=Could not create the Python environment." & goto :fail )
)

REM --- Install or update the packages when requirements.txt changed.
fc /b requirements.txt .venv\installed-requirements.txt >nul 2>nul
if errorlevel 1 (
    echo Installing Python packages...
    > "%SPLASH%" echo 15;Installing Python packages, first time or after an update...
    .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q --upgrade pip
    .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt
    if errorlevel 1 ( set "FAIL=Package installation failed. Check your internet connection and try again." & goto :fail )
    copy /y requirements.txt .venv\installed-requirements.txt >nul
)

REM --- The app's own window (pywebview). Optional: without it the game opens in an Edge app window.
REM Tried once (the result is kept in .venv\window-tried; delete that file to try again).
if not exist .venv\window-tried (
    > "%SPLASH%" echo 25;Installing the app window...
    .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q "pywebview>=5" >nul 2>nul
    echo tried> .venv\window-tried
)

REM --- Build the interface if needed, start the app and open its window.
> "%SPLASH%" echo 30;Starting Caliope...
.venv\Scripts\python.exe launcher.py %*
if errorlevel 1 if not defined QUIET pause
exit /b

:fail
REM Without the black window the loading screen shows the problem; with it, the message stays on screen.
> "%SPLASH%" echo error;%FAIL%
if defined QUIET if not defined PYCMD powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [void][System.Windows.MessageBox]::Show('%FAIL%', 'Caliope')"
if not defined QUIET ( echo %FAIL% & pause )
exit /b 1
