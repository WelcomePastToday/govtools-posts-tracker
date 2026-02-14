#!/bin/bash

# Navigate to script directory
cd "$(dirname "$0")"

# Activate virtual environment
source venv/bin/activate

echo "Starting Robust Tracker with Smart Backoff..."
echo "Computer will be kept awake using 'caffeinate' to prevent sleep."

FAIL_COUNT=0

while true; do
    # Check internet connection first (using Google DNS as reliable target)
    if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
        echo "[$(date '+%H:%M:%S')] Network UP. Launching tracker..."
        
        # Run the tracker; caffeinate -i prevents idle sleep
        caffeinate -i python tracker.py
        EXIT_CODE=$?
        
        if [ $EXIT_CODE -eq 0 ]; then
            echo "✅ Tracker finished full list successfully!"
            exit 0
        fi
        
        echo "⚠️ Tracker exited with error code $EXIT_CODE."
    else
        echo "[$(date '+%H:%M:%S')] ⚠️ No internet connection detected."
    fi

    # If we are here, something failed (no net or script crash)
    FAIL_COUNT=$((FAIL_COUNT + 1))
    
    # Calculate backoff strategy based on user request:
    # 1. First 3 mins: 60s intervals (Attributes 1-3)
    # 2. Next 3 times: 10 min intervals (Attempts 4-6)
    # 3. Then: 1 hour intervals (Attempts 7+)
    
    if [ $FAIL_COUNT -le 3 ]; then
        SLEEP_SEC=60
        STRATEGY="Short retry"
    elif [ $FAIL_COUNT -le 6 ]; then
        SLEEP_SEC=600
        STRATEGY="Medium retry (10m)"
    else
        SLEEP_SEC=3600
        STRATEGY="Long retry (1h)"
    fi
    
    echo "Failure #$FAIL_COUNT. Strategy: $STRATEGY. Waiting ${SLEEP_SEC}s..."
    sleep $SLEEP_SEC
done
