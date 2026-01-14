#!/usr/bin/env python3
"""
Validate 3-month parallel config by running 3 times
Calculate average time and win rate
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
PARALLEL = 3
DELAY = 4

def fetch_month(month, session_id):
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
                return {'month': month, 'success': True, 'time': elapsed}
        
        return {'month': month, 'success': False, 'time': elapsed}
    except:
        return {'month': month, 'success': False, 'time': time.time() - start}

def run_single_test(session_id, run_number):
    """Run one complete test"""
    print(f"\n{'='*60}")
    print(f"🔄 RUN {run_number}/3")
    print(f"{'='*60}")
    
    start_time = time.time()
    success_count = 0
    
    batches = [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]]
    
    for batch_idx, batch in enumerate(batches):
        print(f"\n  Batch {batch_idx+1}/4 (months {batch}):", end=" ", flush=True)
        
        with ThreadPoolExecutor(max_workers=PARALLEL) as executor:
            futures = {executor.submit(fetch_month, m, session_id): m for m in batch}
            batch_results = []
            
            for future in as_completed(futures):
                result = future.result()
                if result['success']:
                    success_count += 1
                    batch_results.append(f"✓{result['month']}")
                else:
                    batch_results.append(f"✗{result['month']}")
            
            print(" ".join(batch_results))
        
        if batch_idx < len(batches) - 1:
            time.sleep(DELAY)
    
    total_time = time.time() - start_time
    success_rate = (success_count / 12) * 100
    
    print(f"\n  Result: {success_count}/12 ({success_rate:.0f}%) in {total_time:.1f}s")
    
    return {
        'run': run_number,
        'success_count': success_count,
        'success_rate': success_rate,
        'time': total_time
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_3runs.py <session_id>")
        return
    
    session_id = sys.argv[1]
    
    print("🔬 3-Month Parallel Validation (3 runs)")
    print(f"Config: {PARALLEL} parallel, {TIMEOUT}s timeout, {DELAY}s delay")
    print(f"Branch: {BRANCH_ID}")
    
    results = []
    
    for run in range(1, 4):
        result = run_single_test(session_id, run)
        results.append(result)
        
        if run < 3:
            print("\n⏳ Waiting 15s before next run...")
            time.sleep(15)
    
    # Calculate statistics
    total_months = sum(r['success_count'] for r in results)
    total_possible = 12 * 3
    overall_winrate = (total_months / total_possible) * 100
    avg_time = sum(r['time'] for r in results) / 3
    
    runs_100 = sum(1 for r in results if r['success_rate'] == 100)
    
    # Summary
    print("\n" + "="*60)
    print("📊 FINAL STATISTICS (3 runs)")
    print("="*60)
    print(f"{'Run':<10} {'Success':<15} {'Time':<15}")
    print("-"*60)
    
    for r in results:
        status = "✅" if r['success_rate'] == 100 else "⚠️"
        print(f"Run {r['run']:<6} {r['success_count']}/12 ({r['success_rate']:.0f}%){'':<3} {r['time']:.1f}s {status}")
    
    print("-"*60)
    print(f"\n🎯 OVERALL STATS:")
    print(f"   Total Success: {total_months}/{total_possible} months")
    print(f"   Win Rate: {overall_winrate:.1f}%")
    print(f"   100% Runs: {runs_100}/3")
    print(f"   Average Time: {avg_time:.1f}s ({avg_time/60:.1f} min)")

if __name__ == "__main__":
    main()
