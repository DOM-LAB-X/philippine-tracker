@echo off
setlocal enabledelayedexpansion
title PhilFlight Tracker — Installer

echo.
echo  ==========================================
echo   PhilFlight Tracker — First-Time Setup
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

:: Create desktop shortcut using PowerShell
echo  [3/3] Creating desktop shortcut...
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"
set "SHORTCUT=%USERPROFILE%\Desktop\PhilFlight Tracker.lnk"
set "ICON=%APP_DIR%\assets\icon.ico"
set "SCRIPT=%APP_DIR%\main.py"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s  = $ws.CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath    = 'pythonw';" ^
  "$s.Arguments     = '\"%SCRIPT%\"';" ^
  "$s.WorkingDirectory = '%APP_DIR%';" ^
  "$s.IconLocation  = '%ICON%';" ^
  "$s.Description   = 'PhilFlight Tracker — Live Philippine flight monitor';" ^
  "$s.Save();"

if exist "%SHORTCUT%" (
    echo        Shortcut created on your Desktop!
) else (
    echo        Could not create shortcut ^(PowerShell may be restricted^).
    echo        You can still launch the app by double-clicking launch.bat
)

echo.
echo  ==========================================
echo   Setup complete!
echo   Double-click "PhilFlight Tracker" on
echo   your Desktop to open the app.
echo  ==========================================
echo.
pause
