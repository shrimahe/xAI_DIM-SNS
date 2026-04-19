#!/bin/bash

echo "========================================"
echo "   Starting XAI Apartment Safety System"
echo "========================================"

BASE_DIR=$(pwd)

# -------------------------------
# 1. Start Mosquitto
# -------------------------------
echo "[1/6] Checking Mosquitto..."
if ! systemctl is-active --quiet mosquitto; then
    echo "Starting Mosquitto..."
    sudo systemctl start mosquitto
else
    echo "Mosquitto already running"
fi

# -------------------------------
# 2. Start Ollama Server
# -------------------------------
echo "[2/6] Starting Ollama server..."
if ! pgrep -f "ollama serve" > /dev/null; then
    ollama serve > logs/ollama.log 2>&1 &
    sleep 3
    echo "Ollama server started"
else
    echo "Ollama server already running"
fi

# -------------------------------
# 3. Ensure llama3.2 Model
# -------------------------------
echo "[3/6] Checking llama3.2 model..."
if ! ollama list | grep -q "llama3.2"; then
    echo "Pulling llama3.2 model..."
    ollama pull llama3.2
else
    echo "llama3.2 model ready"
fi

# -------------------------------
# 4. Start Node-RED
# -------------------------------
echo "[4/6] Starting Node-RED..."
if ! pgrep -f "node-red" > /dev/null; then
    node-red > logs/node-red.log 2>&1 &
    sleep 5
    echo "Node-RED started"
else
    echo "Node-RED already running"
fi

# -------------------------------
# 5. Start Python XAI System
# -------------------------------
echo "[5/6] Starting Python XAI system..."
python central_system/main.py > logs/xai_system.log 2>&1 &
sleep 3
echo "Python XAI system running"

# -------------------------------
# 6. Apartment Score Scheduler
# -------------------------------
echo "[6/6] Starting Apartment Score Scheduler (hourly)..."

(
while true; do
    echo "[Apartment Score] Updating scores at $(date)" >> logs/apartment_score.log
    python central_system/apartment_score.py >> logs/apartment_score.log 2>&1
    sleep 3600   # 1 hour
done
) &

echo "========================================"
echo "   System started successfully!"
echo "========================================"
echo "Logs:"
echo " - Ollama: logs/ollama.log"
echo " - Node-RED: logs/node-red.log"
echo " - XAI System: logs/xai_system.log"
echo " - Apartment Scores: logs/apartment_score.log"
echo ""
echo "Dashboard:"
echo " - Node-RED UI: http://localhost:1880/ui"
