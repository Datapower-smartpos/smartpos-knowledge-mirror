@echo off
setlocal
set PROJECT=C:\AI\SmartPOS\SmartPOS_Daemon
set CASE=All
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Test-SmartPOSDaemon.ps1" -ProjectRoot "%PROJECT%" -Case "%CASE%"
echo ExitCode=%ERRORLEVEL%
endlocal
