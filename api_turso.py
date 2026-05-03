from flask import Blueprint, jsonify, request
from turso_handler import TursoHandler
import os

# สร้าง Blueprint สำหรับ Turso API
turso_api = Blueprint('turso_api', __name__)

# ระบบ API Key พื้นฐาน (สามารถเปลี่ยนได้ที่ .env)
DEFAULT_API_KEY = "techtrade_pro_secret_2026"

def require_api_key(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        valid_key = os.environ.get('API_KEY', DEFAULT_API_KEY)
        
        # ถ้าเป็นการเรียกจากในเว็บตัวเอง (มี session) ให้ผ่านได้
        from flask import session
        if session.get('user'):
            return f(*args, **kwargs)
            
        if api_key and api_key == valid_key:
            return f(*args, **kwargs)
        
        return jsonify({'error': 'Unauthorized: Invalid or missing API Key'}), 401
    return decorated

@turso_api.route('/api/v2/trades', methods=['GET'])
@require_api_key
def get_trades():
    """
    API สำหรับดึงข้อมูล Trade จาก Turso 
    รองรับการ Filter ตาม Zone และวันที่
    """
    zone_name = request.args.get('zone')
    start_date = request.args.get('start_date') # YYYY-MM-DD
    end_date = request.args.get('end_date')     # YYYY-MM-DD
    limit = request.args.get('limit', 100, type=int)
    
    turso = TursoHandler()
    if not turso.client:
        return jsonify({'error': 'Database connection failed'}), 500
        
    try:
        # สร้าง SQL สำหรับดึงข้อมูล
        query = "SELECT * FROM trades"
        conditions = []
        params = []
        
        if zone_name:
            conditions.append("zone_name = ?")
            params.append(zone_name)
        
        if start_date:
            conditions.append("document_date >= ?")
            params.append(start_date)
            
        if end_date:
            conditions.append("document_date <= ?")
            params.append(end_date)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        query += " ORDER BY document_date DESC LIMIT ?"
        params.append(limit)
        
        result = turso.client.execute(query, params)
        
        # แปลงผลลัพธ์เป็น list of dicts
        trades = []
        columns = [col for col in result.columns]
        for row in result.rows:
            trades.append(dict(zip(columns, row)))
            
        return jsonify({
            'success': True,
            'count': len(trades),
            'data': trades
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        turso.close()

@turso_api.route('/api/v2/stats', methods=['GET'])
@require_api_key
def get_stats():
    """API สำหรับสรุปข้อมูลรายโซน (Dashboard Stats)"""
    turso = TursoHandler()
    try:
        query = """
            SELECT 
                zone_name, 
                COUNT(*) as total_trades, 
                SUM(net_price) as total_value,
                MAX(document_date) as last_updated
            FROM trades 
            GROUP BY zone_name
        """
        result = turso.client.execute(query)
        
        stats = []
        columns = [col for col in result.columns]
        for row in result.rows:
            stats.append(dict(zip(columns, row)))
            
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        turso.close()
