@echo off
REM Builds the interface once. Afterwards the backend serves it at http://127.0.0.1:8000
REM so you only need start-backend.bat.
cd /d "%~dp0frontend"
if not exist node_modules ( call npm install )
call npm run build
echo.
echo Done. Restart start-backend.bat and open http://127.0.0.1:8000
pause
