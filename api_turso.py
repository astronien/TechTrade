from flask import Blueprint, jsonify, request
from turso_handler import TursoHandler
import os

# สร้าง Blueprint สำหรับ Turso API
turso_api = Blueprint('turso_api', __name__)

@turso_api.route('/api/v2/trades', methods=['GET'])
def get_trades():
    """
    API สำหรับดึงข้อมูล Trade จาก Turso 
    รองรับการ Filter ตาม Zone และวันที่
    """
    zone_name = request.args.get('zone')
    limit = request.args.get('limit', 100, type=int)
    
    turso = TursoHandler()
    if not turso.client:
        return jsonify({'error': 'Database connection failed'}), 500
        
    try:
        # สร้าง SQL สำหรับดึงข้อมูลล่าสุด
        query = "SELECT * FROM trades"
        params = []
        
        if zone_name:
            query += " WHERE zone_name = ?"
            params.append(zone_name)
            
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
