#!/usr/bin/env python3
"""
Aggressive Strategy Test - aiming for 100% success
Branch 231 (highest data volume)

Strategy: Sequential + Many Retries + Long Timeout + Long Delays
"""

import requests
import time
import sys

BASE_URL = "https://report-trade.vercel.app"
API_ENDPOINT = f"{BASE_URL}/api/annual-report-data"
YEAR = 2025
BRANCH_ID = "231"

def fetch_month_aggressive(month, session_id, timeout=60, max_retries=5):
    """Fetch with aggressive retry and long timeout"""
    params = {
        'year': YEAR,
        'month': month,
        'branchId': BRANCH_ID,
        'sessionId': session_id
    }
    
    for attempt in range(max_retries + 1):
        start = time.time()
        try:
            print(f"    Attempt {attempt+1}/{max_retries+1} (timeout={timeout}s)...", end=" ", flush=True)
            response = requests.get(API_ENDPOINT, params=params, timeout=timeout)
            elapsed = time.time() - start
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    print(f"✓ ({elapsed:.1f}s)")
                    return {'success': True, 'time': elapsed, 'attempts': attempt + 1}
                else:
                    print(f"API Error: {data.get('error', 'Unknown')[:30]}")
            else:
                print(f"HTTP {response.status_code}")
        except requests.exceptions.Timeout:
            print(f"Timeout ({time.time() - start:.1f}s)")
        except Exception as e:
            print(f"Error: {str(e)[:30]}")
        
        if attempt < max_retries:
            wait = 2 * (attempt + 1)  # Exponential backoff: 2, 4, 6, 8, 10s
            print(f"      Waiting {wait}s before retry...")
            time.sleep(wait)
    
    return {'success': False, 'attempts': max_retries + 1}

def test_strategy(session_id, timeout, retries, delay_between):
    """Test a specific strategy"""
    print(f"\n{'='*60}")
    print(f"🧪 Testing: timeout={timeout}s, retries={retries}, delay={delay_between}s")
    print(f"{'='*60}")
    
    start_time = time.time()
    success_count = 0
    total_attempts = 0
    
    for month in range(1, 13):
        print(f"\n  Month {month}/12:")
        result = fetch_month_aggressive(month, session_id, timeout, retries)
        
        if result['success']:
            success_count += 1
        total_attempts += result['attempts']
        
        if month < 12:
            print(f"    [Delay {delay_between}s]")
            time.sleep(delay_between)
    
    total_time = time.time() - start_time
    success_rate = (success_count / 12) * 100
    
    print(f"\n{'='*60}")
    print(f"📊 Result: {success_count}/12 ({success_rate:.0f}%)")
    print(f"   Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
    print(f"   Total attempts: {total_attempts}")
    print(f"{'='*60}")
    
    return {
        'success_count': success_count,
        'success_rate': success_rate,
        'total_time': total_time,
        'total_attempts': total_attempts,
        'config': f"timeout={timeout}s, retries={retries}, delay={delay_between}s"
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_aggressive.py <session_id>")
        return
    
    session_id = sys.argv[1]
    
    print("🔬 Aggressive Strategy Test - Branch 231")
    print("Goal: Find 100% success rate configuration\n")
    
    strategies = [
        # (timeout, retries, delay_between_months)
        (60, 5, 3),   # Strategy 1: 60s timeout, 5 retries, 3s delay
        (90, 7, 5),   # Strategy 2: 90s timeout, 7 retries, 5s delay (if needed)
    ]
    
    results = []
    
    for timeout, retries, delay in strategies:
        result = test_strategy(session_id, timeout, retries, delay)
        results.append(result)
        
        if result['success_rate'] == 100:
            print("\n🎉 FOUND 100% SUCCESS RATE!")
            print(f"   Config: {result['config']}")
            print(f"   Time: {result['total_time']/60:.1f} minutes")
            break
        else:
            print(f"\n⚠️ Not 100% - trying next strategy...")
            time.sleep(5)
    
    # Summary
    print("\n" + "="*60)
    print("📊 FINAL SUMMARY")
    print("="*60)
    for r in results:
        status = "✅" if r['success_rate'] == 100 else "❌"
        print(f"{status} {r['config']}: {r['success_rate']:.0f}% ({r['total_time']/60:.1f} min)")

if __name__ == "__main__":
    main()
