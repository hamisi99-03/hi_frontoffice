@echo off
title MeatMagic Updater
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_meatmagic.ps1"
echo.
pause
