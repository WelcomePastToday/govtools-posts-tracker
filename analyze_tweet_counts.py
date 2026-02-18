import csv
from collections import defaultdict
from datetime import datetime
import re

LOG_PATH = "data/master_log.csv"

def parse_count(count_str):
    if not count_str:
        return 0
    # Remove commas
    clean_str = count_str.replace(",", "")
    # specialized handling 10k, 1M, etc? 
    # The logs usually show exact numbers or "1,234".
    # Sometimes it might be empty.
    try:
        return int(clean_str)
    except ValueError:
        return 0

def main():
    # Dictionary to store list of (timestamp, count) for each handle
    handle_data = defaultdict(list)
    
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            # It's not a standard CSV, it uses ;;; separator
            lines = f.readlines()
    except FileNotFoundError:
        print(f"File {LOG_PATH} not found.")
        return

    header_skipped = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        parts = line.split(";;;")
            
        # Check if it looks like a header line (repeated headers in append log?)
        if len(parts) > 4 and ("timestamp_utc" in parts[0] or "posts_count" in parts[4]):
            continue
            
        if len(parts) >= 6:
            ts_str = parts[0].strip()
            handle = parts[1].strip()
            count_str = parts[4].strip()
            
            # If count is empty, skip this entry as invalid data point
            if not count_str:
                continue
                
            count = parse_count(count_str)
            
            handle_data[handle].append((ts_str, count))

    print(f"{'Handle':<30} | {'First Count':<12} | {'Last Count':<12} | {'Diff':<10}")
    print("-" * 75)
    
    total_diff = 0
    decreased_count = 0
    
    sorted_handles = sorted(handle_data.keys(), key=lambda x: x.lower())
    
    for handle in sorted_handles:
        entries = handle_data[handle]
        if not entries:
            continue
            
        # Sort by timestamp to be sure (simple string sort works for ISO format)
        entries.sort(key=lambda x: x[0])
        
        first_entry = entries[0]
        last_entry = entries[-1]
        
        first_count = first_entry[1]
        last_count = last_entry[1]
        
        diff = last_count - first_count
        
        if diff != 0:
             print(f"{handle:<30} | {first_count:<12} | {last_count:<12} | {diff:<10}")
        
        total_diff += diff
        # If diff is negative (less tweets now than before), count it
        if diff < 0:
             decreased_count += 1

    print("-" * 75)
    print(f"Total Net Change in Tweets: {total_diff}")
    print(f"Number of accounts with fewer tweets: {decreased_count}")
    print(f"Data Source: {LOG_PATH}")

if __name__ == "__main__":
    main()
