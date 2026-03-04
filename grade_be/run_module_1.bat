@echo off
echo Stopping any existing python processes...
taskkill /F /IM python.exe /T >nul 2>&1

echo Starting Module 1 Backend Server (Mini IDE Style)...
echo Access the API documentation at: http://127.0.0.1:8000/docs
echo.
cd /d "%~dp0"
.\venv\Scripts\python.exe -m uvicorn promptRightProd.asgi:application --reload --port 8000
pause
