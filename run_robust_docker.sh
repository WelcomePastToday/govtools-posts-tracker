#!/bin/bash

# Navigate to script directory
cd "$(dirname "$0")"

echo "Starting Robust Tracker with Smart Backoff (Docker Version)..."

FAIL_COUNT=0

while true; do
    echo "[$(date '+%H:%M:%S')] Launching tracker in Docker..."
    
    # Run the tracker via Docker Compose
    # --rm cleans up container after exit to save space
    docker compose run --rm tracker
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ Tracker finished successfully!"
        exit 0
    fi
    
    echo "⚠️ Tracker exited with error code $EXIT_CODE."

    # If we are here, something failed (no net or script crash)
    FAIL_COUNT=$((FAIL_COUNT + 1))
    
    # Calculate backoff strategy:
    # 1. First 3 attempts: 60s intervals
    # 2. Next 3 attempts: 10 min intervals
    # 3. Then: 1 hour intervals
    
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
