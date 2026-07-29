from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import hashlib
import uuid
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), 'material.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            department TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS material_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_code TEXT UNIQUE NOT NULL,
            material_name TEXT NOT NULL,
            category TEXT,
            unit TEXT,
            safety_stock INTEGER DEFAULT 0,
            max_stock INTEGER DEFAULT 0,
            min_stock INTEGER DEFAULT 0,
            supplier TEXT,
            remark TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS batch_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_code TEXT UNIQUE NOT NULL,
            material_id INTEGER NOT NULL,
            production_date DATE,
            expire_date DATE,
            supplier_batch TEXT,
            quantity INTEGER DEFAULT 0,
            status TEXT DEFAULT 'in_stock',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (material_id) REFERENCES material_master(id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS stock_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            batch_id INTEGER NOT NULL,
            warehouse TEXT,
            quantity INTEGER DEFAULT 0,
            in_quantity INTEGER DEFAULT 0,
            out_quantity INTEGER DEFAULT 0,
            last_update DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (material_id) REFERENCES material_master(id),
            FOREIGN KEY (batch_id) REFERENCES batch_info(id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS stock_flow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            batch_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            operator TEXT,
            operation_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            reason TEXT,
            remark TEXT,
            FOREIGN KEY (material_id) REFERENCES material_master(id),
            FOREIGN KEY (batch_id) REFERENCES batch_info(id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS alert_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            batch_id INTEGER,
            alert_type TEXT NOT NULL,
            level TEXT DEFAULT 'low',
            message TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (material_id) REFERENCES material_master(id),
            FOREIGN KEY (batch_id) REFERENCES batch_info(id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS alert_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT UNIQUE NOT NULL,
            threshold INTEGER DEFAULT 7,
            enabled INTEGER DEFAULT 1
        )
    ''')
    
    c.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if c.fetchone()[0] == 0:
        hashed_pwd = hashlib.sha256('admin123'.encode()).hexdigest()
        c.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', ('admin', hashed_pwd, 'admin'))
    
    c.execute("SELECT COUNT(*) FROM alert_config")
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO alert_config (alert_type, threshold) VALUES (?, ?)', ('expiring', 7))
        c.execute('INSERT INTO alert_config (alert_type, threshold) VALUES (?, ?)', ('low_stock', 0))
    
    c.execute("SELECT COUNT(*) FROM material_master")
    if c.fetchone()[0] == 0:
        materials = [
            ('SUG-001', '白砂糖', '糖类', 'kg', 100, 1000, 50, '供应商A'),
            ('FLA-005', '香精-草莓', '香精', 'kg', 50, 500, 20, '供应商B'),
            ('PAC-010', '包装膜', '包装材料', '箱', 200, 2000, 100, '供应商C'),
            ('ACI-002', '柠檬酸', '添加剂', 'kg', 80, 800, 40, '供应商A'),
            ('WAT-001', '纯净水', '其他', '桶', 100, 500, 50, '供应商D')
        ]
        c.executemany('INSERT INTO material_master (material_code, material_name, category, unit, safety_stock, max_stock, min_stock, supplier) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', materials)
    
    conn.commit()
    conn.close()

def generate_token(user_id):
    return str(uuid.uuid4()) + '_' + str(user_id)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        token = token.replace('Bearer ', '')
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE id = ?', (token.split('_')[-1],))
        user = c.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'error': 'Token is invalid'}), 401
        
        return f(*args, **kwargs)
    
    return decorated

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    
    conn = get_db()
    c = conn.cursor()
    hashed_pwd = hashlib.sha256(password.encode()).hexdigest()
    c.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, hashed_pwd))
    user = c.fetchone()
    conn.close()
    
    if user:
        token = generate_token(user['id'])
        return jsonify({
            'token': token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'department': user['department']
            }
        })
    else:
        return jsonify({'error': '用户名或密码错误'}), 401

@app.route('/api/material/stats', methods=['GET'])
@token_required
def get_stats():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT COALESCE(SUM(quantity), 0) FROM stock_record')
    total_stock = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM material_master')
    total_materials = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM alert_record WHERE status = "pending"')
    alert_count = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM alert_record WHERE status = "pending" AND alert_type = "expired"')
    expired_count = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM alert_record WHERE status = "pending" AND alert_type = "expiring"')
    expiring_count = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM alert_record WHERE status = "pending" AND alert_type = "low_stock"')
    low_stock_count = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'total_stock': total_stock,
        'total_materials': total_materials,
        'alert_count': alert_count,
        'turnover_days': 7.5,
        'low_stock_count': low_stock_count,
        'expiring_count': expiring_count,
        'expired_count': expired_count
    })

@app.route('/api/material/alert', methods=['GET'])
@token_required
def get_alerts():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        SELECT ar.*, mm.material_name, mm.material_code, bi.batch_code
        FROM alert_record ar
        LEFT JOIN material_master mm ON ar.material_id = mm.id
        LEFT JOIN batch_info bi ON ar.batch_id = bi.id
        WHERE ar.status = "pending"
        ORDER BY ar.level DESC, ar.created_at DESC
    ''')
    alerts = []
    for row in c.fetchall():
        alerts.append({
            'id': row['id'],
            'material_id': row['material_id'],
            'material_name': row['material_name'],
            'material_code': row['material_code'],
            'batch_code': row['batch_code'],
            'alert_type': row['alert_type'],
            'level': row['level'],
            'message': row['message'],
            'status': row['status'],
            'created_at': row['created_at']
        })
    
    conn.close()
    
    return jsonify({'alerts': alerts, 'total': len(alerts)})

@app.route('/api/material/report/category', methods=['GET'])
@token_required
def get_category_distribution():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        SELECT mm.category, COALESCE(SUM(sr.quantity), 0) as value
        FROM material_master mm
        LEFT JOIN stock_record sr ON mm.id = sr.material_id
        GROUP BY mm.category
    ''')
    categories = []
    total = 0
    for row in c.fetchall():
        total += row['value']
        categories.append({
            'name': row['category'] or '其他',
            'value': row['value'],
            'percentage': 0
        })
    
    for cat in categories:
        cat['percentage'] = round((cat['value'] / total * 100) if total > 0 else 0, 2)
    
    conn.close()
    
    return jsonify({'categories': categories})

@app.route('/api/material/report/trend', methods=['GET'])
@token_required
def get_stock_trend():
    today = datetime.now()
    trend = []
    for i in range(7):
        date = today - timedelta(days=6 - i)
        date_str = date.strftime('%m-%d')
        trend.append({'date': date_str, 'value': 11000 + i * 200})
    
    return jsonify({'trend': trend})

@app.route('/api/material/master', methods=['GET'])
@token_required
def get_materials():
    conn = get_db()
    c = conn.cursor()
    
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    keyword = request.args.get('keyword', '')
    
    query = 'SELECT * FROM material_master WHERE 1=1'
    params = []
    
    if keyword:
        query += ' AND (material_code LIKE ? OR material_name LIKE ?)'
        params.extend([f'%{keyword}%', f'%{keyword}%'])
    
    c.execute(query + ' ORDER BY created_at DESC LIMIT ? OFFSET ?', params + [page_size, (page - 1) * page_size])
    materials = []
    for row in c.fetchall():
        materials.append(dict(row))
    
    c.execute('SELECT COUNT(*) FROM material_master WHERE 1=1' + (' AND (material_code LIKE ? OR material_name LIKE ?)' if keyword else ''), params)
    total = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({'materials': materials, 'total': total})

@app.route('/api/material/master', methods=['POST'])
@token_required
def create_material():
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    
    try:
        c.execute('''
            INSERT INTO material_master (material_code, material_name, category, unit, safety_stock, max_stock, min_stock, supplier, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['material_code'],
            data['material_name'],
            data.get('category', ''),
            data.get('unit', ''),
            data.get('safety_stock', 0),
            data.get('max_stock', 0),
            data.get('min_stock', 0),
            data.get('supplier', ''),
            data.get('remark', '')
        ))
        conn.commit()
        return jsonify({'id': c.lastrowid})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': '物料编码已存在'}), 400
    finally:
        conn.close()

@app.route('/api/material/master/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@token_required
def material_detail(id):
    conn = get_db()
    c = conn.cursor()
    
    if request.method == 'GET':
        c.execute('SELECT * FROM material_master WHERE id = ?', (id,))
        material = c.fetchone()
        conn.close()
        if material:
            return jsonify(dict(material))
        return jsonify({'error': '物料不存在'}), 404
    
    elif request.method == 'PUT':
        data = request.get_json()
        c.execute('''
            UPDATE material_master SET material_name=?, category=?, unit=?, safety_stock=?, max_stock=?, min_stock=?, supplier=?, remark=?
            WHERE id = ?
        ''', (
            data.get('material_name'),
            data.get('category', ''),
            data.get('unit', ''),
            data.get('safety_stock', 0),
            data.get('max_stock', 0),
            data.get('min_stock', 0),
            data.get('supplier', ''),
            data.get('remark', ''),
            id
        ))
        conn.commit()
        conn.close()
        return jsonify({'message': '更新成功'})
    
    elif request.method == 'DELETE':
        c.execute('DELETE FROM material_master WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return jsonify({'message': '删除成功'})

@app.route('/api/material/stock', methods=['GET'])
@token_required
def get_stock():
    conn = get_db()
    c = conn.cursor()
    
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    
    c.execute('''
        SELECT sr.*, mm.material_code, mm.material_name, bi.batch_code
        FROM stock_record sr
        JOIN material_master mm ON sr.material_id = mm.id
        JOIN batch_info bi ON sr.batch_id = bi.id
        ORDER BY sr.last_update DESC
        LIMIT ? OFFSET ?
    ''', (page_size, (page - 1) * page_size))
    records = []
    for row in c.fetchall():
        records.append(dict(row))
    
    c.execute('SELECT COUNT(*) FROM stock_record')
    total = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({'records': records, 'total': total})

@app.route('/api/material/batch', methods=['GET'])
@token_required
def get_batches():
    conn = get_db()
    c = conn.cursor()
    
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    
    c.execute('''
        SELECT bi.*, mm.material_code, mm.material_name
        FROM batch_info bi
        JOIN material_master mm ON bi.material_id = mm.id
        ORDER BY bi.created_at DESC
        LIMIT ? OFFSET ?
    ''', (page_size, (page - 1) * page_size))
    batches = []
    for row in c.fetchall():
        batches.append(dict(row))
    
    c.execute('SELECT COUNT(*) FROM batch_info')
    total = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({'records': batches, 'total': total})

@app.route('/api/material/flow', methods=['GET'])
@token_required
def get_flow():
    conn = get_db()
    c = conn.cursor()
    
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    flow_type = request.args.get('type', '')
    
    query = '''
        SELECT sf.*, mm.material_code, mm.material_name, bi.batch_code
        FROM stock_flow sf
        JOIN material_master mm ON sf.material_id = mm.id
        JOIN batch_info bi ON sf.batch_id = bi.id
        WHERE 1=1
    '''
    params = []
    
    if flow_type:
        query += ' AND sf.type = ?'
        params.append(flow_type)
    
    query += ' ORDER BY sf.operation_time DESC LIMIT ? OFFSET ?'
    params.extend([page_size, (page - 1) * page_size])
    
    c.execute(query, params)
    records = []
    for row in c.fetchall():
        records.append(dict(row))
    
    c.execute('SELECT COUNT(*) FROM stock_flow WHERE 1=1' + (' AND type = ?' if flow_type else ''), params[:-2])
    total = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({'records': records, 'total': total})

@app.route('/api/material/inbound', methods=['POST'])
@token_required
def inbound():
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    
    try:
        conn.execute('BEGIN')
        
        c.execute('SELECT * FROM material_master WHERE id = ?', (data['material_id'],))
        material = c.fetchone()
        if not material:
            raise Exception('物料不存在')
        
        c.execute('SELECT * FROM batch_info WHERE batch_code = ?', (data['batch_code'],))
        batch = c.fetchone()
        
        if not batch:
            c.execute('''
                INSERT INTO batch_info (batch_code, material_id, production_date, expire_date, supplier_batch, quantity, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['batch_code'],
                data['material_id'],
                data.get('production_date', ''),
                data.get('expire_date', ''),
                data.get('supplier_batch', ''),
                data['quantity'],
                'in_stock'
            ))
            batch_id = c.lastrowid
        else:
            batch_id = batch['id']
            c.execute('UPDATE batch_info SET quantity = quantity + ? WHERE id = ?', (data['quantity'], batch_id))
        
        c.execute('SELECT * FROM stock_record WHERE material_id = ? AND batch_id = ?', (data['material_id'], batch_id))
        stock = c.fetchone()
        
        if stock:
            c.execute('''
                UPDATE stock_record SET quantity = quantity + ?, in_quantity = in_quantity + ?, last_update = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (data['quantity'], data['quantity'], stock['id']))
        else:
            c.execute('''
                INSERT INTO stock_record (material_id, batch_id, warehouse, quantity, in_quantity)
                VALUES (?, ?, ?, ?, ?)
            ''', (data['material_id'], batch_id, data.get('warehouse', ''), data['quantity'], data['quantity']))
        
        c.execute('''
            INSERT INTO stock_flow (material_id, batch_id, type, quantity, operator, reason, remark)
            VALUES (?, ?, 'inbound', ?, 'admin', ?, ?)
        ''', (data['material_id'], batch_id, data['quantity'], data.get('reason', '采购入库'), data.get('remark', '')))
        
        check_alerts(conn, c, data['material_id'], batch_id)
        
        conn.commit()
        return jsonify({'id': c.lastrowid})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()

@app.route('/api/material/outbound', methods=['POST'])
@token_required
def outbound():
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    
    try:
        conn.execute('BEGIN')
        
        c.execute('SELECT * FROM stock_record WHERE material_id = ? AND batch_id = ?', (data['material_id'], data['batch_id']))
        stock = c.fetchone()
        
        if not stock:
            raise Exception('库存记录不存在')
        
        if stock['quantity'] < data['quantity']:
            raise Exception('库存不足')
        
        c.execute('''
            UPDATE stock_record SET quantity = quantity - ?, out_quantity = out_quantity + ?, last_update = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (data['quantity'], data['quantity'], stock['id']))
        
        c.execute('SELECT * FROM batch_info WHERE id = ?', (data['batch_id'],))
        batch = c.fetchone()
        
        if batch:
            new_qty = batch['quantity'] - data['quantity']
            status = 'empty' if new_qty <= 0 else ('partial' if new_qty < batch['quantity'] else 'in_stock')
            c.execute('UPDATE batch_info SET quantity = ?, status = ? WHERE id = ?', (max(0, new_qty), status, batch['id']))
        
        c.execute('''
            INSERT INTO stock_flow (material_id, batch_id, type, quantity, operator, reason, remark)
            VALUES (?, ?, 'outbound', ?, 'admin', ?, ?)
        ''', (data['material_id'], data['batch_id'], data['quantity'], data.get('reason', '生产领料'), data.get('remark', '')))
        
        check_alerts(conn, c, data['material_id'], data['batch_id'])
        
        conn.commit()
        return jsonify({'id': c.lastrowid})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()

def check_alerts(conn, c, material_id, batch_id):
    c.execute('SELECT safety_stock FROM material_master WHERE id = ?', (material_id,))
    material = c.fetchone()
    if not material:
        return
    
    c.execute('SELECT COALESCE(SUM(quantity), 0) FROM stock_record WHERE material_id = ?', (material_id,))
    total_qty = c.fetchone()[0]
    
    if total_qty < material['safety_stock']:
        c.execute('SELECT COUNT(*) FROM alert_record WHERE material_id = ? AND alert_type = "low_stock" AND status = "pending"', (material_id,))
        if c.fetchone()[0] == 0:
            c.execute('''
                INSERT INTO alert_record (material_id, alert_type, level, message)
                VALUES (?, 'low_stock', 'low', ?)
            ''', (material_id, f'当前库存{total_qty}，低于安全库存{material["safety_stock"]}'))
    
    c.execute('SELECT expire_date FROM batch_info WHERE id = ?', (batch_id,))
    batch = c.fetchone()
    if batch and batch['expire_date']:
        expire_date = datetime.strptime(batch['expire_date'], '%Y-%m-%d')
        today = datetime.now().date()
        days_left = (expire_date - today).days
        
        if days_left < 0:
            c.execute('SELECT COUNT(*) FROM alert_record WHERE batch_id = ? AND alert_type = "expired" AND status = "pending"', (batch_id,))
            if c.fetchone()[0] == 0:
                c.execute('''
                    INSERT INTO alert_record (material_id, batch_id, alert_type, level, message)
                    VALUES (?, ?, 'expired', 'high', ?)
                ''', (material_id, batch_id, f'已过期{abs(days_left)}天'))
        elif days_left <= 7:
            c.execute('SELECT COUNT(*) FROM alert_record WHERE batch_id = ? AND alert_type = "expiring" AND status = "pending"', (batch_id,))
            if c.fetchone()[0] == 0:
                c.execute('''
                    INSERT INTO alert_record (material_id, batch_id, alert_type, level, message)
                    VALUES (?, ?, 'expiring', 'medium', ?)
                ''', (material_id, batch_id, f'{days_left}天后过期'))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)