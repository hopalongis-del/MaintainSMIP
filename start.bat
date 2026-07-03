@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
) else (
    set PYTHON=python
)
set PYTHONPATH=%~dp0
%PYTHON% -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
pause