@echo off
REM Double-click launcher for the SBS local web app.
cd /d "%~dp0"
conda run -n sbs python -m webapp
pause
