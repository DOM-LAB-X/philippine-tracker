@echo off
setlocal enabledelayedexpansion

echo ============================================
echo  PhilFlight Tracker — Windows Build Script
echo ============================================

:: Install / upgrade dependencies
pip install --upgrade -r requirements.txt
if errorlevel 1 (echo [ERROR] pip install failed & pause & exit /b 1)

pip install --upgrade pyinstaller
if errorlevel 1 (echo [ERROR] PyInstaller install failed & pause & exit /b 1)

:: Generate icon if missing
if not exist assets\icon.ico (
    echo Generating icon...
    python assets\create_icon.py
)

:: Build single-file Windows executable
pyinstaller ^
    --name "PhilFlight Tracker" ^
    --windowed ^
    --onefile ^
    --icon "assets\icon.ico" ^
    --add-data "assets\icon.ico;assets" ^
    --add-data "assets\icon.png;assets" ^
    --add-data "config\default_config.json;config" ^
    --add-data "version.json;." ^
    main.py

if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo Build complete!  Output: dist\PhilFlight Tracker.exe
pause
