@echo off
setlocal enabledelayedexpansion
title PhilFlight Tracker - Installer

echo.
echo  ==========================================
echo   PhilFlight Tracker - First-Time Setup
echo  ==========================================
echo.

:: Install Python packages
echo  [1/3] Installing required packages...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  ERROR: pip failed. Make sure Python is installed.
    pause & exit /b 1
)
echo        Done.
echo.

:: Generate icon
echo  [2/3] Generating app icon...
python assets\create_icon.py
echo        Done.
echo.

:: Write a PowerShell script to a temp file to avoid encoding issues
echo  [3/3] Creating desktop shortcut...
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"
set "PS_SCRIPT=%TEMP%\phil_shortcut.ps1"

(
    echo $ws      = New-Object -ComObject WScript.Shell
    echo $desktop = [Environment]::GetFolderPath('Desktop'^)
    echo $s       = $ws.CreateShortcut($desktop + '\PhilFlight Tracker.lnk'^)
    echo $s.TargetPath       = 'pythonw'
    echo $s.Arguments        = '"%APP_DIR%\main.py"'
    echo $s.WorkingDirectory = '%APP_DIR%'
    echo $s.IconLocation     = '%APP_DIR%\assets\icon.ico'
    echo $s.Description      = 'PhilFlight Tracker'
    echo $s.Save(^)
) > "%PS_SCRIPT%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
del "%PS_SCRIPT%" 2>nul

set "SHORTCUT=%USERPROFILE%\Desktop\PhilFlight Tracker.lnk"
if exist "%SHORTCUT%" (
    echo        Shortcut created on your Desktop!
) else (
    echo        Shortcut could not be created.
    echo        You can still open the app by double-clicking launch.bat
)

echo.
echo  ==========================================
echo   Setup complete!
echo   Double-click "PhilFlight Tracker" on
echo   your Desktop to open the app.
echo  ==========================================
echo.
pause
