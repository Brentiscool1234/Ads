@echo off
REM LocalAds Manager - one-click setup and launch for Windows.
REM Creates an isolated virtual environment, installs dependencies,
REM and starts the dashboard. Safe to run more than once.

cd /d "%~dp0"
echo.
echo ===============================================
echo   LocalAds Manager - setup
echo ===============================================
echo.

REM --- Warn about the stray-file problem that breaks pip on some installs ---
if exist "%LOCALAPPDATA%\Programs\Python\Python310\google.py" (
    echo WARNING: found a stray file that will break pip:
    echo   %LOCALAPPDATA%\Programs\Python\Python310\google.py
    echo.
    echo Rename it first, then run this script again:
    echo   ren "%LOCALAPPDATA%\Programs\Python\Python310\google.py" google_stray.py.bak
    echo.
    pause
    exit /b 1
)

REM --- Locate Python. The "py" launcher avoids the Microsoft Store alias ---
REM --- that hijacks the bare "python" command on many Windows machines.  ---
where py >nul 2>&1
if %errorlevel%==0 (
    set PYRUN=py -3
) else (
    set PYRUN=python
)

%PYRUN% -V >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found.
    echo.
    echo Install Python 3.10 or newer from https://www.python.org/downloads/
    echo During install, tick "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo Using Python:
%PYRUN% -V
echo.

REM --- Create the virtual environment if it isn't there yet ---
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYRUN% -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: could not create the virtual environment.
        pause
        exit /b 1
    )
)

REM --- Install into the venv by full path, so no PATH or alias issues ---
echo Installing dependencies. This takes a minute the first time...
echo.
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: installing dependencies failed. See the message above.
    pause
    exit /b 1
)

echo.
echo ===============================================
echo   Starting at http://localhost:8000
echo   Close this window or press Ctrl+C to stop.
echo ===============================================
echo.

start "" http://localhost:8000
".venv\Scripts\python.exe" -m uvicorn app.main:app
pause
