@echo off
REM ==========================================
REM Todo App Startup Script for Windows
REM ==========================================
REM This script starts both the backend (FastAPI) and frontend (React/Vite) servers.

echo Starting Todo App...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed or not in PATH.
    echo Please install Node.js 18+ from https://nodejs.org/
    pause
    exit /b 1
)

echo [1/4] Installing backend dependencies...
cd backend
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install backend dependencies.
    pause
    exit /b 1
)
cd ..

echo [2/4] Installing frontend dependencies...
cd frontend
call npm install
if errorlevel 1 (
    echo ERROR: Failed to install frontend dependencies.
    pause
    exit /b 1
)
cd ..

echo [3/4] Starting backend server (FastAPI)...
start "Todo Backend - FastAPI" cmd /k "cd backend && python main.py"

echo Waiting for backend to initialize...
timeout /t 3 /nobreak >nul

echo [4/4] Starting frontend server (Vite)...
start "Todo Frontend - React" cmd /k "cd frontend && npm run dev"

echo.
echo ==========================================
echo Todo App is starting!
echo ==========================================
echo.
echo Backend API:  http://localhost:8000
echo API Docs:     http://localhost:8000/docs
echo Frontend:     http://localhost:5173
echo.
echo The app will open in your browser shortly...
echo Close this window to stop the servers.
echo ==========================================

REM Wait a bit then open browser
timeout /t 5 /nobreak >nul
start http://localhost:5173

pause
