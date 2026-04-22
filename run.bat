@echo off
title A2Z Blueprint — MIS 360
cd /d "%~dp0"

echo.
echo  ================================================
echo   A2Z Blueprint MIS 360  ^|  v5.2
echo  ================================================
echo.

:: Check if virtual environment exists
if not exist ".venv\Scripts\activate.bat" (
    echo  Setting up virtual environment for the first time...
    python -m venv .venv
    echo  Installing packages...
    .venv\Scripts\pip install -q streamlit pandas numpy plotly openpyxl requests bcrypt
    echo  Done.
    echo.
)

:: Activate and run
call .venv\Scripts\activate.bat
echo  Starting A2Z Blueprint...
echo  Open your browser at: http://localhost:8501
echo  Press Ctrl+C to stop.
echo.
streamlit run app.py --server.port 8501 --server.headless false
pause
