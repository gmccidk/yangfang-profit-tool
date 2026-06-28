from flask import Flask, request, jsonify, send_from_directory, abort, g
from flask_cors import CORS
import sqlite3
import json
import os
import datetime
import uuid
import hashlib
import hmac
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
_PROJECT_DB = os.path.join(BASE_DIR, 'yangfang.db')

# 数据库连接：线上必须使用项目目录里的持久化数据库。
# PythonAnywhere 的 /tmp 目录不适合保存菜单、图片、价格等业务数据，
# 否则进程重启后可能回到旧数据。
DATABASE = os.environ.get('YANGFANG_DATABASE') or os.environ.get('YANGFANG_DB_PATH') or _PROJECT_DB
if os.path.dirname(DATABASE):
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)

# 会话有效期（小时）
SESSION_EXPIRE_HOURS = 24


def verify_password_hash(stored_hash, password):
    """兼容新版 Werkzeug 生成的 scrypt 哈希，以及旧版支持的哈希。"""
    try:
        return check_password_hash(stored_hash, password)
    except ValueError:
        pass

    try:
        method, salt, hash_hex = str(stored_hash or '').split('$', 2)
        if not method.startswith('scrypt:'):
            return False
        _, n, r, p = method.split(':')
        derived = hashlib.scrypt(
            str(password or '').encode('utf-8'),
            salt=salt.encode('utf-8'),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(hash_hex))
        )
        return hmac.compare_digest(derived.hex(), hash_hex)
    except Exception:
        return False


def get_db():
    if 'db' not in g:
        conn = sqlite3.connect(DATABASE, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=NORMAL")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

        # 如果 users 表为空，自动创建 admin 管理员账号
        cur = db.execute('SELECT COUNT(*) as cnt FROM users')
        count = cur.fetchone()['cnt']
        if count == 0:
            now = datetime.datetime.now().isoformat()
            db.execute(
                'INSERT INTO users (username, password_hash, role, display_name, created_at, is_active) VALUES (?, ?, ?, ?, ?, ?)',
                ['admin', generate_password_hash('admin123'), 'admin', '管理员', now, 1]
            )
            db.commit()


def ensure_schema_migrations():
    with app.app_context():
        db = get_db()
        user_columns = [row['name'] for row in db.execute('PRAGMA table_info(users)').fetchall()]
        if 'last_login_at' not in user_columns:
            db.execute('ALTER TABLE users ADD COLUMN last_login_at TEXT')
            db.commit()


def count_saved_history_records(data):
    if not isinstance(data, dict):
        return 0
    total = 0
    for lib in data.get('libraries') or []:
        if isinstance(lib, dict) and isinstance(lib.get('history'), list):
            total += len(lib.get('history'))
    for lib in data.get('orphanedHistoryLibs') or []:
        if isinstance(lib, dict) and isinstance(lib.get('history'), list):
            total += len(lib.get('history'))
    return total


def slim_user_state_data(data):
    """用户状态只保留套餐/历史/选择信息，不携带菜品图片和价格成本主数据。"""
    if not isinstance(data, dict):
        return data
    out = {
        'activeId': data.get('activeId'),
        'orphanedHistoryLibs': data.get('orphanedHistoryLibs') if isinstance(data.get('orphanedHistoryLibs'), list) else [],
        'libraries': []
    }
    for lib in data.get('libraries') or []:
        if not isinstance(lib, dict):
            continue
        slim_lib = {
            'id': lib.get('id'),
            'backendId': lib.get('backendId'),
            'name': lib.get('name'),
            'pkgName': lib.get('pkgName'),
            'groupPrice': lib.get('groupPrice'),
            'pkgRemark': lib.get('pkgRemark'),
            'history': lib.get('history') if isinstance(lib.get('history'), list) else [],
            'choiceGroups': lib.get('choiceGroups') if isinstance(lib.get('choiceGroups'), list) else [],
            'db': []
        }
        for row in lib.get('db') or []:
            if not isinstance(row, dict):
                continue
            slim_row = {
                '商品名称': row.get('商品名称'),
                'qty': row.get('qty') or 0,
                'manualOrder': row.get('manualOrder') or 0,
                '规格': row.get('规格') or '',
                'importLineNo': row.get('importLineNo')
            }
            if slim_row['qty'] or slim_row['manualOrder'] or slim_row['规格'] or slim_row['importLineNo'] is not None:
                slim_lib['db'].append(slim_row)
        out['libraries'].append(slim_lib)
    return out


def strip_library_images_data(data):
    if not isinstance(data, dict):
        return data
    out = dict(data)
    rows = []
    for row in out.get('db') or []:
        if not isinstance(row, dict):
            rows.append(row)
            continue
        slim = dict(row)
        if slim.get('菜品图片'):
            slim['_imageLazy'] = True
            slim.pop('菜品图片', None)
        rows.append(slim)
    out['db'] = rows
    out['_imagesLazy'] = True
    return out


def merge_library_images(existing_data, incoming_data):
    if not isinstance(existing_data, dict) or not isinstance(incoming_data, dict):
        return incoming_data
    existing_rows = {
        str(row.get('商品名称') or '').strip(): row
        for row in (existing_data.get('db') or [])
        if isinstance(row, dict)
    }
    for row in incoming_data.get('db') or []:
        if not isinstance(row, dict):
            continue
        row.pop('_imageLazy', None)
        name = str(row.get('商品名称') or '').strip()
        existing_img = existing_rows.get(name, {}).get('菜品图片') if name else None
        if not row.get('菜品图片') and existing_img:
            row['菜品图片'] = existing_img
    incoming_data.pop('_imagesLazy', None)
    incoming_data.pop('_imagesLoadedCategories', None)
    return incoming_data


# 初始化数据库
if not os.path.exists(DATABASE):
    init_db()
else:
    # 每次启动也执行 init_db 以确保新表/字段被创建
    init_db()
ensure_schema_migrations()


# ============================================================
# 认证装饰器
# ============================================================

def get_current_user():
    """从请求头中解析 token 并返回用户信息，未认证返回 None"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header[7:].strip()
    if not token:
        return None

    db = get_db()
    cur = db.execute(
        'SELECT s.*, u.username, u.role, u.display_name, u.is_active '
        'FROM sessions s JOIN users u ON s.user_id = u.id '
        'WHERE s.token = ?',
        [token]
    )
    session = cur.fetchone()
    if not session:
        return None

    # 检查会话是否过期
    if datetime.datetime.fromisoformat(session['expires_at']) < datetime.datetime.now():
        # 清理过期会话
        db.execute('DELETE FROM sessions WHERE id = ?', [session['id']])
        db.commit()
        return None

    # 检查用户是否被禁用
    if not session['is_active']:
        return None

    return {
        'id': session['user_id'],
        'username': session['username'],
        'role': session['role'],
        'display_name': session['display_name'],
    }


def requires_auth(f):
    """要求用户已登录（任意角色）"""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': '未认证，请先登录'}), 401
        request.current_user = user
        return f(*args, **kwargs)
    return decorated


def requires_admin(f):
    """要求用户为管理员"""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': '未认证，请先登录'}), 401
        if user['role'] != 'admin':
            return jsonify({'error': '权限不足，需要管理员权限'}), 403
        request.current_user = user
        return f(*args, **kwargs)
    return decorated


# ============================================================
# 认证 API
# ============================================================

@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录，返回 token"""
    data = request.json
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': '请提供用户名和密码'}), 400

    username = data['username']
    password = data['password']

    db = get_db()
    cur = db.execute('SELECT * FROM users WHERE username = ?', [username])
    user = cur.fetchone()

    if not user or not verify_password_hash(user['password_hash'], password):
        return jsonify({'error': '用户名或密码错误'}), 401

    if not user['is_active']:
        return jsonify({'error': '账号已被禁用，请联系管理员'}), 403

    # 生成 token 和会话
    token = str(uuid.uuid4())
    now = datetime.datetime.now()
    expires_at = now + datetime.timedelta(hours=SESSION_EXPIRE_HOURS)

    db.execute(
        'INSERT INTO sessions (user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)',
        [user['id'], token, now.isoformat(), expires_at.isoformat()]
    )
    db.execute(
        'UPDATE users SET last_login_at = ? WHERE id = ?',
        [now.isoformat(), user['id']]
    )
    db.commit()

    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'display_name': user['display_name'],
        }
    })


@app.route('/api/auth/logout', methods=['POST'])
@requires_auth
def logout():
    """用户登出，删除当前会话"""
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:].strip() if auth_header.startswith('Bearer ') else ''

    if token:
        db = get_db()
        db.execute('DELETE FROM sessions WHERE token = ?', [token])
        db.commit()

    return jsonify({'success': True})


@app.route('/api/auth/verify', methods=['GET'])
@requires_auth
def verify_session():
    """验证当前会话是否有效"""
    user = request.current_user
    return jsonify({
        'success': True,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'display_name': user['display_name'],
        }
    })


# ============================================================
# 用户管理 API（仅管理员）
# ============================================================

@app.route('/api/users', methods=['GET'])
@requires_admin
def get_users():
    """获取所有用户列表"""
    db = get_db()
    cur = db.execute(
        '''
        SELECT
            u.id,
            u.username,
            u.role,
            u.display_name,
            u.created_at,
            COALESCE(u.last_login_at, MAX(s.created_at)) AS last_login_at,
            u.is_active
        FROM users u
        LEFT JOIN sessions s ON s.user_id = u.id
        GROUP BY u.id
        ORDER BY u.id
        '''
    )
    users = [dict(row) for row in cur.fetchall()]
    states = db.execute('SELECT user_id, data FROM user_states').fetchall()
    history_counts = {}
    for state in states:
        try:
            count = count_saved_history_records(json.loads(state['data']))
        except Exception:
            count = 0
        history_counts[state['user_id']] = history_counts.get(state['user_id'], 0) + count
    for user in users:
        user['history_count'] = history_counts.get(user['id'], 0)
    return jsonify(users)


@app.route('/api/users', methods=['POST'])
@requires_admin
def create_user():
    """创建新用户"""
    data = request.json
    if not data:
        return jsonify({'error': '请提供用户数据'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'user').strip()
    display_name = data.get('display_name', '').strip()

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    if role not in ('admin', 'user'):
        return jsonify({'error': '角色只能是 admin 或 user'}), 400

    db = get_db()
    # 检查用户名是否已存在
    cur = db.execute('SELECT id FROM users WHERE username = ?', [username])
    if cur.fetchone():
        return jsonify({'error': '用户名已存在'}), 409

    now = datetime.datetime.now().isoformat()
    try:
        cursor = db.execute(
            'INSERT INTO users (username, password_hash, role, display_name, created_at, is_active) VALUES (?, ?, ?, ?, ?, ?)',
            [username, generate_password_hash(password), role, display_name or username, now, 1]
        )
        db.commit()
        return jsonify({
            'success': True,
            'id': cursor.lastrowid,
            'username': username,
            'role': role,
            'display_name': display_name or username,
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/users/<int:user_id>', methods=['PUT'])
@requires_admin
def update_user(user_id):
    """更新用户信息（修改角色、显示名、重置密码、启用/禁用）"""
    data = request.json
    if not data:
        return jsonify({'error': '请提供更新数据'}), 400

    db = get_db()
    cur = db.execute('SELECT * FROM users WHERE id = ?', [user_id])
    user = cur.fetchone()
    if not user:
        return jsonify({'error': '用户不存在'}), 404

    # 构建更新字段
    updates = []
    params = []

    if 'display_name' in data:
        updates.append('display_name = ?')
        params.append(data['display_name'].strip())

    if 'role' in data:
        role = data['role'].strip()
        if role not in ('admin', 'user'):
            return jsonify({'error': '角色只能是 admin 或 user'}), 400
        updates.append('role = ?')
        params.append(role)

    if 'password' in data:
        new_password = data['password'].strip()
        if not new_password:
            return jsonify({'error': '密码不能为空'}), 400
        updates.append('password_hash = ?')
        params.append(generate_password_hash(new_password))

    if 'is_active' in data:
        updates.append('is_active = ?')
        params.append(1 if data['is_active'] else 0)

    if not updates:
        return jsonify({'error': '没有需要更新的字段'}), 400

    params.append(user_id)
    try:
        db.execute(
            f'UPDATE users SET {", ".join(updates)} WHERE id = ?',
            params
        )
        db.commit()

        # 如果禁用了用户，同时删除其所有会话
        if 'is_active' in data and not data['is_active']:
            db.execute('DELETE FROM sessions WHERE user_id = ?', [user_id])
            db.commit()

        # 返回更新后的用户信息
        cur = db.execute(
            'SELECT id, username, role, display_name, created_at, is_active FROM users WHERE id = ?',
            [user_id]
        )
        updated_user = dict(cur.fetchone())
        return jsonify({'success': True, 'user': updated_user})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@requires_admin
def delete_user(user_id):
    """删除用户（同时删除其会话和库数据）"""
    db = get_db()
    cur = db.execute('SELECT * FROM users WHERE id = ?', [user_id])
    user = cur.fetchone()
    if not user:
        return jsonify({'error': '用户不存在'}), 404

    # 不允许删除自己
    if user['id'] == request.current_user['id']:
        return jsonify({'error': '不能删除自己的账号'}), 400

    try:
        # 删除用户的会话
        db.execute('DELETE FROM sessions WHERE user_id = ?', [user_id])
        # 删除用户的库数据
        db.execute('DELETE FROM libraries WHERE user_id = ?', [user_id])
        # 删除用户
        db.execute('DELETE FROM users WHERE id = ?', [user_id])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# 修改密码 API（普通用户可用）
# ============================================================

@app.route('/api/auth/change-password', methods=['POST'])
@requires_auth
def change_password():
    """修改当前用户密码"""
    data = request.json
    if not data or not data.get('old_password') or not data.get('new_password'):
        return jsonify({'error': '请提供旧密码和新密码'}), 400

    user = request.current_user
    db = get_db()
    cur = db.execute('SELECT password_hash FROM users WHERE id = ?', [user['id']])
    row = cur.fetchone()

    if not verify_password_hash(row['password_hash'], data['old_password']):
        return jsonify({'error': '旧密码错误'}), 401

    new_password = data['new_password'].strip()
    if len(new_password) < 4:
        return jsonify({'error': '新密码长度不能少于4位'}), 400

    db.execute(
        'UPDATE users SET password_hash = ? WHERE id = ?',
        [generate_password_hash(new_password), user['id']]
    )
    db.commit()
    return jsonify({'success': True})


# ============================================================
# Libraries API（管理员创建的库对所有用户可见，只有创建者可编辑/删除）
# ============================================================

@app.route('/api/libraries', methods=['GET'])
@requires_auth
def get_libraries():
    """获取库列表：普通用户只看管理员维护的共享菜单，管理员可看全部菜单。"""
    user = request.current_user
    db = get_db()
    lite = request.args.get('lite') == '1'
    full_id = request.args.get('full_id', type=int)
    cur = db.execute(
        'SELECT * FROM libraries WHERE user_id IN (SELECT id FROM users WHERE role = ?) ORDER BY id',
        ['admin']
    )
    rows = cur.fetchall()
    if lite:
        if full_id is None and rows:
            full_id = rows[0]['id']
        libraries = []
        for row in rows:
            item = dict(row)
            if row['id'] != full_id:
                item['data'] = json.dumps({
                    'id': f"backend-{row['id']}",
                    'backendId': row['id'],
                    'name': row['name'],
                    'db': [],
                    '_lazy': True
                })
            else:
                try:
                    item['data'] = json.dumps(strip_library_images_data(json.loads(row['data'])))
                except Exception:
                    pass
            libraries.append(item)
    else:
        libraries = [dict(row) for row in rows]
    return jsonify(libraries)


@app.route('/api/libraries/<int:id>', methods=['GET'])
@requires_auth
def get_library(id):
    """获取单个共享菜单完整数据。"""
    db = get_db()
    cur = db.execute(
        'SELECT * FROM libraries WHERE id = ? AND user_id IN (SELECT id FROM users WHERE role = ?)',
        [id, 'admin']
    )
    row = cur.fetchone()
    if not row:
        return jsonify({'error': '菜单不存在或无权查看'}), 404
    item = dict(row)
    if request.args.get('include_images') != '1':
        try:
            item['data'] = json.dumps(strip_library_images_data(json.loads(item['data'])))
        except Exception:
            pass
    return jsonify(item)


@app.route('/api/libraries/<int:id>/images', methods=['GET'])
@requires_auth
def get_library_images(id):
    """按分类获取菜单图片，避免首屏一次性加载全部 base64 图片。"""
    category = request.args.get('category', '')
    db = get_db()
    cur = db.execute(
        'SELECT data FROM libraries WHERE id = ? AND user_id IN (SELECT id FROM users WHERE role = ?)',
        [id, 'admin']
    )
    row = cur.fetchone()
    if not row:
        return jsonify({'error': '菜单不存在或无权查看'}), 404
    try:
        data = json.loads(row['data'])
        images = {}
        for dish in data.get('db') or []:
            if not isinstance(dish, dict):
                continue
            if category and dish.get('分类') != category:
                continue
            img = dish.get('菜品图片')
            name = dish.get('商品名称')
            if name and img:
                images[name] = img
        return jsonify({'category': category, 'images': images})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/libraries', methods=['POST'])
@requires_auth
def add_library():
    """为当前用户创建库"""
    if request.current_user['role'] != 'admin':
        return jsonify({'error': '权限不足，需要管理员权限'}), 403

    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    user = request.current_user
    db = get_db()
    try:
        now = datetime.datetime.now().isoformat()
        cursor = db.execute(
            'INSERT INTO libraries (name, data, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?)',
            [data.get('name'), json.dumps(data.get('data')), now, now, user['id']]
        )
        db.commit()
        return jsonify({'success': True, 'id': cursor.lastrowid}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/libraries/<int:id>', methods=['PUT'])
@requires_auth
def update_library(id):
    """更新当前用户的库"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    user = request.current_user
    if user['role'] != 'admin':
        return jsonify({'error': '权限不足，需要管理员权限'}), 403

    db = get_db()

    # 管理员可维护共享菜单库
    cur = db.execute('SELECT * FROM libraries WHERE id = ?', [id])
    if not cur.fetchone():
        return jsonify({'error': '库不存在或无权操作'}), 404

    try:
        cur = db.execute('SELECT data FROM libraries WHERE id = ?', [id])
        existing = cur.fetchone()
        incoming_data = data.get('data')
        if existing:
            try:
                incoming_data = merge_library_images(json.loads(existing['data']), incoming_data)
            except Exception:
                pass
        db.execute(
            'UPDATE libraries SET name = ?, data = ?, updated_at = ? WHERE id = ?',
            [data.get('name'), json.dumps(incoming_data), datetime.datetime.now().isoformat(), id]
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/libraries/<int:id>', methods=['DELETE'])
@requires_auth
def delete_library(id):
    """删除当前用户的库"""
    user = request.current_user
    if user['role'] != 'admin':
        return jsonify({'error': '权限不足，需要管理员权限'}), 403

    db = get_db()

    # 管理员可删除共享菜单库
    cur = db.execute('SELECT * FROM libraries WHERE id = ?', [id])
    if not cur.fetchone():
        return jsonify({'error': '库不存在或无权操作'}), 404

    try:
        db.execute('DELETE FROM libraries WHERE id = ?', [id])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user-state/<state_key>', methods=['GET'])
@requires_auth
def get_user_state(state_key):
    """获取当前用户的独立前端状态：套餐历史、当前配置等"""
    user = request.current_user
    db = get_db()
    cur = db.execute(
        'SELECT data FROM user_states WHERE user_id = ? AND state_key = ?',
        [user['id'], state_key]
    )
    row = cur.fetchone()
    if not row:
        return jsonify({'data': None})
    try:
        return jsonify({'data': slim_user_state_data(json.loads(row['data']))})
    except Exception:
        return jsonify({'data': None})


@app.route('/api/user-state/<state_key>', methods=['PUT'])
@requires_auth
def put_user_state(state_key):
    """保存当前用户的独立前端状态。不同账号互相隔离。"""
    payload = request.json or {}
    user = request.current_user
    data = payload.get('data')
    if data is None:
        return jsonify({'error': 'No data provided'}), 400

    db = get_db()
    try:
        now = datetime.datetime.now().isoformat()
        db.execute(
            '''
            INSERT INTO user_states (user_id, state_key, data, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, state_key)
            DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
            ''',
            [user['id'], state_key, json.dumps(data), now]
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# 静态文件服务 - 使用绝对路径（保持不变）
# ============================================================

@app.route('/')
def serve_frontend():
    return send_from_directory(PARENT_DIR, 'profit-tool-25.html')


@app.route('/<path:path>')
def serve_files(path):
    return send_from_directory(PARENT_DIR, path)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)
