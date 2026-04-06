@echo off
REM Windows setup script for Hijab by Copilot

echo ============================================================
echo Hijab by Copilot - Windows Setup
echo ============================================================
echo.

REM Check Python installation
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH!
    echo.
    echo Please install Python 3.8 or higher from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

python --version
echo Python found!
echo.

REM Create virtual environment
if exist "venv\" (
    echo Virtual environment already exists.
    echo.
    choice /C YN /M "Do you want to recreate it"
    if errorlevel 2 goto skip_venv
    echo Removing old virtual environment...
    rmdir /s /q venv
)

echo Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment!
    pause
    exit /b 1
)

:skip_venv
echo.

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment!
    pause
    exit /b 1
)

REM Upgrade pip
echo.
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install requirements
echo.
echo Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies!
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Setup complete!
echo ============================================================
echo.
echo You can now run the application using:
echo   run_windows.bat
echo.
echo Or manually:
echo   venv\Scripts\activate
echo   python main.py
echo.
pause
