#!/usr/bin/env python3
"""
Final Verification: 3 Branches Parallel
Each branch fetches all 12 months (using 3-month batches)
"""

import requests
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://report-trade.vercel.app"
API_ENDPOINT = f"{BASE_URL}/api/annual-report-data"
YEAR = 2025
BRANCH_ID = "231"
TIMEOUT = 60
MONTH_PARALLEL = 3  # Internal parallelism per branch
MONTH_DELAY = 4     # Delay between internal batches

# Simulate 3 different branches (using same ID for load testing)
BRANCHES = ["231 (Sim A)", "231 (Sim B)", "231 (Sim C)"]

def fetch_month(month, session_id, branch_name):
    """Fetch single month"""
    params = {
        'year': YEAR,
        'month': month,
        'branchId': BRANCH_ID,
        'sessionId': session_id
    }
    
    start = time.time()
    try:
        response = requests.get(API_ENDPOINT, params=params, timeout=TIMEOUT)
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"    ✓ {branch_name} Month {month}: {elapsed:.1f}s")
                return True
        print(f"    ✗ {branch_name} Month {month}: Failed")
        return False
    except Exception as e:
        print(f"    ✗ {branch_name} Month {month}: Error {str(e)[:20]}")
        return False

def process_branch(branch_name, session_id):
    """Process one full branch (12 months)"""
    print(f"🚀 Starting {branch_name}...")
    
    batches = [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]]
    success_count = 0
    
    for batch in batches:
        with ThreadPoolExecutor(max_workers=MONTH_PARALLEL) as executor:
            futures = {executor.submit(fetch_month, m, session_id, branch_name): m for m in batch}
            for future in as_completed(futures):
                if future.result():
                    success_count += 1
        
        time.sleep(MONTH_DELAY)
    
    print(f"🏁 Finished {branch_name}: {success_count}/12")
    return success_count

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 verify_final.py <session_id>")
        return
    
    session_id = sys.argv[1]
    
    print(f"🔬 Final Verification: 3 Branches Running Parallel")
    print(f"   (Max concurrent requests: {3 * MONTH_PARALLEL})")
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_branch, b, session_id): b for b in BRANCHES}
        
        results = []
        for future in as_completed(futures):
            results.append(future.result())
    
    total_time = time.time() - start_time
    total_success = sum(results)
    
    print(f"\n" + "="*50)
    print(f"📊 Final Result: {total_success}/{3*12} ({total_success/(3*12)*100:.0f}%)")
    print(f"   Total Time: {total_time:.1f}s ({total_time/60:.1f} min)")
    print("="*50)

if __name__ == "__main__":
    main()
