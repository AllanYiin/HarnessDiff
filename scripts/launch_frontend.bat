@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONLEGACYWINDOWSSTDIO="
set "PROJECT_ROOT=%~dp0.."
set "FRONTEND_DIR=%PROJECT_ROOT%\apps\web"
if not exist "%PROJECT_ROOT%\logs" mkdir "%PROJECT_ROOT%\logs" >nul 2>nul
if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] Frontend package.json not found: %FRONTEND_DIR% 1>>"%PROJECT_ROOT%\logs\frontend.log" 2>>&1
  exit /b 1
)
pushd "%FRONTEND_DIR%"
call corepack pnpm install 1>>"%PROJECT_ROOT%\logs\frontend.log" 2>>&1
if errorlevel 1 (
  echo [ERROR] Frontend install failed. See logs\frontend.log. 1>>"%PROJECT_ROOT%\logs\frontend.log" 2>>&1
  popd
  exit /b 1
)
call corepack pnpm dev 1>>"%PROJECT_ROOT%\logs\frontend.log" 2>>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [ERROR] Frontend exited with code %RC%. See logs\frontend.log. 1>>"%PROJECT_ROOT%\logs\frontend.log" 2>>&1
popd
exit /b %RC%
