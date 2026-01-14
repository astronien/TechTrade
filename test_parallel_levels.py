#!/usr/bin/env python3
"""
Find Optimal Parallelism - while maintaining 100% success
Test: 2, 3, 4 months parallel (with 60s timeout)
"""

import requests
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://report-trade.vercel.app"
API_ENDPOINT = f"{BASE_URL}/api/annual-report-data"
YEAR = 2025
BRANCH_ID = "231"
TIMEOUT = 60  # Fixed at 60s since that worked

def fetch_month(month, session_id):
    """Fetch single month with 60s timeout"""
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
        
        return {'month': month, 'success': False, 'time': elapsed, 'error': f"HTTP {response.status_code}"}
    except requests.exceptions.Timeout:
        return {'month': month, 'success': False, 'time': time.time() - start, 'error': 'Timeout'}
    except Exception as e:
        return {'month': month, 'success': False, 'time': time.time() - start, 'error': str(e)[:30]}

def test_parallel(session_id, parallel_count, delay_between):
    """Test with N months in parallel"""
    print(f"\n{'='*60}")
    print(f"🧪 Testing: {parallel_count} months parallel, {delay_between}s delay")
    print(f"{'='*60}")
    
    start_time = time.time()
    success_count = 0
    errors = []
    
    # Create batches
    all_months = list(range(1, 13))
    batches = []
    for i in range(0, 12, parallel_count):
        batches.append(all_months[i:i + parallel_count])
    
    print(f"   Batches: {batches}")
    
    for batch_idx, batch in enumerate(batches):
        print(f"\n  Batch {batch_idx+1}/{len(batches)} (months {batch}):")
        
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            futures = {executor.submit(fetch_month, m, session_id): m for m in batch}
            
            for future in as_completed(futures):
                result = future.result()
                month = result['month']
                if result['success']:
                    success_count += 1
                    print(f"    ✓ Month {month}: {result['time']:.1f}s")
                else:
                    errors.append(month)
                    print(f"    ✗ Month {month}: {result['error']}")
        
        # Delay between batches
        if batch_idx < len(batches) - 1:
            print(f"    [Delay {delay_between}s]")
            time.sleep(delay_between)
    
    total_time = time.time() - start_time
    success_rate = (success_count / 12) * 100
    
    print(f"\n{'='*60}")
    print(f"📊 Result: {success_count}/12 ({success_rate:.0f}%)")
    print(f"   Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
    if errors:
        print(f"   Failed months: {errors}")
    print(f"{'='*60}")
    
    return {
        'parallel': parallel_count,
        'delay': delay_between,
        'success_count': success_count,
        'success_rate': success_rate,
        'total_time': total_time,
        'errors': errors
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_parallel_levels.py <session_id>")
        return
    
    session_id = sys.argv[1]
    
    print("🔬 Finding Optimal Parallelism (with 60s timeout)")
    print("Branch: 231 (highest data volume)\n")
    
    # Test configurations: (parallel_count, delay_between_batches)
    configs = [
        (2, 3),   # 2 months parallel, 3s delay
        (3, 4),   # 3 months parallel, 4s delay
        (4, 5),   # 4 months parallel, 5s delay
    ]
    
    results = []
    best_fast_100 = None
    
    for parallel, delay in configs:
        result = test_parallel(session_id, parallel, delay)
        results.append(result)
        
        if result['success_rate'] == 100:
            if best_fast_100 is None or result['total_time'] < best_fast_100['total_time']:
                best_fast_100 = result
            print(f"\n✅ {parallel} parallel achieved 100%!")
        else:
            print(f"\n❌ {parallel} parallel failed ({result['success_rate']:.0f}%). Stopping here.")
            break
        
        print("\n⏳ Waiting 10s before next test...")
        time.sleep(10)
    
    # Summary
    print("\n" + "="*70)
    print("📊 FINAL SUMMARY")
    print("="*70)
    print(f"{'Parallel':<12} {'Delay':<10} {'Success':<12} {'Time':<12} {'Status'}")
    print("-"*70)
    
    for r in results:
        status = "✅ 100%" if r['success_rate'] == 100 else f"❌ {r['success_rate']:.0f}%"
        print(f"{r['parallel']:<12} {r['delay']}s{'':<7} {r['success_count']}/12{'':<6} {r['total_time']/60:.1f} min{'':<5} {status}")
    
    print("-"*70)
    
    if best_fast_100:
        print(f"\n🏆 BEST CONFIG (100% + fastest):")
        print(f"   {best_fast_100['parallel']} months parallel, {best_fast_100['delay']}s delay")
        print(f"   Time: {best_fast_100['total_time']/60:.1f} minutes")

if __name__ == "__main__":
    main()
