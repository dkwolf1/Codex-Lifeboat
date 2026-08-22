@echo off
setlocal
chcp 65001 >nul
title Codex Portable Backup 2.0
echo.
echo Sluit Codex volledig af voordat u verdergaat.
echo De standaard doelmap staat in backup-config.json.
echo.
pause
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Backup-Codex.ps1" -ConfigPath "%~dp0backup-config.json"
set "resultaat=%ERRORLEVEL%"
echo.
if not "%resultaat%"=="0" echo BACK-UP MISLUKT. Lees de foutmelding hierboven.
if "%resultaat%"=="0" echo BACK-UP GESLAAGD.
echo.
pause
exit /b %resultaat%
