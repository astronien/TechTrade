#!/usr/bin/env python3
"""
Benchmark script to test different fetching strategies for Zone Annual Reports.
Tests against Zone "APP" with different concurrency configurations.

Usage: python3 benchmark_options.py <session_id>
"""

import requests
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
BASE_URL = "https://report-trade.vercel.app"
API_ENDPOINT = f"{BASE_URL}/api/annual-report-data"
YEAR = 2025

# Zone APP - ทดสอบเฉพาะสาขา 231 (ข้อมูลเยอะสุด)
ZONE_APP_BRANCHES = ["231"]

def fetch_month_data(branch_id, month, session_id, timeout=30):
    """Fetch data for a single month"""
    params = {
        'year': YEAR,
        'month': month,
        'branchId': branch_id,
        'sessionId': session_id
    }
    
    start = time.time()
    try:
        response = requests.get(API_ENDPOINT, params=params, timeout=timeout)
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                return {'success': True, 'time': elapsed, 'records': data.get('total_records', 0)}
            return {'success': False, 'time': elapsed, 'error': data.get('error', 'Unknown')}
        
        return {'success': False, 'time': elapsed, 'error': f"HTTP {response.status_code}"}
    except requests.exceptions.Timeout:
        return {'success': False, 'time': time.time() - start, 'error': 'Timeout'}
    except Exception as e:
        return {'success': False, 'time': time.time() - start, 'error': str(e)[:50]}

def benchmark_option_a(branches, session_id):
    """Option A: Fully Sequential"""
    print("\n" + "="*60)
    print("🐢 Option A: Sequential (1 branch, 1 month)")
    print("="*60)
    
    start_time = time.time()
    success_count = 0
    error_count = 0
    
    for i, branch_id in enumerate(branches):
        print(f"  Branch {i+1}/{len(branches)}: {branch_id}")
        for month in range(1, 13):
            result = fetch_month_data(branch_id, month, session_id)
            if result['success']:
                success_count += 1
                sys.stdout.write(f"\r    Months: {month}/12 ✓")
            else:
                error_count += 1
                print(f"\n    ✗ Month {month}: {result['error']}")
            time.sleep(0.1)
        print()
    
    return {
        'option': 'A - Sequential',
        'total_time': time.time() - start_time,
        'success': success_count,
        'errors': error_count
    }

def benchmark_option_b(branches, session_id):
    """Option B: Sequential branches, 2 months parallel"""
    print("\n" + "="*60)
    print("🐇 Option B: Sequential branches, 2 months parallel")
    print("="*60)
    
    start_time = time.time()
    success_count = 0
    error_count = 0
    
    for i, branch_id in enumerate(branches):
        print(f"  Branch {i+1}/{len(branches)}: {branch_id}")
        
        for batch_start in range(1, 13, 2):
            months = [batch_start, batch_start + 1] if batch_start + 1 <= 12 else [batch_start]
            
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(fetch_month_data, branch_id, m, session_id): m for m in months}
                for future in as_completed(futures):
                    result = future.result()
                    if result['success']:
                        success_count += 1
                    else:
                        error_count += 1
                        print(f"    ✗ Month {futures[future]}: {result['error']}")
            
            sys.stdout.write(f"\r    Months: {min(batch_start+1, 12)}/12")
            time.sleep(0.2)
        print()
    
    return {
        'option': 'B - Sequential+Parallel(2)',
        'total_time': time.time() - start_time,
        'success': success_count,
        'errors': error_count
    }

def benchmark_option_c(branches, session_id, max_retries=2):
    """Option C: Sequential with retry"""
    print("\n" + "="*60)
    print(f"🔄 Option C: Sequential + Retry ({max_retries}x)")
    print("="*60)
    
    start_time = time.time()
    success_count = 0
    error_count = 0
    retry_used = 0
    
    for i, branch_id in enumerate(branches):
        print(f"  Branch {i+1}/{len(branches)}: {branch_id}")
        
        for month in range(1, 13):
            result = None
            for attempt in range(max_retries + 1):
                result = fetch_month_data(branch_id, month, session_id)
                if result['success']:
                    break
                if attempt < max_retries:
                    retry_used += 1
                    time.sleep(1)  # Wait before retry
            
            if result['success']:
                success_count += 1
                sys.stdout.write(f"\r    Months: {month}/12 ✓")
            else:
                error_count += 1
                print(f"\n    ✗ Month {month}: {result['error']} (failed after retries)")
            
            time.sleep(0.1)
        print()
    
    return {
        'option': 'C - Sequential+Retry',
        'total_time': time.time() - start_time,
        'success': success_count,
        'errors': error_count,
        'retries': retry_used
    }

def benchmark_option_d(branches, session_id):
    """Option D: 2 branches × 2 months with 1s delay"""
    print("\n" + "="*60)
    print("⏱️ Option D: 2 branches × 2 months, 1s delay")
    print("="*60)
    
    start_time = time.time()
    success_count = 0
    error_count = 0
    
    for b_start in range(0, len(branches), 2):
        b_end = min(b_start + 2, len(branches))
        branch_slice = branches[b_start:b_end]
        print(f"  Branches {b_start+1}-{b_end}/{len(branches)}")
        
        for m_start in range(1, 13, 2):
            months = [m_start, min(m_start + 1, 12)]
            tasks = [(b, m) for b in branch_slice for m in months]
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(fetch_month_data, b, m, session_id): (b, m) for b, m in tasks}
                for future in as_completed(futures):
                    result = future.result()
                    if result['success']:
                        success_count += 1
                    else:
                        error_count += 1
                        b, m = futures[future]
                        print(f"    ✗ B{b} M{m}: {result['error']}")
            
            sys.stdout.write(f"\r    Progress: {min(m_start+1, 12)}/12")
            time.sleep(1.0)  # Longer delay
        print()
    
    return {
        'option': 'D - Parallel+LongDelay',
        'total_time': time.time() - start_time,
        'success': success_count,
        'errors': error_count
    }

def print_summary(results):
    """Print comparison summary"""
    print("\n" + "="*70)
    print("📊 BENCHMARK RESULTS")
    print("="*70)
    print(f"{'Option':<30} {'Time':<12} {'Success':<10} {'Errors':<10}")
    print("-"*70)
    
    for r in results:
        retries = f" (retry:{r.get('retries', 0)})" if r.get('retries') else ""
        print(f"{r['option']:<30} {r['total_time']:.1f}s{'':<5} {r['success']:<10} {r['errors']}{retries}")
    
    print("-"*70)
    
    # Find best
    no_errors = [r for r in results if r['errors'] == 0]
    if no_errors:
        best = min(no_errors, key=lambda x: x['total_time'])
        print(f"\n🏆 BEST: {best['option']} ({best['total_time']:.1f}s, 0 errors)")
    else:
        best = min(results, key=lambda x: x['errors'])
        print(f"\n⚠️ BEST (least errors): {best['option']} ({best['errors']} errors)")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 benchmark_options.py <session_id>")
        print("\nGet session_id from browser cookies (ASP.NET_SessionId)")
        return
    
    session_id = sys.argv[1]
    branches = ZONE_APP_BRANCHES
    
    print("🔬 Zone APP Benchmark")
    print(f"Branches: {branches}")
    print(f"Session: {session_id[:15]}...")
    
    # Limit to first 2 branches for quick test
    test_branches = branches[:2]
    print(f"\n⚠️ Quick test: 2 branches × 12 months = 24 requests per option")
    
    results = []
    
    try:
        results.append(benchmark_option_a(test_branches, session_id))
        time.sleep(3)
        
        results.append(benchmark_option_b(test_branches, session_id))
        time.sleep(3)
        
        results.append(benchmark_option_c(test_branches, session_id))
        time.sleep(3)
        
        results.append(benchmark_option_d(test_branches, session_id))
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted!")
    
    if results:
        print_summary(results)

if __name__ == "__main__":
    main()
