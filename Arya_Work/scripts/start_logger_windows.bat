@echo off
REM ========================================================
REM Predictive Idle-Compute: Standalone Telemetry Logger
REM Runs the logger in background every 15s to laptop_telemetry.csv
REM ========================================================

cd /d "%~dp0\.."
echo Starting Idle-Compute Telemetry Logger in background...
start /b python main.py --log-only --interval 15 --csv-file laptop_telemetry.csv
echo Logger is running! Telemetry being saved to laptop_telemetry.csv
pause
