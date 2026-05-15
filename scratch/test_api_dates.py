import requests

def check_dates():
    url = "https://report-trade.vercel.app/api/v2/trades?limit=50000&start_date=2026-04-01&end_date=2026-04-30"
    headers = {
        "X-API-Key": "techtrade_pro_secret_2026"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json().get("data", [])
        dates = {}
        for row in data:
            bid = str(row.get('real_branch_id', ''))
            bname = str(row.get('branch_name', ''))
            if bid == '645' or 'Westgate' in bname:
                dt = str(row.get('document_date', ''))
                dates[dt] = dates.get(dt, 0) + 1
                
        print("Date distribution for branch 645:")
        for dt, c in sorted(dates.items()):
            print(f"  - {dt}: {c} records")
    else:
        print("Error")

if __name__ == "__main__":
    check_dates()
