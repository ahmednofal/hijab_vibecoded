@echo off
REM Windows launcher for Hijab by Copilot

echo ============================================================
echo Hijab by Copilot - Windows Launcher
echo ============================================================
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo Virtual environment not found!
    echo.
    echo Please run setup_windows.bat first to install dependencies.
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if activated
if errorlevel 1 (
    echo Failed to activate virtual environment!
    pause
    exit /b 1
)

echo Virtual environment activated.
echo.

REM Run the application in test mode (red rectangle, no segmentation)
echo Starting Hijab by Copilot (TEST MODE)...
echo Press Ctrl+C to exit.
echo.
python main.py --test

REM Deactivate when done
deactivate
