import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    'https://report-trade.vercel.app/api/v2/trades',
    headers={'X-API-Key': 'techtrade_pro_secret_2026'}
)

try:
    with urllib.request.urlopen(req, context=ctx) as response:
        payload = json.loads(response.read().decode('utf-8'))
        data = payload.get('data', [])
        
        # Filter for Westgate (645)
        westgate_trades = []
        for t in data:
            bid = str(t.get('real_branch_id', ''))
            bname = str(t.get('branch_name', ''))
            if bid == '645' or 'Westgate' in bname:
                westgate_trades.append(t)
                
        print(f"Total Westgate Trades: {len(westgate_trades)}")
        
        # Group by SALE_CODE and SALE_NAME
        emp_stats = {}
        for t in westgate_trades:
            emp_id = str(t.get('SALE_CODE', '')).strip()
            # Normalize ID like in JS
            try:
                emp_id = str(int(emp_id))
            except:
                pass
                
            emp_name = str(t.get('SALE_NAME', '')).strip()
            key = f"{emp_id}|{emp_name}"
            
            if key not in emp_stats:
                emp_stats[key] = {'eval': 0, 'agreed': 0}
            
            emp_stats[key]['eval'] += 1
            
            status = str(t.get('BIDDING_STATUS_NAME', '')).strip()
            if status in ['สิ้นสุดการประเมินราคา', 'ยืนยันราคาแล้ว']:
                emp_stats[key]['agreed'] += 1
                
        # Print results sorted by eval desc
        for k, v in sorted(emp_stats.items(), key=lambda x: x[1]['eval'], reverse=True):
            print(f"EMP: {k} -> Eval: {v['eval']}, Agreed: {v['agreed']}")
            
except Exception as e:
    print("Error:", e)
