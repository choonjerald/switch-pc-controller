@echo off
setlocal
cd /d "%~dp0"
set "python_exe="
set "python_args="
py -3 -c "import sys, tkinter; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    set "python_exe=py"
    set "python_args=-3"
)
if not defined python_exe call :try_python "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined python_exe call :try_python python
if /i "%~1"=="--check" (
    if defined python_exe exit /b 0
    exit /b 1
)
if not defined python_exe (
    echo Python with Tcl/Tk was not found. Double-click setup.cmd first.
    pause
    exit /b 1
)
"%python_exe%" %python_args% launch.py %*
set "result=%errorlevel%"
if not "%result%"=="0" pause
exit /b %result%

:try_python
"%~1" -c "import sys, tkinter; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 set "python_exe=%~1"
exit /b 0
