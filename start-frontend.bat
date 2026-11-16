@echo off
REM Starts the web interface in development mode (auto-reloads when the code changes).
REM Open http://localhost:5173 after it starts. The backend (start-backend.bat) must be running too.
cd /d "%~dp0frontend"
where npm >nul 2>nul
if errorlevel 1 (
    echo Node.js was not found. Install the LTS version from nodejs.org, then run this again.
    pause
    exit /b 1
)
if not exist node_modules (
    echo Installing packages ^(first run only, needs internet^)...
    call npm install
    if errorlevel 1 ( echo Installation failed. & pause & exit /b 1 )
)
echo.
echo Interface running at http://localhost:5173
call npm run dev -- --open
pause
