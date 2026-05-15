import requests
import json

def check_api():
    url = "https://report-trade.vercel.app/api/v2/trades?limit=50000&start_date=2026-04-01&end_date=2026-04-30"
    headers = {
        "X-API-Key": "techtrade_pro_secret_2026"
    }
    
    print(f"Fetching from: {url}")
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json().get("data", [])
        print(f"Total records received: {len(data)}")
        
        count_645 = 0
        status_counts = {}
        for row in data:
            bid = str(row.get('real_branch_id', ''))
            bname = str(row.get('branch_name', ''))
            
            if bid == '645' or 'Westgate' in bname:
                count_645 += 1
                status = str(row.get('status_name', 'Unknown'))
                status_counts[status] = status_counts.get(status, 0) + 1
                
        print(f"\nRecords for branch 645 / Westgate: {count_645}")
        print("Status breakdown:")
        for s, c in status_counts.items():
            print(f"  - {s}: {c}")
    else:
        print(f"Error fetching API: {response.status_code}")

if __name__ == "__main__":
    check_api()
