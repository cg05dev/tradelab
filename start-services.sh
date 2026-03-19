#!/bin/bash
# Start backend in background
cd /home/christian/dev/tradelab/backend
source venv/bin/activate
nohup python main.py > ../backend_startup.log 2>&1 &
BACKEND_PID=$!
echo "Backend started with PID $BACKEND_PID"

# Wait for backend to be ready
ATTEMPTS=0
until curl -s http://localhost:8000/api/portfolio > /dev/null || [ $ATTEMPTS -eq 20 ]; do
    echo "Waiting for backend..."
    sleep 2
    ATTEMPTS=$((ATTEMPTS+1))
done

# Start frontend in background
cd /home/christian/dev/tradelab/frontend
nohup npm run dev > ../frontend_startup.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend started with PID $FRONTEND_PID"

# Save PIDs for later
echo "BACKEND_PID=$BACKEND_PID" > /tmp/service_pids
echo "FRONTEND_PID=$FRONTEND_PID" >> /tmp/service_pids
