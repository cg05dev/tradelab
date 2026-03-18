#!/bin/bash
set -e

echo "=== TradeLab Mission Init ==="

# Install frontend dependencies if needed
if [ ! -d "frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  cd frontend && npm install && cd ..
fi

# Verify backend dependencies (Python assumes venv or system install)
echo "Backend uses Python with requirements in backend/requirements.txt"
echo "Ensure you have activated your virtual environment if using one."

echo "=== Init complete ==="
