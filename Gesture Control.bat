@echo off
title Gesture Control
cd /d "%~dp0"

rem First run only: create the virtual environment and install packages
if not exist ".venv\Scripts\python.exe" (
    echo Setting up for the first time, this takes a few minutes...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo Python was not found. Install Python 3.12 from python.org
        echo and tick "Add python.exe to PATH" during install.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

".venv\Scripts\python.exe" main.py %*

rem keep the window open if something went wrong, so you can read the error
if errorlevel 1 pause
