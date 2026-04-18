@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting Django application on http://127.0.0.1:8000/
"%PYTHON_EXE%" manage.py runserver 127.0.0.1:8000
