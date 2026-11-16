@echo off
REM Starts the RPG chat backend (creates the virtual environment on first run).
cd /d "%~dp0backend"

REM Find Python: prefer the "py" launcher (Python install manager), fall back to "python".
set "PYCMD="
py -3.12 --version >nul 2>nul && set "PYCMD=py -3.12"
if not defined PYCMD ( py -3 --version >nul 2>nul && set "PYCMD=py -3" )
if not defined PYCMD ( python --version >nul 2>nul && set "PYCMD=python" )
if not defined PYCMD (
    echo Python was not found. Open Command Prompt and run:  py install 3.12
    pause
    exit /b 1
)
echo Using: %PYCMD%

if not exist .venv\Scripts\activate.bat (
    echo Creating virtual environment...
    %PYCMD% -m venv .venv
    if errorlevel 1 ( echo Failed to create the environment. & pause & exit /b 1 )
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    if errorlevel 1 ( echo Package installation failed. & pause & exit /b 1 )
) else (
    call .venv\Scripts\activate.bat
)
echo.
echo Backend running at http://127.0.0.1:8000  (API docs: http://127.0.0.1:8000/docs)
echo Close this window or press Ctrl+C to stop.
python run.py
pause
