@echo off
cd /d "%~dp0"
echo Starting MaintainSMIP...
start "MaintainSMIP Server" cmd /k "%~dp0start.bat"
timeout /t 3 /nobreak >nul
start http://localhost:8000
echo Browser opened at http://localhost:8000
echo Keep the server window open while you use the app.