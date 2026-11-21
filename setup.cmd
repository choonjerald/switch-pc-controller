@echo off
setlocal
cd /d "%~dp0"
call launch.cmd --check
if not errorlevel 1 goto ready
where winget >nul 2>&1
if errorlevel 1 goto manual
echo Installing Python 3.13 for the current Windows user...
winget install --id Python.Python.3.13 --exact --source winget --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto manual
call launch.cmd --check
if errorlevel 1 goto manual
:ready
echo Setup complete. Double-click launch.cmd to start Switch PC Controller.
pause
exit /b 0
:manual
echo Install Python 3.10 or newer from https://www.python.org/downloads/windows/
echo Include Tcl/Tk and the Python launcher, then open setup.cmd again.
pause
exit /b 1
