@echo off
setlocal EnableExtensions
title Remember Me Launcher

set "BASE=%~dp0"
set "PROJECT_DIR="

echo.
echo === Remember Me Launcher ===
echo Searching project files...

call :find_project

if not defined PROJECT_DIR (
  echo Project folder was not found. Trying to extract a zip package...
  set "ZIP_FILE="
  for %%Z in ("%BASE%*.zip") do (
    if not defined ZIP_FILE set "ZIP_FILE=%%~fZ"
  )

  if not defined ZIP_FILE (
    echo [ERROR] No project folder or zip package was found beside this BAT file.
    echo Put this BAT file beside the project zip, or extract the zip first.
    pause
    exit /b 1
  )

  powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath $env:ZIP_FILE -DestinationPath $env:BASE -Force"
  if errorlevel 1 (
    echo [ERROR] Failed to extract the zip package.
    pause
    exit /b 1
  )

  call :find_project
)

if not defined PROJECT_DIR (
  echo [ERROR] Could not find backend and frontend package files.
  pause
  exit /b 1
)

echo Project folder:
echo %PROJECT_DIR%
echo.

if not exist "%PROJECT_DIR%\backend\.env" (
  echo Creating backend local .env...
  > "%PROJECT_DIR%\backend\.env" echo DATABASE_URL="file:./dev.db"
  >> "%PROJECT_DIR%\backend\.env" echo JWT_SECRET="dev-jwt-secret-change-for-production"
  >> "%PROJECT_DIR%\backend\.env" echo JWT_REFRESH_SECRET="dev-refresh-secret-change-for-production"
  >> "%PROJECT_DIR%\backend\.env" echo JWT_EXPIRATION="15m"
  >> "%PROJECT_DIR%\backend\.env" echo JWT_REFRESH_EXPIRATION="7d"
  >> "%PROJECT_DIR%\backend\.env" echo FRONTEND_URL="http://localhost:3000"
  >> "%PROJECT_DIR%\backend\.env" echo PORT=3001
)

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js is not installed or not in PATH.
  echo Please install Node.js 20 or newer, then run this file again.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm is not available.
  echo Please reinstall Node.js with npm enabled.
  pause
  exit /b 1
)

if not exist "%PROJECT_DIR%\backend\node_modules\@nestjs\core" (
  echo Installing backend dependencies...
  cd /d "%PROJECT_DIR%\backend"
  call npm install --registry=https://registry.npmjs.org/
  if errorlevel 1 (
    echo [ERROR] Backend dependency installation failed.
    pause
    exit /b 1
  )
  call npx prisma generate
)

if not exist "%PROJECT_DIR%\frontend\node_modules\next" (
  echo Installing frontend dependencies...
  cd /d "%PROJECT_DIR%\frontend"
  call npm install --legacy-peer-deps --registry=https://registry.npmjs.org/
  if errorlevel 1 (
    echo [ERROR] Frontend dependency installation failed.
    pause
    exit /b 1
  )
)

echo Starting backend at http://localhost:3001
start "Remember Me Backend" cmd /k "cd /d ""%PROJECT_DIR%\backend"" && npm run start:dev"

timeout /t 3 /nobreak >nul

echo Starting frontend at http://localhost:3000
start "Remember Me Frontend" cmd /k "cd /d ""%PROJECT_DIR%\frontend"" && npm run dev"

echo.
echo Open http://localhost:3000 in your browser.
echo Keep the two command windows open while using the project.
pause
exit /b 0

:find_project
for /d /r "%BASE%" %%D in (*) do (
  if not defined PROJECT_DIR (
    if exist "%%D\backend\package.json" (
      if exist "%%D\frontend\package.json" (
        set "PROJECT_DIR=%%D"
      )
    )
  )
)
exit /b 0
