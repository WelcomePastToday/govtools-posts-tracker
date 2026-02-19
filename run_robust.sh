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
        # Exit code 0 means success
        caffeinate -i python tracker.py
        EXIT_CODE=$?
        
        if [ $EXIT_CODE -eq 0 ]; then
            echo "✅ Tracker processed list successfully!"
            
            # --- SYNC TO SERVER ---
            # Upload data to govtools.org so it can be visualized
            if command -v rsync &> /dev/null; then
                echo "Syncing data to server..."
                # Sync data/ folder to server. 
                # Preserves timestamps (-t), recursive (-r), compress (-z), verbose (-v), display progress (--progress)
                # Using --update to only copy newer files
                # TARGET PATH: Relative to home dir (which is mapped correctly for Caddy)
                rsync -rtzv --update --progress ./data/ deploy@govtools.org:govtools-posts-tracker/data/
                if [ $? -eq 0 ]; then
                    echo "Data sync complete."
                else
                    echo "Data sync failed (rsync error)."
                fi
            else
                echo "rsync not found, skipping upload."
            fi
            # -----------------------

            # Reset fail count on success
            FAIL_COUNT=0
            
            # Sleep until next scheduled run (e.g. daily run logic handled inside python script? No, external loop handles it)
            # Tracker.py only runs once through list.
            # If we want continuous loop, we should sleep for X hours.
            # But the user might be running this via launchd now? 
            # If launchd runs this script, and this script loops forever, that's fine.
            # Assuming 'Success' means 'Done for now'.
            
            # Let's wait 6 hours before next pass if success
            echo "Sleeping for 6 hours..."
            sleep 21600
            continue 
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
