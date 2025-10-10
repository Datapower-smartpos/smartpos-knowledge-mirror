@echo off
setlocal ENABLEDELAYEDEXPANSION
REM SmartPOS USB DevCtl — BAT wrapper (v1.4.1)
REM Запускает каноничный CLI с удобными алиасами. Хранить рядом с usb_devctl_cli.py

set SCRIPT_DIR=%~dp0
set PY_EXE=python
set CLI="%SCRIPT_DIR%usb_devctl_cli.py"

%PY_EXE% -c "import sys;print(sys.version)" >nul 2>&1 || (
  echo [ERROR] Python не найден. Установите Python 3.9+ x64 и добавьте в PATH.
  exit /b 1
)

set CMD=%1
if "%CMD%"=="" goto :HELP
shift

if /I "%CMD%"=="status"           goto :STATUS
if /I "%CMD%"=="preflight"        goto :PREFLIGHT
if /I "%CMD%"=="policy-reload"    goto :POLICY
if /I "%CMD%"=="service-restart"  goto :SVC
if /I "%CMD%"=="recycle"          goto :RECYCLE
if /I "%CMD%"=="export-zip"       goto :EXPORT

REM Фоллбек: пробрасываем команды как есть
%PY_EXE% %CLI% %CMD% %*
exit /b %ERRORLEVEL%

:STATUS
%PY_EXE% %CLI% status %*
exit /b %ERRORLEVEL%

:PREFLIGHT
%PY_EXE% %CLI% preflight %*
exit /b %ERRORLEVEL%

:POLICY
%PY_EXE% %CLI% policy-reload %*
exit /b %ERRORLEVEL%

:SVC
%PY_EXE% %CLI% service-restart %*
exit /b %ERRORLEVEL%

:RECYCLE
REM Удобный алиас под старое имя команды → новое действие
%PY_EXE% %CLI% action recycle %*
exit /b %ERRORLEVEL%

:EXPORT
%PY_EXE% %CLI% export-zip %*
exit /b %ERRORLEVEL%

:HELP
echo.
echo SmartPOS USB DevCtl — BAT wrapper
echo Использование:
echo   run_usb_devctl.bat ^<status^|preflight^|policy-reload^|service-restart^|recycle^|export-zip^> [параметры]
echo Примеры:
echo   run_usb_devctl.bat status
echo   run_usb_devctl.bat preflight --api-key YOUR_KEY
echo   run_usb_devctl.bat policy-reload
echo   run_usb_devctl.bat service-restart
echo   run_usb_devctl.bat recycle
echo   run_usb_devctl.bat export-zip --mask "*.log" --out "C:\Temp\usb.zip"
exit /b 2