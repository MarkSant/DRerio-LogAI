@echo off
REM Double-clickable entry point for install.ps1.
REM
REM Why this file exists at all: Windows does not run a .ps1 on double-click.
REM Explorer's default action for .ps1 is "open in an editor" -- on a current
REM Windows 11 that is Notepad -- and even from a prompt the default
REM ExecutionPolicy on a client OS is Restricted, which refuses to run any
REM script. A .ps1 extracted from a downloaded ZIP carries the Mark of the Web
REM as well, so it is blocked even at RemoteSigned. A .cmd has none of those
REM restrictions.
REM
REM The single line below is the whole file: it launches PowerShell with the
REM policy bypassed for THAT process only. It changes nothing on the machine.

setlocal
echo.
echo  Installing DRerio LogAI...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" (
    echo  Setup did not finish. The message above says what to do.
)
echo  Press any key to close this window.
pause >nul
exit /b %EXITCODE%
