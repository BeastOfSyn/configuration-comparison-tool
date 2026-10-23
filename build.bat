@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   Configuration Comparison Tool - EXE Builder
echo ============================================================
echo.

rem --- Locate a working Python (prefer "python", fall back to the "py" launcher and standard paths) ---
set "PYCMD="
where python >nul 2>nul
if not errorlevel 1 set "PYCMD=python"

if not defined PYCMD (
    where py >nul 2>nul
    if not errorlevel 1 set "PYCMD=py -3"
)

if not defined PYCMD (
    for /d %%I in ("%APPDATA%\uv\python\cpython-3.12*") do (
        if exist "%%I\python.exe" set "PYCMD=%%I\python.exe"
    )
)
if not defined PYCMD (
    for /d %%I in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%I\python.exe" set "PYCMD=%%I\python.exe"
    )
)

if not defined PYCMD (
    echo ERROR: Python was not found on PATH.
    echo Install Python 3.10 or newer from https://www.python.org/downloads/
    echo During setup, check the box "Add python.exe to PATH", then re-run this script.
    echo.
    pause
    exit /b 1
)

echo [1/6] Using: %PYCMD%
%PYCMD% --version

echo.
echo [2/6] Creating isolated build environment (.buildenv)...
if not exist ".buildenv" (
    %PYCMD% -m venv .buildenv
    if errorlevel 1 (
        echo ERROR: Failed to create the virtual environment.
        pause
        exit /b 1
    )
)
call ".buildenv\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Failed to activate the virtual environment.
    pause
    exit /b 1
)

echo.
echo [3/6] Upgrading pip...
python -m pip install --upgrade pip

echo.
echo [4/6] Installing project dependencies + PyInstaller...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install requirements.txt.
    pause
    exit /b 1
)
python -m pip install pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
    pause
    exit /b 1
)

echo.
echo [5/7] Verifying build integrity and signature...
python validate_build.py
if errorlevel 1 (
    echo ERROR: Build validation failed - see message above.
    pause
    exit /b 1
)

echo.
echo [6/7] Cleaning previous build artifacts...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo.
echo [7/7] Building the EXE with PyInstaller...
python -m PyInstaller --clean --noconfirm PMR_Comparison.spec
if errorlevel 1 (
    echo.
    echo ============================================================
    echo   BUILD FAILED - scroll up to see the PyInstaller error.
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   BUILD COMPLETE
echo   EXE location: dist\Configuration_Comparison_Tool.exe
============================================================
echo.
if exist "dist\Configuration_Comparison_Tool.exe" explorer "dist"
pause
