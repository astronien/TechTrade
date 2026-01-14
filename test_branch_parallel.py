#!/usr/bin/env python3
"""
Test branch-level parallelism
Simulate running 2, 3, 4 branches at the same time
Each branch uses 3-month parallel (best config from previous test)
"""

import requests
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://report-trade.vercel.app"
API_ENDPOINT = f"{BASE_URL}/api/annual-report-data"
YEAR = 2025
BRANCH_ID = "231"  # ใช้สาขาเดียวกันแต่ยิงพร้อมกันเพื่อจำลองโหลด
TIMEOUT = 60
MONTH_PARALLEL = 3
MONTH_DELAY = 4

def fetch_month(month, session_id, branch_sim_id):
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
                return {'month': month, 'branch': branch_sim_id, 'success': True, 'time': elapsed}
        
        return {'month': month, 'branch': branch_sim_id, 'success': False, 'time': elapsed}
    except:
        return {'month': month, 'branch': branch_sim_id, 'success': False, 'time': time.time() - start}

def simulate_branch(session_id, branch_sim_id):
    """Simulate one branch fetching all 12 months (3 parallel)"""
    batches = [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]]
    success_count = 0
    
    for batch in batches:
        with ThreadPoolExecutor(max_workers=MONTH_PARALLEL) as executor:
            futures = {executor.submit(fetch_month, m, session_id, branch_sim_id): m for m in batch}
            for future in as_completed(futures):
                result = future.result()
                if result['success']:
                    success_count += 1
        
        time.sleep(MONTH_DELAY)
    
    return {'branch': branch_sim_id, 'success': success_count}

def test_branch_parallel(session_id, num_branches):
    """Test running N branches in parallel"""
    print(f"\n{'='*60}")
    print(f"🧪 Testing: {num_branches} branches parallel (each with 3 months)")
    print(f"   Max concurrent requests: {num_branches * MONTH_PARALLEL}")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=num_branches) as executor:
        futures = {executor.submit(simulate_branch, session_id, f"B{i+1}"): i for i in range(num_branches)}
        
        results = []
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = "✅" if result['success'] == 12 else f"⚠️ {result['success']}/12"
            print(f"   {result['branch']}: {status}")
    
    total_time = time.time() - start_time
    total_success = sum(r['success'] for r in results)
    total_possible = num_branches * 12
    success_rate = (total_success / total_possible) * 100
    perfect_branches = sum(1 for r in results if r['success'] == 12)
    
    print(f"\n📊 Result: {total_success}/{total_possible} ({success_rate:.0f}%)")
    print(f"   Perfect branches: {perfect_branches}/{num_branches}")
    print(f"   Time: {total_time:.1f}s ({total_time/60:.1f} min)")
    
    return {
        'num_branches': num_branches,
        'success': total_success,
        'total': total_possible,
        'success_rate': success_rate,
        'perfect_branches': perfect_branches,
        'time': total_time
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_branch_parallel.py <session_id>")
        return
    
    session_id = sys.argv[1]
    
    print("🔬 Branch-Level Parallelism Test")
    print("Each branch: 3 months parallel, 60s timeout, 4s delay")
    print(f"Branch: {BRANCH_ID} (simulated multiple times)\n")
    
    configs = [2, 3, 4]  # Test 2, 3, 4 branches parallel
    results = []
    
    for num_branches in configs:
        result = test_branch_parallel(session_id, num_branches)
        results.append(result)
        
        if num_branches < max(configs):
            print("\n⏳ Waiting 15s before next test...")
            time.sleep(15)
    
    # Summary
    print("\n" + "="*70)
    print("📊 FINAL SUMMARY")
    print("="*70)
    print(f"{'Branches':<12} {'Concurrent':<12} {'Success':<15} {'Time':<12} {'Status'}")
    print("-"*70)
    
    for r in results:
        concurrent = r['num_branches'] * MONTH_PARALLEL
        status = "✅ 100%" if r['success_rate'] == 100 else f"❌ {r['success_rate']:.0f}%"
        print(f"{r['num_branches']:<12} {concurrent:<12} {r['success']}/{r['total']}{'':<7} {r['time']/60:.1f} min{'':<5} {status}")
    
    print("-"*70)
    
    # Find best 100%
    perfect = [r for r in results if r['success_rate'] == 100]
    if perfect:
        best = max(perfect, key=lambda x: x['num_branches'])
        print(f"\n🏆 BEST CONFIG (100% + most parallel):")
        print(f"   {best['num_branches']} branches parallel")
        print(f"   Time: {best['time']/60:.1f} minutes")
    else:
        print("\n⚠️ No config achieved 100%. Recommend using 1 branch at a time.")

if __name__ == "__main__":
    main()
