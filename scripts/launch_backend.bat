@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONLEGACYWINDOWSSTDIO="
set "PROJECT_ROOT=%~dp0.."
pushd "%PROJECT_ROOT%"
if not exist "logs" mkdir "logs" >nul 2>nul
set "PYEXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"
"%PYEXE%" "%PROJECT_ROOT%\scripts\start_backend.py" 1>>"%PROJECT_ROOT%\logs\backend.log" 2>>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [ERROR] Backend exited with code %RC%. See logs\backend.log.
popd
exit /b %RC%
