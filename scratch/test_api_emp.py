import requests
import json

def check_emp_fields():
    url = "https://report-trade.vercel.app/api/v2/trades?limit=10"
    headers = {
        "X-API-Key": "techtrade_pro_secret_2026"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json().get("data", [])
        if data:
            print("Sample API row fields:")
            for k, v in data[0].items():
                print(f"  {k}: {v}")
    else:
        print("Error")

if __name__ == "__main__":
    check_emp_fields()
