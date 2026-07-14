@echo off
rem Portable launcher for OpenMarket Desktop (alpha).
rem Double-click this, or the desktop shortcut. On first run it sets up a local
rem Python environment inside this folder; after that it just launches the GUI.
rem The whole folder is self-contained -- copy it anywhere with Python 3 installed.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo First run: creating local Python environment...
  where py >nul 2>nul && ( py -3 -m venv .venv ) || ( python -m venv .venv )
  if not exist ".venv\Scripts\pythonw.exe" (
    echo.
    echo Could not create a virtual environment. Install Python 3 from python.org
    echo ^(check "Add python.exe to PATH"^) and run this again.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

start "" ".venv\Scripts\pythonw.exe" "%~dp0gui.py"
endlocal
