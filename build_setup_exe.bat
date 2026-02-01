@echo off
REM Build script to create TradeLab-Setup.exe
REM This requires PyInstaller to be installed

echo ========================================
echo   Building TradeLab Setup Executable
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation!
    pause
    exit /b 1
)

REM Try to use python -m pip instead of pip directly (more reliable)
echo Checking Python installation...
python --version
echo.

REM Check if PyInstaller is installed
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    echo Using: python -m pip install pyinstaller
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install PyInstaller
        echo.
        echo Try installing manually:
        echo   python -m pip install pyinstaller
        echo.
        echo Or if you have multiple Python installations, try:
        echo   py -3 -m pip install pyinstaller
        pause
        exit /b 1
    )
    echo [OK] PyInstaller installed successfully
) else (
    echo [OK] PyInstaller already installed
)

REM Install setup script dependencies
echo.
echo Installing setup script dependencies...
python -m pip install -r setup_requirements.txt
if errorlevel 1 (
    echo [WARNING] Failed to install some dependencies
    echo Shortcut creation may not work, but setup will continue
    echo You can install manually: python -m pip install pywin32
)

echo.
echo Building executable...
echo.

REM Build the executable
REM Note: The executable should be placed in the project root directory
REM It will look for backend/ and frontend/ folders in the same directory
python -m PyInstaller --onefile ^
    --name "TradeLab-Setup" ^
    --console ^
    --icon "frontend\assets\icon.ico" ^
    --hidden-import win32timezone ^
    --hidden-import win32com.client ^
    setup.py

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to build executable
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Build Complete!
echo ========================================
echo.
echo The executable is located at:
echo   dist\TradeLab-Setup.exe
echo.
echo You can distribute this single .exe file to users.
echo They just need to:
echo   1. Place it in the TradeLab folder
echo   2. Double-click it to run setup
echo.
pause

