from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS
import sqlite3
import json
import os
import datetime
from functools import wraps

app = Flask(__name__)
CORS(app)

# 基本认证装饰器
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not (auth.username == 'admin' and auth.password == 'password'):
            abort(401)
        return f(*args, **kwargs)
    return decorated

# 数据库连接
DATABASE = 'yangfang.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

# 初始化数据库
if not os.path.exists(DATABASE):
    init_db()

# API接口

@app.route('/api/libraries', methods=['GET'])
@requires_auth
def get_libraries():
    db = get_db()
    cur = db.execute('SELECT * FROM libraries')
    libraries = [dict(row) for row in cur.fetchall()]
    return jsonify(libraries)

@app.route('/api/libraries', methods=['POST'])
@requires_auth
def add_library():
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    db = get_db()
    try:
        db.execute(
            'INSERT INTO libraries (name, data, created_at, updated_at) VALUES (?, ?, ?, ?)',
            [data.get('name'), json.dumps(data.get('data')), datetime.datetime.now().isoformat(), datetime.datetime.now().isoformat()]
        )
        db.commit()
        return jsonify({'success': True}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/libraries/<int:id>', methods=['PUT'])
@requires_auth
def update_library(id):
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    db = get_db()
    try:
        db.execute(
            'UPDATE libraries SET name = ?, data = ?, updated_at = ? WHERE id = ?',
            [data.get('name'), json.dumps(data.get('data')), datetime.datetime.now().isoformat(), id]
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/libraries/<int:id>', methods=['DELETE'])
@requires_auth
def delete_library(id):
    db = get_db()
    try:
        db.execute('DELETE FROM libraries WHERE id = ?', [id])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 静态文件服务
@app.route('/')
def serve_frontend():
    return send_from_directory('../', 'profit-tool-25.html')

@app.route('/<path:path>')
def serve_files(path):
    return send_from_directory('../', path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)
