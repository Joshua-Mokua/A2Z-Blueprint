@echo off
title A2Z Blueprint MIS 360
cd /d "%~dp0"
call .venv\Scripts\activate.bat

echo.
echo  ================================================
echo   A2Z Blueprint MIS 360  ^|  v5.3
echo   Starting Streamlit + FastAPI
echo  ================================================
echo.

:: Start FastAPI in background
echo  Starting FastAPI backend on port 8502...
start "A2Z API" cmd /k ".venv\Scripts\activate.bat && python -m utils.api"

:: Wait 3 seconds for API to start
timeout /t 3 /nobreak > nul

:: Start Streamlit
echo  Starting Streamlit on port 8501...
echo  Open browser at: http://localhost:8501
echo.
streamlit run app.py --server.port 8501
pause
