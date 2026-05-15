import requests

def check_emp_counts():
    url = "https://report-trade.vercel.app/api/v2/trades?limit=50000"
    headers = {
        "X-API-Key": "techtrade_pro_secret_2026"
    }
    print("Fetching data from API...")
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json().get("data", [])
        print(f"Total rows fetched: {len(data)}")
        
        emp_stats = {}
        branch_645_count = 0
        
        for row in data:
            bid = str(row.get('real_branch_id', ''))
            bname = str(row.get('branch_name', ''))
            
            # Filter for the same branch the user is testing (Westgate / 645)
            if bid == '645' or 'Westgate' in bname:
                branch_645_count += 1
                emp_id = str(row.get('SALE_CODE', ''))
                emp_name = str(row.get('SALE_NAME', ''))
                status_text = str(row.get('BIDDING_STATUS_NAME', ''))
                
                # Use SALE_NAME as fallback if SALE_CODE is empty
                emp_key = f"ID:{emp_id}|NAME:{emp_name}"
                
                if emp_key not in emp_stats:
                    emp_stats[emp_key] = {"evaluated": 0, "agreed": 0, "status_breakdown": {}}
                
                emp_stats[emp_key]["evaluated"] += 1
                if status_text == "สิ้นสุดการประเมินราคา":
                    emp_stats[emp_key]["agreed"] += 1
                
                # Track exact status messages for this employee
                if status_text not in emp_stats[emp_key]["status_breakdown"]:
                    emp_stats[emp_key]["status_breakdown"][status_text] = 0
                emp_stats[emp_key]["status_breakdown"][status_text] += 1

        print(f"\n--- Branch 645 Total Evaluated: {branch_645_count} ---")
        for emp, stats in emp_stats.items():
            print(f"EMP {emp}: Evaluated={stats['evaluated']}, Agreed={stats['agreed']}")
            for st, cnt in stats["status_breakdown"].items():
                print(f"   -> {st}: {cnt}")
    else:
        print("API Error")

if __name__ == "__main__":
    check_emp_counts()
