#!/bin/bash
# ==========================================
# Todo App Startup Script for Unix/Linux/Mac
# ==========================================
# This script starts both the backend (FastAPI) and frontend (React/Vite) servers.

set -e

echo "Starting Todo App..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Please install Python 3.8+ from https://www.python.org/downloads/"
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js is not installed."
    echo "Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi

echo "[1/4] Installing backend dependencies..."
cd backend
pip3 install -r requirements.txt
cd ..

echo "[2/4] Installing frontend dependencies..."
cd frontend
npm install
cd ..

echo "[3/4] Starting backend server (FastAPI)..."
cd backend
python3 main.py &
BACKEND_PID=$!
cd ..

echo "Waiting for backend to initialize..."
sleep 3

echo "[4/4] Starting frontend server (Vite)..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "=========================================="
echo "Todo App is running!"
echo "=========================================="
echo ""
echo "Backend API:  http://localhost:8000"
echo "API Docs:     http://localhost:8000/docs"
echo "Frontend:     http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all servers..."
echo "=========================================="

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down servers..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

# Trap Ctrl+C
trap cleanup SIGINT SIGTERM

# Wait for processes
wait
