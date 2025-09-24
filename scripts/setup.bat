@echo off
REM ScreenTranslate-AI Environment Setup Script (Windows)
REM Check Python version, create virtual environment, install dependencies

echo ========================================
echo ScreenTranslate-AI Environment Setup
echo ========================================

REM 自动切换到脚本所在目录的上级目录（项目根目录）
cd /d "%~dp0\.."

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not installed or not in PATH
    echo Please install Python 3.8+: https://python.org/downloads/
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo [INFO] Detected Python version: %PYTHON_VERSION%

REM Check if Python version meets requirements (3.8+)
python -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"
if %errorlevel% neq 0 (
    echo [ERROR] Python version too low, need Python 3.8+
    echo Current version: %PYTHON_VERSION%
    pause
    exit /b 1
)

echo [INFO] Python version check passed

REM Check if in project root directory
if not exist "requirements.txt" (
    echo [ERROR] 未找到 requirements.txt 文件
    echo 请确保脚本位于项目的 scripts 目录中
    echo 当前目录: %CD%
    pause
    exit /b 1
)

REM Check if virtual environment already exists
if exist ".venv" (
    echo [INFO] Virtual environment already exists, skipping creation
) else (
    echo [INFO] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [SUCCESS] Virtual environment created
)

REM Activate virtual environment
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

REM Upgrade pip
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip
if %errorlevel% neq 0 (
    echo [WARNING] pip upgrade failed, continuing with dependency installation...
)

REM Install dependencies
echo [INFO] Installing project dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Dependencies installation failed
    echo Please check network connection and requirements.txt file
    pause
    exit /b 1
)

echo [SUCCESS] Dependencies installed

REM Install PyInstaller for packaging
echo [INFO] Installing PyInstaller...
pip install pyinstaller
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller installation failed
    pause
    exit /b 1
)

echo [SUCCESS] PyInstaller installed

REM Verify installation
echo [INFO] Verifying installation...

python -c "import PyQt6" >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] Dependency verification failed: PyQt6 not found! && pause && exit /b 1 )
python -c "import easyocr" >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] Dependency verification failed: easyocr not found! && pause && exit /b 1 )
python -c "import httpx" >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] Dependency verification failed: httpx not found! && pause && exit /b 1 )
python -c "import mss" >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] Dependency verification failed: mss not found! && pause && exit /b 1 )
python -c "import pynput" >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] Dependency verification failed: pynput not found! && pause && exit /b 1 )

echo [SUCCESS] All dependencies verified

echo ========================================
echo Environment setup completed!
echo ========================================
echo.
echo Next steps:
echo 1. Run scripts\build.bat to package the application
echo 2. Or run python main.py to start the program directly
echo.
echo Note: Before running the program each time, activate the virtual environment:
echo call .venv\Scripts\activate.bat
echo.
pause
