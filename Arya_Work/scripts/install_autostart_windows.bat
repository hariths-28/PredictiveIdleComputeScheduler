@echo off
REM ========================================================
REM Phase 0 Step 4: Register Logger to Autostart on Login (Windows)
REM ========================================================

set TARGET_DIR=%~dp0\..
set SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\IdleComputeLogger.vbs

echo Creating startup launcher in: "%SHORTCUT_PATH%"

(
echo Set WshShell = CreateObject("WScript.Shell"^)
echo WshShell.CurrentDirectory = "%TARGET_DIR%"
echo WshShell.Run "python main.py --log-only --interval 15 --csv-file laptop_telemetry.csv", 0, False
) > "%SHORTCUT_PATH%"

echo [SUCCESS] Telemetry logger registered to autostart silently on user login!
echo To test, you can run: "%SHORTCUT_PATH%"
pause
