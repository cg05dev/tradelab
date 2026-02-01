@echo off
REM This batch file can be run hidden or visible
REM When run hidden, errors will show in message boxes
setlocal enabledelayedexpansion

REM Get script directory
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    REM Show error in a message box since window is hidden
    mshta vbscript:Execute("msgbox ""Node.js is not installed or not in PATH. Please install Node.js from https://nodejs.org/"", 16, ""TradeLab Error"")(window.close)")
    exit /b 1
)

REM Check if frontend directory exists
if not exist "%SCRIPT_DIR%\frontend" (
    mshta vbscript:Execute("msgbox ""Frontend directory not found! Expected: %SCRIPT_DIR%\frontend"", 16, ""TradeLab Error"")(window.close)")
    exit /b 1
)

REM Check if Electron dependencies are installed
cd /d "%SCRIPT_DIR%\frontend"
if errorlevel 1 (
    mshta vbscript:Execute("msgbox ""Failed to change to frontend directory!"", 16, ""TradeLab Error"")(window.close)")
    exit /b 1
)

if not exist "node_modules\electron" (
    REM Install dependencies silently
    call npm install >nul 2>&1
    if errorlevel 1 (
        mshta vbscript:Execute("msgbox ""Failed to install Electron dependencies. Please run: cd frontend && npm install"", 16, ""TradeLab Error"")(window.close)")
        exit /b 1
    )
)

REM Check if Python is available (for backend) - just check, don't error
python --version >nul 2>&1

REM Start Electron app
cd /d "%SCRIPT_DIR%\frontend"
npm run electron:dev

set "EXIT_CODE=%ERRORLEVEL%"

REM Exit immediately when Electron closes (no pause)
REM This allows the PowerShell window to close automatically
exit /b %EXIT_CODE%

