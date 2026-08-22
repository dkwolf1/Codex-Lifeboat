@echo off
setlocal
chcp 65001 >nul
title Controleer Codex Portable Backup 2.0
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Controleer-CodexBackup.ps1"
set "resultaat=%ERRORLEVEL%"
echo.
if not "%resultaat%"=="0" echo CONTROLE MISLUKT. Gebruik deze back-up niet voor herstel.
if "%resultaat%"=="0" echo CONTROLE GESLAAGD.
echo.
pause
exit /b %resultaat%
