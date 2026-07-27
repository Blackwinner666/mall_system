# -*- coding: utf-8 -*-
"""
百货商城系统 - 后端 API
技术栈: Flask + SQLite + Session Auth
功能模块: 首页/店铺管理/商品管理/订单管理/售后管理
"""
import os
import sqlite3
import hashlib
import json
import time
import re
from datetime import datetime, timedelta
from functools import wraps
import requests
from flask import Flask, request, jsonify, session, redirect, url_for, g

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = 'mall_secret_key_2026_change_in_production'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mall.db')


def _load_dotenv():
    """Load .env file if present (simple parser, no external dependency).
    Real API keys live in .env (gitignored), never in source code."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass


_load_dotenv()


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys=ON")

    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            role TEXT NOT NULL DEFAULT 'customer',
            phone TEXT,
            email TEXT,
            avatar TEXT DEFAULT '',
            store_role TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            logo TEXT DEFAULT '',
            description TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            detail_html TEXT DEFAULT '',
            price REAL NOT NULL DEFAULT 0,
            original_price REAL,
            stock INTEGER NOT NULL DEFAULT 0,
            category_id INTEGER,
            brand_id INTEGER,
            images TEXT DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'active',
            sales_count INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            specs TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id),
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        );

        CREATE TABLE IF NOT EXISTS product_skus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            sku_code TEXT,
            spec_values TEXT NOT NULL DEFAULT '[]',
            price REAL NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL DEFAULT 0,
            image TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS product_collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            cover_image TEXT DEFAULT '',
            product_ids TEXT DEFAULT '[]',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            wechat_id TEXT,
            address TEXT,
            city TEXT,
            notes TEXT,
            total_orders INTEGER DEFAULT 0,
            total_spent REAL DEFAULT 0,
            source TEXT DEFAULT '商城',
            tags TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            customer_id INTEGER,
            total_amount REAL NOT NULL DEFAULT 0,
            discount_amount REAL DEFAULT 0,
            actual_amount REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending_payment',
            payment_method TEXT,
            payment_time TIMESTAMP,
            shipping_address TEXT,
            receiver_name TEXT DEFAULT '',
            receiver_phone TEXT DEFAULT '',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT,
            product_image TEXT,
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL,
            specs TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS delivery_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            express_company TEXT DEFAULT '',
            tracking_number TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            shipped_at TIMESTAMP,
            delivered_at TIMESTAMP,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );

        CREATE TABLE IF NOT EXISTS shipping_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            province TEXT DEFAULT '',
            city TEXT DEFAULT '',
            district TEXT DEFAULT '',
            address TEXT NOT NULL,
            is_default INTEGER DEFAULT 0,
            address_type TEXT DEFAULT 'return',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS order_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            rating INTEGER DEFAULT 5,
            content TEXT DEFAULT '',
            images TEXT DEFAULT '[]',
            reply TEXT DEFAULT '',
            reply_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );

        CREATE TABLE IF NOT EXISTS after_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            type TEXT NOT NULL DEFAULT 'refund',
            reason TEXT DEFAULT '',
            description TEXT DEFAULT '',
            images TEXT DEFAULT '[]',
            amount REAL DEFAULT 0,
            status TEXT DEFAULT 'pending',
            handler_note TEXT DEFAULT '',
            result TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );

        CREATE TABLE IF NOT EXISTS appeals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            after_sale_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            reason TEXT DEFAULT '',
            description TEXT DEFAULT '',
            images TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            handler_note TEXT DEFAULT '',
            result TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (after_sale_id) REFERENCES after_sales(id)
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT DEFAULT '',
            is_pinned INTEGER DEFAULT 0,
            status TEXT DEFAULT 'published',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS platform_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            banner_image TEXT DEFAULT '',
            start_time TEXT,
            end_time TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS store_page_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_type TEXT NOT NULL,
            title TEXT DEFAULT '',
            config TEXT DEFAULT '{}',
            sort_order INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS store_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS visit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page TEXT,
            ip TEXT,
            user_agent TEXT,
            visitor_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS cart_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            sku_id INTEGER,
            product_name TEXT,
            product_image TEXT,
            spec_desc TEXT,
            quantity INTEGER NOT NULL DEFAULT 1,
            price REAL NOT NULL,
            checked INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id),
            UNIQUE(user_id, product_id)
        );

        CREATE TABLE IF NOT EXISTS generation_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action_type TEXT NOT NULL,
            title TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            status TEXT DEFAULT 'success',
            draft_media_id TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS style_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            profile_json TEXT NOT NULL DEFAULT '{}',
            source_url TEXT DEFAULT '',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS article_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            blocks_json TEXT NOT NULL DEFAULT '[]',
            thumbnail TEXT DEFAULT '',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        );
    """)

    # --- 迁移：补充可能缺失的字段 ---
    migrations = [
        # products 表
        "ALTER TABLE products ADD COLUMN detail_html TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN brand_id INTEGER",
        # users 表
        "ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN store_role TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active'",
        "ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN default_style_template TEXT DEFAULT ''",
        # orders 表
        "ALTER TABLE orders ADD COLUMN receiver_name TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN receiver_phone TEXT DEFAULT ''",
        # article_templates 表迁移
        "ALTER TABLE article_templates ADD COLUMN is_public INTEGER DEFAULT 0",
        "ALTER TABLE article_templates ADD COLUMN author_name TEXT DEFAULT ''",
    ]
    for m in migrations:
        try:
            c.execute(m)
        except sqlite3.OperationalError:
            pass

    # --- 种子数据 ---
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        admin_hash = hashlib.sha256('admin123'.encode()).hexdigest()
        customer_hash = hashlib.sha256('123456'.encode()).hexdigest()
        c.execute("INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
                   ('admin', admin_hash, '管理员', 'admin'))
        c.execute("INSERT INTO users (username, password_hash, display_name, role, phone) VALUES (?, ?, ?, ?, ?)",
                   ('customer1', customer_hash, '顾客小王', 'customer', '13800000001'))

    c.execute("SELECT COUNT(*) FROM categories")
    if c.fetchone()[0] == 0:
        categories = ['服装鞋帽', '数码家电', '食品饮料', '家居日用', '美妆护肤', '母婴用品', '运动户外', '图书文具']
        for i, name in enumerate(categories):
            c.execute("INSERT INTO categories (name, sort_order) VALUES (?, ?)", (name, i))

    c.execute("SELECT COUNT(*) FROM brands")
    if c.fetchone()[0] == 0:
        brands = ['华为', '小米', '苹果', '耐克', '阿迪达斯', '联合利华', '宝洁', '三星', '美的', '格力']
        for i, name in enumerate(brands):
            c.execute("INSERT INTO brands (name, sort_order) VALUES (?, ?)", (name, i))

    c.execute("SELECT COUNT(*) FROM store_settings WHERE key='store_name'")
    if c.fetchone()[0] == 0:
        defaults = [
            ('store_name', '百货商城'),
            ('store_logo', ''),
            ('store_description', '品质百货，一站购齐'),
            ('contact_phone', ''),
            ('contact_email', ''),
            ('store_address', ''),
            ('shipping_fee', '0'),
            ('free_shipping_min', '99'),
            ('wechat_pay_enabled', 'true'),
            ('alipay_enabled', 'true'),
        ]
        for k, v in defaults:
            c.execute("INSERT INTO store_settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()


# ============================================================
# 认证装饰器
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': '请先登录'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': '请先登录'}), 401
            return redirect(url_for('login_page'))
        if session.get('role') != 'admin':
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': '权限不足'}), 403
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


def log_visit(page=''):
    db = get_db()
    visitor_id = request.cookies.get('visitor_id', '')
    db.execute("INSERT INTO visit_logs (page, ip, user_agent, visitor_id) VALUES (?, ?, ?, ?)",
               (page, request.remote_addr, request.user_agent.string[:200] if request.user_agent else '', visitor_id))
    db.commit()


def read_template(path):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', path), 'r', encoding='utf-8') as f:
        return f.read()


# ============================================================
# 页面路由
# ============================================================

@app.route('/')
def index():
    log_visit('home')
    return read_template('store/index.html')


@app.route('/login')
def login_page():
    return read_template('login.html')


@app.route('/product/<int:product_id>')
def product_detail_page(product_id):
    return read_template('store/product_detail.html')


@app.route('/cart')
def cart_page():
    return read_template('store/cart.html')


@app.route('/profile')
def profile_page():
    return read_template('store/profile.html')


@app.route('/admin')
@admin_required
def admin_dashboard():
    return read_template('admin/dashboard.html')


@app.route('/admin/store')
@admin_required
def admin_store():
    return read_template('admin/store.html')


@app.route('/admin/products')
@admin_required
def admin_products():
    return read_template('admin/products.html')


@app.route('/admin/orders')
@admin_required
def admin_orders():
    return read_template('admin/orders.html')


@app.route('/admin/after-sales')
@admin_required
def admin_after_sales():
    return read_template('admin/after_sales.html')


@app.route('/admin/customers')
@admin_required
def admin_customers():
    return read_template('admin/customers.html')


@app.route('/admin/settings')
@admin_required
def admin_settings():
    return read_template('admin/settings.html')


@app.route('/template-editor')
@login_required
def template_editor_page():
    """模板编辑器 - 所有登录用户均可访问"""
    return read_template('admin/template_editor.html')


@app.route('/admin/template-editor')
@login_required
def admin_template_editor():
    """兼容旧路径，重定向到新路径"""
    return read_template('admin/template_editor.html')


# ============================================================
# 认证 API
# ============================================================

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()
    identifier = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not identifier or not password:
        return jsonify({'success': False, 'message': '账号和密码不能为空'})

    db = get_db()

    # 自动识别登录方式：手机号 / 邮箱 / 用户名
    user = None
    if re.match(r'^1[3-9]\d{9}$', identifier):
        # 手机号登录
        user = db.execute("SELECT * FROM users WHERE phone = ? AND status='active'", (identifier,)).fetchone()
    elif re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', identifier):
        # 邮箱登录
        user = db.execute("SELECT * FROM users WHERE email = ? AND status='active'", (identifier,)).fetchone()
    else:
        # 用户名登录（也尝试用手机号匹配，兼容旧数据）
        user = db.execute("SELECT * FROM users WHERE (username = ? OR phone = ?) AND status='active'", (identifier, identifier)).fetchone()

    if not user:
        return jsonify({'success': False, 'message': '账号或密码错误'})

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if user['password_hash'] != password_hash:
        return jsonify({'success': False, 'message': '账号或密码错误'})

    db.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user['id'],))
    db.commit()

    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    session['display_name'] = user['display_name'] or user['username']
    session.permanent = True

    return jsonify({
        'success': True,
        'message': '登录成功',
        'user': {
            'id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'display_name': user['display_name'] or user['username'],
            'default_style_template': user['default_style_template'] or ''
        }
    })


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True, 'message': '已退出登录'})


@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip()
    display_name = data.get('display_name', '').strip()

    if not password:
        return jsonify({'success': False, 'message': '请设置密码'})
    if len(password) < 6:
        return jsonify({'success': False, 'message': '密码至少6个字符'})

    # 手机号和邮箱至少填一个
    has_phone = bool(phone)
    has_email = bool(email)
    if not has_phone and not has_email:
        return jsonify({'success': False, 'message': '请至少填写手机号或邮箱'})

    # 验证手机号格式
    if has_phone and not re.match(r'^1[3-9]\d{9}$', phone):
        return jsonify({'success': False, 'message': '请输入正确的手机号'})

    # 验证邮箱格式
    if has_email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return jsonify({'success': False, 'message': '请输入正确的邮箱地址'})

    # 自动生成用户名（用手机号或邮箱前缀）
    if not username:
        if has_phone:
            username = phone
        else:
            username = email.split('@')[0]

    # 如果自动生成的用户名已被占用，加随机后缀
    db = get_db()
    base_username = username
    counter = 1
    while db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
        username = f"{base_username}{counter}"
        counter += 1

    # 显示名默认用用户名
    if not display_name:
        display_name = username

    # 检查手机号唯一
    if has_phone:
        existing_phone = db.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
        if existing_phone:
            return jsonify({'success': False, 'message': '该手机号已被注册'})

    # 检查邮箱唯一
    if has_email:
        existing_email = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing_email:
            return jsonify({'success': False, 'message': '该邮箱已被注册'})

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    db.execute(
        "INSERT INTO users (username, password_hash, display_name, role, phone, email) VALUES (?, ?, ?, ?, ?, ?)",
        (username, password_hash, display_name, 'customer', phone, email))
    db.commit()

    # 同时创建客户记录
    db.execute(
        "INSERT INTO customers (name, phone, email, source) VALUES (?, ?, ?, ?)",
        (display_name, phone, email, '自主注册'))
    db.commit()

    return jsonify({'success': True, 'message': '注册成功，请登录'})


@app.route('/api/auth/me', methods=['GET'])
def api_me():
    if 'user_id' not in session:
        return jsonify({'success': False, 'logged_in': False})
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    if not user:
        return jsonify({'success': False, 'logged_in': False})
    return jsonify({
        'success': True,
        'logged_in': True,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'display_name': user['display_name'] or user['username'],
            'default_style_template': user['default_style_template'] or ''
        }
    })


# ============================================================
# 数据分析 API (首页 Dashboard)
# ============================================================

@app.route('/api/admin/analytics', methods=['GET'])
@admin_required
def api_analytics():
    db = get_db()
    today = datetime.now().strftime('%Y-%m-%d')
    this_week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
    this_month_start = datetime.now().strftime('%Y-%m-01')

    # 今日数据
    pv_today = db.execute("SELECT COUNT(*) FROM visit_logs WHERE date(created_at) = ?", (today,)).fetchone()[0]
    uv_today = db.execute("SELECT COUNT(DISTINCT visitor_id) FROM visit_logs WHERE date(created_at) = ? AND visitor_id != ''", (today,)).fetchone()[0]
    orders_today = db.execute("SELECT COUNT(*), COALESCE(SUM(actual_amount), 0) FROM orders WHERE date(created_at) = ?", (today,)).fetchone()

    # 本周数据
    orders_week = db.execute("SELECT COUNT(*), COALESCE(SUM(actual_amount), 0) FROM orders WHERE date(created_at) >= ?", (this_week_start,)).fetchone()
    customers_week = db.execute("SELECT COUNT(*) FROM customers WHERE date(created_at) >= ?", (this_week_start,)).fetchone()[0]

    # 本月数据
    orders_month = db.execute("SELECT COUNT(*), COALESCE(SUM(actual_amount), 0) FROM orders WHERE date(created_at) >= ?", (this_month_start,)).fetchone()

    # 汇总数据
    total_products = db.execute("SELECT COUNT(*) FROM products WHERE status != 'deleted'").fetchone()[0]
    active_products = db.execute("SELECT COUNT(*) FROM products WHERE status = 'active'").fetchone()[0]
    total_customers = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    total_revenue = db.execute("SELECT COALESCE(SUM(actual_amount), 0) FROM orders WHERE status = 'completed'").fetchone()[0]

    # 7天趋势
    recent_7days = []
    for i in range(6, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        v = db.execute("SELECT COUNT(*) FROM visit_logs WHERE date(created_at) = ?", (d,)).fetchone()[0]
        o = db.execute("SELECT COUNT(*) FROM orders WHERE date(created_at) = ?", (d,)).fetchone()[0]
        r = db.execute("SELECT COALESCE(SUM(actual_amount), 0) FROM orders WHERE date(created_at) = ?", (d,)).fetchone()[0]
        recent_7days.append({'date': d[5:], 'pv': v, 'orders': o, 'revenue': round(r, 2)})

    # 订单状态分布
    order_status = []
    status_labels = {'pending_payment': '待付款', 'paid': '已付款', 'shipped': '已发货', 'completed': '已完成', 'cancelled': '已取消'}
    for s, label in status_labels.items():
        c = db.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (s,)).fetchone()[0]
        order_status.append({'status': s, 'label': label, 'count': c})

    # 待处理售后
    pending_after_sales = db.execute("SELECT COUNT(*) FROM after_sales WHERE status = 'pending'").fetchone()[0]

    # 最新订单
    latest_orders = db.execute("""
        SELECT o.order_no, o.status, o.actual_amount, o.created_at, c.name as customer_name
        FROM orders o LEFT JOIN customers c ON o.customer_id = c.id
        ORDER BY o.id DESC LIMIT 5
    """).fetchall()
    latest = [{'order_no': lo['order_no'], 'status': lo['status'], 'amount': lo['actual_amount'],
               'customer': lo['customer_name'] or '未知', 'time': lo['created_at']} for lo in latest_orders]

    return jsonify({
        'success': True,
        'data': {
            'pv_today': pv_today,
            'uv_today': uv_today,
            'orders_today': orders_today[0],
            'revenue_today': round(orders_today[1] or 0, 2),
            'orders_week': orders_week[0],
            'revenue_week': round(orders_week[1] or 0, 2),
            'customers_week': customers_week,
            'orders_month': orders_month[0],
            'revenue_month': round(orders_month[1] or 0, 2),
            'total_products': total_products,
            'active_products': active_products,
            'total_customers': total_customers,
            'total_revenue': round(total_revenue, 2),
            'pending_after_sales': pending_after_sales,
            'recent_7days': recent_7days,
            'order_status': order_status,
            'latest_orders': latest
        }
    })


# ============================================================
# 商品管理 API
# ============================================================

@app.route('/api/products', methods=['GET'])
def api_products():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    category_id = request.args.get('category_id', type=int)
    brand_id = request.args.get('brand_id', type=int)
    keyword = request.args.get('keyword', '')
    status = request.args.get('status', '')

    query = """
        SELECT p.*, c.name as category_name, b.name as brand_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN brands b ON p.brand_id = b.id
        WHERE 1=1
    """
    params = []

    if category_id:
        query += " AND p.category_id = ?"
        params.append(category_id)
    if brand_id:
        query += " AND p.brand_id = ?"
        params.append(brand_id)
    if keyword:
        query += " AND p.name LIKE ?"
        params.append(f'%{keyword}%')
    if status:
        if status == 'non_sellable':
            query += " AND p.status = 'non_sellable'"
        elif status != 'all':
            query += " AND p.status = ?"
            params.append(status)
    else:
        query += " AND p.status NOT IN ('deleted', 'non_sellable')"

    count = db.execute(f"SELECT COUNT(*) FROM ({query})", params).fetchone()[0]
    offset = (page - 1) * per_page
    query += " ORDER BY p.id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    products = db.execute(query, params).fetchall()
    items = []
    for p in products:
        items.append({
            'id': p['id'],
            'name': p['name'],
            'description': p['description'],
            'detail_html': p['detail_html'] or '',
            'price': p['price'],
            'original_price': p['original_price'],
            'stock': p['stock'],
            'category_id': p['category_id'],
            'category_name': p['category_name'],
            'brand_id': p['brand_id'],
            'brand_name': p['brand_name'],
            'images': json.loads(p['images'] or '[]'),
            'status': p['status'],
            'sales_count': p['sales_count'],
            'view_count': p['view_count'],
            'specs': json.loads(p['specs'] or '[]'),
            'created_at': p['created_at']
        })

    return jsonify({
        'success': True,
        'data': {'items': items, 'total': count, 'page': page, 'per_page': per_page}
    })


@app.route('/api/products/<int:product_id>', methods=['GET'])
def api_product_detail(product_id):
    db = get_db()
    p = db.execute("""
        SELECT p.*, c.name as category_name, b.name as brand_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN brands b ON p.brand_id = b.id
        WHERE p.id = ?
    """, (product_id,)).fetchone()
    if not p:
        return jsonify({'success': False, 'message': '商品不存在'}), 404

    skus = db.execute("SELECT * FROM product_skus WHERE product_id = ? AND status != 'deleted' ORDER BY id", (product_id,)).fetchall()
    sku_list = [{
        'id': sku['id'], 'sku_code': sku['sku_code'],
        'spec_values': json.loads(sku['spec_values'] or '[]'),
        'price': sku['price'], 'stock': sku['stock'], 'image': sku['image'], 'status': sku['status']
    } for sku in skus]

    return jsonify({
        'success': True,
        'data': {
            'id': p['id'], 'name': p['name'], 'description': p['description'],
            'detail_html': p['detail_html'] or '',
            'price': p['price'], 'original_price': p['original_price'],
            'stock': p['stock'],
            'category_id': p['category_id'], 'category_name': p['category_name'],
            'brand_id': p['brand_id'], 'brand_name': p['brand_name'],
            'images': json.loads(p['images'] or '[]'),
            'status': p['status'], 'sales_count': p['sales_count'],
            'view_count': p['view_count'],
            'specs': json.loads(p['specs'] or '[]'), 'skus': sku_list,
            'created_at': p['created_at']
        }
    })


@app.route('/api/products', methods=['POST'])
@admin_required
def api_add_product():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': '商品名称不能为空'})

    db = get_db()
    cursor = db.execute("""
        INSERT INTO products (name, description, detail_html, price, original_price, stock,
            category_id, brand_id, images, specs, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        data.get('description', ''),
        data.get('detail_html', ''),
        float(data.get('price', 0)),
        float(data.get('original_price', 0)) or None,
        int(data.get('stock', 0)),
        data.get('category_id') or None,
        data.get('brand_id') or None,
        json.dumps(data.get('images', []), ensure_ascii=False),
        json.dumps(data.get('specs', []), ensure_ascii=False),
        data.get('status', 'active')
    ))
    product_id = cursor.lastrowid

    skus = data.get('skus', [])
    for sku in skus:
        db.execute("""
            INSERT INTO product_skus (product_id, sku_code, spec_values, price, stock, image)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            product_id, sku.get('sku_code', ''),
            json.dumps(sku.get('spec_values', []), ensure_ascii=False),
            float(sku.get('price', data.get('price', 0))),
            int(sku.get('stock', 0)), sku.get('image', '')
        ))
    db.commit()
    return jsonify({'success': True, 'message': '商品添加成功', 'data': {'id': product_id}})


@app.route('/api/products/<int:product_id>', methods=['PUT'])
@admin_required
def api_update_product(product_id):
    db = get_db()
    existing = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not existing:
        return jsonify({'success': False, 'message': '商品不存在'}), 404

    data = request.get_json()
    db.execute("""
        UPDATE products SET name=?, description=?, detail_html=?, price=?, original_price=?, stock=?,
        category_id=?, brand_id=?, images=?, specs=?, status=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (
        data.get('name', existing['name']),
        data.get('description', existing['description']),
        data.get('detail_html', existing['detail_html'] or ''),
        float(data.get('price', existing['price'])),
        float(data.get('original_price', 0)) or None,
        int(data.get('stock', existing['stock'])),
        data.get('category_id', existing['category_id']),
        data.get('brand_id', existing['brand_id']),
        json.dumps(data.get('images', json.loads(existing['images'] or '[]')), ensure_ascii=False),
        json.dumps(data.get('specs', json.loads(existing['specs'] or '[]')), ensure_ascii=False),
        data.get('status', existing['status']),
        product_id
    ))

    if 'skus' in data:
        db.execute("UPDATE product_skus SET status='deleted' WHERE product_id = ?", (product_id,))
        for sku in data['skus']:
            db.execute("""
                INSERT INTO product_skus (product_id, sku_code, spec_values, price, stock, image)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                product_id, sku.get('sku_code', ''),
                json.dumps(sku.get('spec_values', []), ensure_ascii=False),
                float(sku.get('price', data.get('price', existing['price']))),
                int(sku.get('stock', 0)), sku.get('image', '')
            ))
    db.commit()
    return jsonify({'success': True, 'message': '商品更新成功'})


@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@admin_required
def api_delete_product(product_id):
    db = get_db()
    db.execute("UPDATE products SET status='deleted', updated_at=CURRENT_TIMESTAMP WHERE id=?", (product_id,))
    db.commit()
    return jsonify({'success': True, 'message': '商品已删除'})


@app.route('/api/products/<int:product_id>/status', methods=['PUT'])
@admin_required
def api_product_status(product_id):
    """快捷修改商品状态（标记为非卖品等）"""
    data = request.get_json()
    new_status = data.get('status')
    valid = ['active', 'draft', 'non_sellable', 'deleted']
    if new_status not in valid:
        return jsonify({'success': False, 'message': '无效状态'})
    db = get_db()
    db.execute("UPDATE products SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_status, product_id))
    db.commit()
    return jsonify({'success': True, 'message': '状态已更新'})


# ============================================================
# 购物车 API
# ============================================================

def login_required(f):
    """需要登录的装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': '请先登录', 'need_login': True}), 401
        return f(*args, **kwargs)
    return decorated


@app.route('/api/cart', methods=['GET'])
@login_required
def api_cart_list():
    """获取购物车列表"""
    db = get_db()
    items = db.execute("""
        SELECT ci.*, p.stock as product_stock, p.status as product_status, p.images as product_images
        FROM cart_items ci
        LEFT JOIN products p ON ci.product_id = p.id
        WHERE ci.user_id = ?
        ORDER BY ci.created_at DESC
    """, (session['user_id'],)).fetchall()

    cart_list = []
    for item in items:
        # 如果商品已下架，标记但保留
        available = item['product_status'] == 'active'
        imgs = json.loads(item['product_images'] or '[]') if item['product_images'] else []
        cart_list.append({
            'id': item['id'],
            'product_id': item['product_id'],
            'sku_id': item['sku_id'],
            'product_name': item['product_name'],
            'product_image': item['product_image'] or (imgs[0] if imgs else ''),
            'spec_desc': item['spec_desc'] or '',
            'quantity': item['quantity'],
            'price': item['price'],
            'checked': bool(item['checked']),
            'stock': item['product_stock'] or 99999,
            'available': available,
            'created_at': item['created_at']
        })

    # 统计
    total_count = sum(item['quantity'] for item in cart_list)
    checked_items = [item for item in cart_list if item['checked'] and item['available']]
    checked_total = sum(item['price'] * item['quantity'] for item in checked_items)
    all_checked = len(cart_list) > 0 and all(item['checked'] for item in cart_list)

    return jsonify({
        'success': True,
        'data': {
            'items': cart_list,
            'total_count': total_count,
            'checked_count': len(checked_items),
            'checked_total': round(checked_total, 2),
            'all_checked': all_checked
        }
    })


@app.route('/api/cart', methods=['POST'])
@login_required
def api_cart_add():
    """加入购物车"""
    data = request.get_json()
    product_id = int(data.get('product_id', 0))
    sku_id = data.get('sku_id')
    quantity = int(data.get('quantity', 1))
    spec_desc = data.get('spec_desc', '')

    if not product_id or quantity < 1:
        return jsonify({'success': False, 'message': '参数错误'})

    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ? AND status='active'", (product_id,)).fetchone()
    if not product:
        return jsonify({'success': False, 'message': '商品不存在或已下架'})

    # 确定价格与图片
    price = float(product['price'])
    product_name = product['name']
    imgs = json.loads(product['images'] or '[]')
    product_image = imgs[0] if imgs else ''

    if sku_id:
        sku = db.execute("SELECT * FROM product_skus WHERE id = ? AND product_id = ? AND status='active'",
                         (sku_id, product_id)).fetchone()
        if sku:
            price = float(sku['price'])
            if sku['image']:
                product_image = sku['image']

    # 检查是否已存在相同商品+规格
    if sku_id:
        existing = db.execute(
            "SELECT * FROM cart_items WHERE user_id = ? AND product_id = ? AND sku_id = ?",
            (session['user_id'], product_id, sku_id)).fetchone()
    else:
        existing = db.execute(
            "SELECT * FROM cart_items WHERE user_id = ? AND product_id = ? AND (sku_id IS NULL OR sku_id = 0)",
            (session['user_id'], product_id)).fetchone()

    if existing:
        new_qty = existing['quantity'] + quantity
        db.execute("UPDATE cart_items SET quantity = ?, checked = 1 WHERE id = ?", (new_qty, existing['id']))
        db.commit()
        return jsonify({'success': True, 'message': '已更新购物车数量', 'data': {'id': existing['id'], 'quantity': new_qty}})

    db.execute("""
        INSERT INTO cart_items (user_id, product_id, sku_id, product_name, product_image, spec_desc, quantity, price, checked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (session['user_id'], product_id, sku_id, product_name, product_image, spec_desc, quantity, price))
    db.commit()
    return jsonify({
        'success': True,
        'message': '已加入购物车',
        'data': {'id': db.execute("SELECT last_insert_rowid()").fetchone()[0]}
    })


@app.route('/api/cart/<int:item_id>', methods=['PUT'])
@login_required
def api_cart_update(item_id):
    """更新购物车商品数量"""
    data = request.get_json()
    quantity = int(data.get('quantity', 1))
    checked = data.get('checked')

    db = get_db()
    item = db.execute("SELECT * FROM cart_items WHERE id = ? AND user_id = ?", (item_id, session['user_id'])).fetchone()
    if not item:
        return jsonify({'success': False, 'message': '购物车项不存在'})

    if checked is not None:
        db.execute("UPDATE cart_items SET checked = ? WHERE id = ?", (1 if checked else 0, item_id))

    if quantity and quantity > 0:
        db.execute("UPDATE cart_items SET quantity = ? WHERE id = ?", (quantity, item_id))

    db.commit()
    return jsonify({'success': True, 'message': '更新成功'})


@app.route('/api/cart/<int:item_id>', methods=['DELETE'])
@login_required
def api_cart_delete(item_id):
    """删除购物车单项"""
    db = get_db()
    db.execute("DELETE FROM cart_items WHERE id = ? AND user_id = ?", (item_id, session['user_id']))
    db.commit()
    return jsonify({'success': True, 'message': '已删除'})


@app.route('/api/cart', methods=['DELETE'])
@login_required
def api_cart_clear():
    """清空购物车（已勾选的）或全部"""
    data = request.get_json() or {}
    clear_all = data.get('all', False)
    db = get_db()
    if clear_all:
        db.execute("DELETE FROM cart_items WHERE user_id = ?", (session['user_id'],))
    else:
        db.execute("DELETE FROM cart_items WHERE user_id = ? AND checked = 1", (session['user_id'],))
    db.commit()
    return jsonify({'success': True, 'message': '已清空'})


@app.route('/api/cart/check-all', methods=['PUT'])
@login_required
def api_cart_check_all():
    """全选/全不选"""
    data = request.get_json()
    checked = 1 if data.get('checked', True) else 0
    db = get_db()
    db.execute("UPDATE cart_items SET checked = ? WHERE user_id = ?", (checked, session['user_id']))
    db.commit()
    return jsonify({'success': True})


# ============================================================
# 收藏 API
# ============================================================

@app.route('/api/favorites', methods=['GET'])
@login_required
def api_favorites_list():
    """获取用户收藏列表"""
    db = get_db()
    favorites = db.execute("""
        SELECT f.*, p.name as product_name, p.price, p.original_price,
               p.images, p.status as product_status, p.sales_count, p.stock
        FROM favorites f
        LEFT JOIN products p ON f.product_id = p.id
        WHERE f.user_id = ?
        ORDER BY f.created_at DESC
    """, (session['user_id'],)).fetchall()

    items = []
    for f in favorites:
        imgs = json.loads(f['images'] or '[]')
        items.append({
            'id': f['id'],
            'product_id': f['product_id'],
            'product_name': f['product_name'],
            'price': f['price'],
            'original_price': f['original_price'],
            'image': imgs[0] if imgs else '',
            'product_status': f['product_status'],
            'sales_count': f['sales_count'],
            'stock': f['stock'],
            'created_at': f['created_at']
        })

    return jsonify({
        'success': True,
        'data': {'items': items, 'total': len(items)}
    })


@app.route('/api/favorites/<int:product_id>', methods=['POST'])
@login_required
def api_favorite_toggle(product_id):
    """切换收藏状态（收藏/取消收藏）"""
    db = get_db()
    existing = db.execute(
        "SELECT id FROM favorites WHERE user_id = ? AND product_id = ?",
        (session['user_id'], product_id)
    ).fetchone()

    if existing:
        db.execute("DELETE FROM favorites WHERE id = ?", (existing['id'],))
        db.commit()
        return jsonify({'success': True, 'favorited': False, 'message': '已取消收藏'})
    else:
        product = db.execute("SELECT id FROM products WHERE id = ? AND status = 'active'", (product_id,)).fetchone()
        if not product:
            return jsonify({'success': False, 'message': '商品不存在'})
        db.execute("INSERT INTO favorites (user_id, product_id) VALUES (?, ?)",
                   (session['user_id'], product_id))
        db.commit()
        return jsonify({'success': True, 'favorited': True, 'message': '已加入收藏'})


@app.route('/api/favorites/check/<int:product_id>', methods=['GET'])
def api_favorite_check(product_id):
    """检查是否已收藏（需要登录）"""
    if 'user_id' not in session:
        return jsonify({'success': True, 'favorited': False})
    db = get_db()
    fav = db.execute(
        "SELECT id FROM favorites WHERE user_id = ? AND product_id = ?",
        (session['user_id'], product_id)
    ).fetchone()
    return jsonify({'success': True, 'favorited': bool(fav)})


# ============================================================
# 用户个人中心 API
# ============================================================

@app.route('/api/user/profile', methods=['GET'])
@login_required
def api_user_profile():
    """获取用户个人中心数据（含订单统计）"""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'})

    # 通过手机号找到客户记录
    customer = db.execute("SELECT * FROM customers WHERE phone = ?", (user['phone'],)).fetchone() if user['phone'] else None
    customer_id = customer['id'] if customer else None

    # 订单状态统计
    order_stats = {}
    status_config = {
        'pending_payment': '待付款',
        'paid': '待发货',
        'shipped': '待收货',
        'completed': '待评价'
    }

    if customer_id:
        for status, label in status_config.items():
            if status == 'completed':
                # 待评价 = 已完成但没评价的订单
                count = db.execute("""
                    SELECT COUNT(*) FROM orders o
                    WHERE o.customer_id = ? AND o.status = 'completed'
                    AND NOT EXISTS (SELECT 1 FROM order_reviews r WHERE r.order_id = o.id)
                """, (customer_id,)).fetchone()[0]
            else:
                count = db.execute(
                    "SELECT COUNT(*) FROM orders WHERE customer_id = ? AND status = ?",
                    (customer_id, status)
                ).fetchone()[0]
            order_stats[status] = count

        # 售后统计
        after_sales_count = db.execute(
            "SELECT COUNT(*) FROM after_sales WHERE customer_id = ? AND status != 'completed'",
            (customer_id,)
        ).fetchone()[0]
        order_stats['after_sales'] = after_sales_count
    else:
        for status in list(status_config.keys()) + ['after_sales']:
            order_stats[status] = 0

    # 收藏数
    fav_count = db.execute("SELECT COUNT(*) FROM favorites WHERE user_id = ?", (session['user_id'],)).fetchone()[0]

    return jsonify({
        'success': True,
        'data': {
            'user': {
                'id': user['id'],
                'username': user['username'],
                'display_name': user['display_name'] or user['username'],
                'phone': user['phone'] or '',
                'email': user['email'] or '',
                'avatar': user['avatar'] or '',
                'created_at': user['created_at']
            },
            'customer_id': customer_id,
            'order_stats': order_stats,
            'fav_count': fav_count
        }
    })


@app.route('/api/user/orders', methods=['GET'])
@login_required
def api_user_orders():
    """获取用户订单列表（按状态筛选）"""
    db = get_db()
    user = db.execute("SELECT phone FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    if not user or not user['phone']:
        return jsonify({'success': True, 'data': {'items': [], 'total': 0}})

    customer = db.execute("SELECT id FROM customers WHERE phone = ?", (user['phone'],)).fetchone()
    if not customer:
        return jsonify({'success': True, 'data': {'items': [], 'total': 0}})

    customer_id = customer['id']
    status = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    query = """
        SELECT o.* FROM orders o WHERE o.customer_id = ?
    """
    params = [customer_id]

    if status == 'pending_review':
        # 待评价：已完成的订单且没有评价
        query += """ AND o.status = 'completed'
            AND NOT EXISTS (SELECT 1 FROM order_reviews r WHERE r.order_id = o.id)"""
    elif status == 'after_sales':
        # 有售后的订单
        query += """ AND EXISTS (SELECT 1 FROM after_sales a WHERE a.order_id = o.id AND a.status != 'completed')"""
    elif status:
        query += " AND o.status = ?"
        params.append(status)

    count = db.execute(f"SELECT COUNT(*) FROM ({query})", params).fetchone()[0]
    offset = (page - 1) * per_page
    query += " ORDER BY o.id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    orders = db.execute(query, params).fetchall()
    items = []
    for o in orders:
        # 订单商品
        order_items = db.execute("SELECT * FROM order_items WHERE order_id = ?", (o['id'],)).fetchall()
        items_list = [{
            'id': oi['id'], 'product_id': oi['product_id'], 'product_name': oi['product_name'],
            'product_image': oi['product_image'], 'quantity': oi['quantity'],
            'unit_price': oi['unit_price'], 'specs': oi['specs']
        } for oi in order_items]

        # 配送
        delivery = db.execute("SELECT * FROM delivery_records WHERE order_id = ? ORDER BY id DESC LIMIT 1",
                              (o['id'],)).fetchone()
        delivery_info = None
        if delivery:
            delivery_info = {
                'id': delivery['id'], 'express_company': delivery['express_company'],
                'tracking_number': delivery['tracking_number'], 'status': delivery['status'],
                'shipped_at': delivery['shipped_at'], 'delivered_at': delivery['delivered_at']
            }

        # 评价
        review = db.execute("SELECT * FROM order_reviews WHERE order_id = ?", (o['id'],)).fetchone()
        review_info = None
        if review:
            review_info = {
                'id': review['id'], 'rating': review['rating'], 'content': review['content'],
                'images': json.loads(review['images'] or '[]'),
                'reply': review['reply'], 'created_at': review['created_at']
            }

        # 售后
        after_sale = db.execute("SELECT * FROM after_sales WHERE order_id = ? ORDER BY id DESC LIMIT 1",
                                (o['id'],)).fetchone()
        after_sale_info = None
        if after_sale:
            after_sale_info = {
                'id': after_sale['id'], 'type': after_sale['type'], 'reason': after_sale['reason'],
                'status': after_sale['status'], 'amount': after_sale['amount'],
                'handler_note': after_sale['handler_note'], 'created_at': after_sale['created_at']
            }

        status_map = {
            'pending_payment': '待付款', 'paid': '待发货',
            'shipped': '待收货', 'completed': '已完成', 'cancelled': '已取消'
        }

        items.append({
            'id': o['id'], 'order_no': o['order_no'],
            'total_amount': o['total_amount'], 'actual_amount': o['actual_amount'],
            'status': o['status'], 'status_label': status_map.get(o['status'], o['status']),
            'items': items_list, 'delivery': delivery_info,
            'review': review_info, 'after_sale': after_sale_info,
            'shipping_address': o['shipping_address'],
            'receiver_name': o['receiver_name'], 'receiver_phone': o['receiver_phone'],
            'payment_method': o['payment_method'],
            'created_at': o['created_at']
        })

    return jsonify({
        'success': True,
        'data': {'items': items, 'total': count, 'page': page, 'per_page': per_page}
    })


# ============================================================
# 分类 API
# ============================================================

@app.route('/api/categories', methods=['GET'])
def api_categories():
    db = get_db()
    cats = db.execute("SELECT c.*, (SELECT COUNT(*) FROM products WHERE category_id=c.id AND status='active') as product_count FROM categories c ORDER BY c.sort_order").fetchall()
    items = [{'id': c['id'], 'name': c['name'], 'sort_order': c['sort_order'], 'product_count': c['product_count']} for c in cats]
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/categories', methods=['POST'])
@admin_required
def api_add_category():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': '分类名称不能为空'})
    if len(name) > 20:
        return jsonify({'success': False, 'message': '分类名称最多20个字'})
    db = get_db()
    existing = db.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    if existing:
        return jsonify({'success': False, 'message': '该分类已存在'})
    max_order = db.execute("SELECT COALESCE(MAX(sort_order), -1) FROM categories").fetchone()[0]
    db.execute("INSERT INTO categories (name, sort_order) VALUES (?, ?)", (name, max_order + 1))
    db.commit()
    return jsonify({'success': True, 'message': f'分类「{name}」已添加', 'data': {'id': db.execute("SELECT last_insert_rowid()").fetchone()[0]}})


@app.route('/api/admin/categories/<int:cat_id>', methods=['PUT'])
@admin_required
def api_update_category(cat_id):
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': '分类名称不能为空'})
    db = get_db()
    cat = db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if not cat:
        return jsonify({'success': False, 'message': '分类不存在'}), 404
    existing = db.execute("SELECT id FROM categories WHERE name = ? AND id != ?", (name, cat_id)).fetchone()
    if existing:
        return jsonify({'success': False, 'message': '该分类名称已被占用'})
    db.execute("UPDATE categories SET name = ?, sort_order = ? WHERE id = ?",
               (name, data.get('sort_order', cat['sort_order']), cat_id))
    db.commit()
    return jsonify({'success': True, 'message': f'分类已更新为「{name}」'})


@app.route('/api/admin/categories/<int:cat_id>', methods=['DELETE'])
@admin_required
def api_delete_category(cat_id):
    db = get_db()
    cat = db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if not cat:
        return jsonify({'success': False, 'message': '分类不存在'}), 404
    db.execute("UPDATE products SET category_id = NULL WHERE category_id = ?", (cat_id,))
    db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    db.commit()
    return jsonify({'success': True, 'message': f'分类「{cat["name"]}」已删除'})


# ============================================================
# 品牌 API
# ============================================================

@app.route('/api/brands', methods=['GET'])
def api_brands():
    db = get_db()
    brands = db.execute("SELECT * FROM brands WHERE status='active' ORDER BY sort_order").fetchall()
    items = [{'id': b['id'], 'name': b['name'], 'logo': b['logo'], 'description': b['description'],
              'sort_order': b['sort_order']} for b in brands]
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/brands', methods=['GET'])
@admin_required
def api_admin_brands():
    db = get_db()
    brands = db.execute("""
        SELECT b.*, (SELECT COUNT(*) FROM products WHERE brand_id=b.id AND status!='deleted') as product_count
        FROM brands b ORDER BY b.sort_order
    """).fetchall()
    items = [{'id': b['id'], 'name': b['name'], 'logo': b['logo'], 'description': b['description'],
              'sort_order': b['sort_order'], 'status': b['status'], 'product_count': b['product_count'],
              'created_at': b['created_at']} for b in brands]
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/brands', methods=['POST'])
@admin_required
def api_add_brand():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': '品牌名称不能为空'})
    db = get_db()
    max_o = db.execute("SELECT COALESCE(MAX(sort_order), -1) FROM brands").fetchone()[0]
    db.execute("INSERT INTO brands (name, logo, description, sort_order) VALUES (?, ?, ?, ?)",
               (name, data.get('logo', ''), data.get('description', ''), max_o + 1))
    db.commit()
    return jsonify({'success': True, 'message': '品牌已添加'})


@app.route('/api/admin/brands/<int:brand_id>', methods=['PUT'])
@admin_required
def api_update_brand(brand_id):
    data = request.get_json()
    db = get_db()
    b = db.execute("SELECT * FROM brands WHERE id = ?", (brand_id,)).fetchone()
    if not b:
        return jsonify({'success': False, 'message': '品牌不存在'}), 404
    db.execute("UPDATE brands SET name=?, logo=?, description=?, sort_order=? WHERE id=?",
               (data.get('name', b['name']), data.get('logo', b['logo']),
                data.get('description', b['description']),
                data.get('sort_order', b['sort_order']), brand_id))
    db.commit()
    return jsonify({'success': True, 'message': '品牌已更新'})


@app.route('/api/admin/brands/<int:brand_id>', methods=['DELETE'])
@admin_required
def api_delete_brand(brand_id):
    db = get_db()
    db.execute("UPDATE products SET brand_id = NULL WHERE brand_id = ?", (brand_id,))
    db.execute("DELETE FROM brands WHERE id = ?", (brand_id,))
    db.commit()
    return jsonify({'success': True, 'message': '品牌已删除'})


# ============================================================
# 商品合集 API
# ============================================================

@app.route('/api/admin/collections', methods=['GET'])
@admin_required
def api_collections():
    db = get_db()
    cols = db.execute("SELECT * FROM product_collections ORDER BY id DESC").fetchall()
    items = []
    for c in cols:
        product_ids = json.loads(c['product_ids'] or '[]')
        items.append({
            'id': c['id'], 'name': c['name'], 'description': c['description'],
            'cover_image': c['cover_image'], 'product_ids': product_ids,
            'product_count': len(product_ids), 'status': c['status'], 'created_at': c['created_at']
        })
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/collections', methods=['POST'])
@admin_required
def api_add_collection():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': '合集名称不能为空'})
    db = get_db()
    db.execute("INSERT INTO product_collections (name, description, cover_image, product_ids) VALUES (?, ?, ?, ?)",
               (name, data.get('description', ''), data.get('cover_image', ''),
                json.dumps(data.get('product_ids', []), ensure_ascii=False)))
    db.commit()
    return jsonify({'success': True, 'message': '合集已创建'})


@app.route('/api/admin/collections/<int:col_id>', methods=['PUT'])
@admin_required
def api_update_collection(col_id):
    data = request.get_json()
    db = get_db()
    c = db.execute("SELECT * FROM product_collections WHERE id = ?", (col_id,)).fetchone()
    if not c:
        return jsonify({'success': False, 'message': '合集不存在'}), 404
    db.execute("UPDATE product_collections SET name=?, description=?, cover_image=?, product_ids=?, status=? WHERE id=?",
               (data.get('name', c['name']), data.get('description', c['description']),
                data.get('cover_image', c['cover_image']),
                json.dumps(data.get('product_ids', json.loads(c['product_ids'] or '[]')), ensure_ascii=False),
                data.get('status', c['status']), col_id))
    db.commit()
    return jsonify({'success': True, 'message': '合集已更新'})


@app.route('/api/admin/collections/<int:col_id>', methods=['DELETE'])
@admin_required
def api_delete_collection(col_id):
    db = get_db()
    db.execute("DELETE FROM product_collections WHERE id = ?", (col_id,))
    db.commit()
    return jsonify({'success': True, 'message': '合集已删除'})


# ============================================================
# 公告管理 API
# ============================================================

@app.route('/api/announcements', methods=['GET'])
def api_announcements_public():
    db = get_db()
    anns = db.execute("SELECT * FROM announcements WHERE status='published' ORDER BY is_pinned DESC, id DESC LIMIT 10").fetchall()
    items = [{'id': a['id'], 'title': a['title'], 'content': a['content'],
              'is_pinned': a['is_pinned'], 'created_at': a['created_at']} for a in anns]
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/announcements', methods=['GET'])
@admin_required
def api_admin_announcements():
    db = get_db()
    anns = db.execute("SELECT * FROM announcements ORDER BY is_pinned DESC, id DESC").fetchall()
    items = [{'id': a['id'], 'title': a['title'], 'content': a['content'],
              'is_pinned': a['is_pinned'], 'status': a['status'],
              'created_at': a['created_at'], 'updated_at': a['updated_at']} for a in anns]
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/announcements', methods=['POST'])
@admin_required
def api_add_announcement():
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({'success': False, 'message': '标题不能为空'})
    db = get_db()
    db.execute("INSERT INTO announcements (title, content, is_pinned, status) VALUES (?, ?, ?, ?)",
               (title, data.get('content', ''), 1 if data.get('is_pinned') else 0, data.get('status', 'published')))
    db.commit()
    return jsonify({'success': True, 'message': '公告已发布'})


@app.route('/api/admin/announcements/<int:ann_id>', methods=['PUT'])
@admin_required
def api_update_announcement(ann_id):
    data = request.get_json()
    db = get_db()
    a = db.execute("SELECT * FROM announcements WHERE id = ?", (ann_id,)).fetchone()
    if not a:
        return jsonify({'success': False, 'message': '公告不存在'}), 404
    db.execute("UPDATE announcements SET title=?, content=?, is_pinned=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
               (data.get('title', a['title']), data.get('content', a['content']),
                1 if data.get('is_pinned') else 0, data.get('status', a['status']), ann_id))
    db.commit()
    return jsonify({'success': True, 'message': '公告已更新'})


@app.route('/api/admin/announcements/<int:ann_id>', methods=['DELETE'])
@admin_required
def api_delete_announcement(ann_id):
    db = get_db()
    db.execute("DELETE FROM announcements WHERE id = ?", (ann_id,))
    db.commit()
    return jsonify({'success': True, 'message': '公告已删除'})


# ============================================================
# 平台活动 API
# ============================================================

@app.route('/api/admin/activities', methods=['GET'])
@admin_required
def api_activities():
    db = get_db()
    acts = db.execute("SELECT * FROM platform_activities ORDER BY id DESC").fetchall()
    items = [{'id': a['id'], 'title': a['title'], 'description': a['description'],
              'banner_image': a['banner_image'], 'start_time': a['start_time'],
              'end_time': a['end_time'], 'status': a['status'], 'created_at': a['created_at']} for a in acts]
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/activities', methods=['POST'])
@admin_required
def api_add_activity():
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({'success': False, 'message': '活动标题不能为空'})
    db = get_db()
    db.execute("INSERT INTO platform_activities (title, description, banner_image, start_time, end_time) VALUES (?, ?, ?, ?, ?)",
               (title, data.get('description', ''), data.get('banner_image', ''),
                data.get('start_time', ''), data.get('end_time', '')))
    db.commit()
    return jsonify({'success': True, 'message': '活动已创建'})


@app.route('/api/admin/activities/<int:act_id>', methods=['PUT'])
@admin_required
def api_update_activity(act_id):
    data = request.get_json()
    db = get_db()
    a = db.execute("SELECT * FROM platform_activities WHERE id = ?", (act_id,)).fetchone()
    if not a:
        return jsonify({'success': False, 'message': '活动不存在'}), 404
    db.execute("""UPDATE platform_activities SET title=?, description=?, banner_image=?,
        start_time=?, end_time=?, status=? WHERE id=?""",
               (data.get('title', a['title']), data.get('description', a['description']),
                data.get('banner_image', a['banner_image']), data.get('start_time', a['start_time']),
                data.get('end_time', a['end_time']), data.get('status', a['status']), act_id))
    db.commit()
    return jsonify({'success': True, 'message': '活动已更新'})


@app.route('/api/admin/activities/<int:act_id>', methods=['DELETE'])
@admin_required
def api_delete_activity(act_id):
    db = get_db()
    db.execute("DELETE FROM platform_activities WHERE id = ?", (act_id,))
    db.commit()
    return jsonify({'success': True, 'message': '活动已删除'})


# ============================================================
# 店铺主页模块 API
# ============================================================

@app.route('/api/admin/store-blocks', methods=['GET'])
@admin_required
def api_store_blocks():
    db = get_db()
    blocks = db.execute("SELECT * FROM store_page_blocks ORDER BY sort_order").fetchall()
    items = [{'id': b['id'], 'block_type': b['block_type'], 'title': b['title'],
              'config': json.loads(b['config'] or '{}'), 'sort_order': b['sort_order'],
              'status': b['status']} for b in blocks]
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/store-blocks', methods=['POST'])
@admin_required
def api_add_store_block():
    data = request.get_json()
    db = get_db()
    max_o = db.execute("SELECT COALESCE(MAX(sort_order), -1) FROM store_page_blocks").fetchone()[0]
    db.execute("INSERT INTO store_page_blocks (block_type, title, config, sort_order) VALUES (?, ?, ?, ?)",
               (data.get('block_type', 'banner'), data.get('title', ''),
                json.dumps(data.get('config', {}), ensure_ascii=False), max_o + 1))
    db.commit()
    return jsonify({'success': True, 'message': '模块已添加'})


@app.route('/api/admin/store-blocks/<int:block_id>', methods=['PUT'])
@admin_required
def api_update_store_block(block_id):
    data = request.get_json()
    db = get_db()
    b = db.execute("SELECT * FROM store_page_blocks WHERE id = ?", (block_id,)).fetchone()
    if not b:
        return jsonify({'success': False, 'message': '模块不存在'}), 404
    db.execute("UPDATE store_page_blocks SET block_type=?, title=?, config=?, sort_order=?, status=? WHERE id=?",
               (data.get('block_type', b['block_type']), data.get('title', b['title']),
                json.dumps(data.get('config', json.loads(b['config'] or '{}')), ensure_ascii=False),
                data.get('sort_order', b['sort_order']), data.get('status', b['status']), block_id))
    db.commit()
    return jsonify({'success': True, 'message': '模块已更新'})


@app.route('/api/admin/store-blocks/<int:block_id>', methods=['DELETE'])
@admin_required
def api_delete_store_block(block_id):
    db = get_db()
    db.execute("DELETE FROM store_page_blocks WHERE id = ?", (block_id,))
    db.commit()
    return jsonify({'success': True, 'message': '模块已删除'})


# ============================================================
# 客户管理 API
# ============================================================

@app.route('/api/customers', methods=['GET'])
@admin_required
def api_customers():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    keyword = request.args.get('keyword', '')

    query = "SELECT * FROM customers WHERE 1=1"
    params = []
    if keyword:
        query += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)"
        k = f'%{keyword}%'
        params.extend([k, k, k])

    count = db.execute(f"SELECT COUNT(*) FROM ({query})", params).fetchone()[0]
    offset = (page - 1) * per_page
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    customers = db.execute(query, params).fetchall()
    items = [{
        'id': c['id'], 'name': c['name'], 'phone': c['phone'], 'email': c['email'],
        'wechat_id': c['wechat_id'], 'address': c['address'], 'city': c['city'],
        'total_orders': c['total_orders'], 'total_spent': c['total_spent'],
        'source': c['source'], 'tags': json.loads(c['tags'] or '[]'),
        'notes': c['notes'], 'created_at': c['created_at']
    } for c in customers]

    return jsonify({
        'success': True,
        'data': {'items': items, 'total': count, 'page': page, 'per_page': per_page}
    })


@app.route('/api/customers', methods=['POST'])
@admin_required
def api_add_customer():
    data = request.get_json()
    phone = data.get('phone', '').strip()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()

    # 手机号必填
    if not phone:
        return jsonify({'success': False, 'message': '手机号为必填项'})
    if not re.match(r'^1[3-9]\d{9}$', phone):
        return jsonify({'success': False, 'message': '请输入正确的手机号'})

    db = get_db()

    # 创建用户账号（密码默认为手机号后4位）
    default_password = phone[-4:]
    password_hash = hashlib.sha256(default_password.encode()).hexdigest()

    # 检查用户是否已存在
    existing_user = db.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
    if not existing_user:
        # 用户名用手机号
        username = phone
        counter = 1
        while db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            username = f"{phone}_{counter}"
            counter += 1
        db.execute(
            "INSERT INTO users (username, password_hash, display_name, role, phone, email) VALUES (?, ?, ?, ?, ?, ?)",
            (username, password_hash, name or phone, 'customer', phone, email))
    elif email:
        # 如果用户已存在但有新邮箱，更新邮箱
        db.execute("UPDATE users SET email = ? WHERE phone = ?", (email, phone))

    # 检查客户是否已存在
    existing_customer = db.execute("SELECT id FROM customers WHERE phone = ?", (phone,)).fetchone()
    if existing_customer:
        # 更新已有客户信息
        db.execute("""
            UPDATE customers SET name=?, email=?, wechat_id=?, address=?, city=?,
            tags=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE phone=?
        """, (name, email,
              data.get('wechat_id', ''), data.get('address', ''), data.get('city', ''),
              json.dumps(data.get('tags', []), ensure_ascii=False), data.get('notes', ''),
              phone))
        db.commit()
        return jsonify({'success': True, 'message': '客户已存在，信息已更新；密码为手机号后4位'})

    # 新增客户
    db.execute("""
        INSERT INTO customers (name, phone, email, wechat_id, address, city, source, tags, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, phone, email,
          data.get('wechat_id', ''), data.get('address', ''), data.get('city', ''),
          data.get('source', '手动添加'), json.dumps(data.get('tags', []), ensure_ascii=False),
          data.get('notes', '')))
    db.commit()
    return jsonify({'success': True, 'message': '客户添加成功！账号为手机号，密码为手机号后4位'})


@app.route('/api/customers/<int:customer_id>', methods=['PUT'])
@admin_required
def api_update_customer(customer_id):
    data = request.get_json()
    db = get_db()
    db.execute("""
        UPDATE customers SET name=?, phone=?, email=?, wechat_id=?, address=?, city=?,
        tags=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?
    """, (data.get('name', ''), data.get('phone', ''), data.get('email', ''),
          data.get('wechat_id', ''), data.get('address', ''), data.get('city', ''),
          json.dumps(data.get('tags', []), ensure_ascii=False), data.get('notes', ''),
          customer_id))
    db.commit()
    return jsonify({'success': True, 'message': '客户信息更新成功'})


@app.route('/api/customers/<int:customer_id>', methods=['DELETE'])
@admin_required
def api_delete_customer(customer_id):
    db = get_db()
    db.execute("DELETE FROM customers WHERE id=?", (customer_id,))
    db.commit()
    return jsonify({'success': True, 'message': '客户已删除'})


# ============================================================
# 订单管理 API
# ============================================================

@app.route('/api/orders', methods=['GET'])
@admin_required
def api_orders():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', '')
    keyword = request.args.get('keyword', '')

    query = """
        SELECT o.*, c.name as customer_name, c.phone as customer_phone
        FROM orders o LEFT JOIN customers c ON o.customer_id = c.id WHERE 1=1
    """
    params = []
    if status:
        query += " AND o.status = ?"
        params.append(status)
    if keyword:
        query += " AND (o.order_no LIKE ? OR c.name LIKE ? OR c.phone LIKE ?)"
        k = f'%{keyword}%'
        params.extend([k, k, k])

    count = db.execute(f"SELECT COUNT(*) FROM ({query})", params).fetchone()[0]
    offset = (page - 1) * per_page
    query += " ORDER BY o.id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    orders = db.execute(query, params).fetchall()
    items = []
    for o in orders:
        order_items = db.execute("SELECT * FROM order_items WHERE order_id = ?", (o['id'],)).fetchall()
        items_list = [{
            'id': oi['id'], 'product_id': oi['product_id'], 'product_name': oi['product_name'],
            'product_image': oi['product_image'], 'quantity': oi['quantity'],
            'unit_price': oi['unit_price'], 'specs': oi['specs']
        } for oi in order_items]

        # 配送信息
        delivery = db.execute("SELECT * FROM delivery_records WHERE order_id = ? ORDER BY id DESC LIMIT 1", (o['id'],)).fetchone()
        delivery_info = None
        if delivery:
            delivery_info = {
                'id': delivery['id'], 'express_company': delivery['express_company'],
                'tracking_number': delivery['tracking_number'], 'status': delivery['status'],
                'shipped_at': delivery['shipped_at'], 'delivered_at': delivery['delivered_at']
            }

        # 评价信息
        review = db.execute("SELECT * FROM order_reviews WHERE order_id = ?", (o['id'],)).fetchone()
        review_info = None
        if review:
            review_info = {
                'id': review['id'], 'rating': review['rating'], 'content': review['content'],
                'images': json.loads(review['images'] or '[]'), 'reply': review['reply'],
                'created_at': review['created_at']
            }

        items.append({
            'id': o['id'], 'order_no': o['order_no'],
            'customer_name': o['customer_name'], 'customer_phone': o['customer_phone'],
            'total_amount': o['total_amount'], 'actual_amount': o['actual_amount'],
            'status': o['status'], 'items': items_list,
            'shipping_address': o['shipping_address'],
            'receiver_name': o['receiver_name'], 'receiver_phone': o['receiver_phone'],
            'payment_method': o['payment_method'],
            'delivery': delivery_info,
            'review': review_info,
            'created_at': o['created_at']
        })

    status_counts = {}
    for s in ['pending_payment', 'paid', 'shipped', 'completed', 'cancelled']:
        status_counts[s] = db.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (s,)).fetchone()[0]

    return jsonify({
        'success': True,
        'data': {'items': items, 'total': count, 'page': page, 'per_page': per_page, 'status_counts': status_counts}
    })


@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
@admin_required
def api_update_order_status(order_id):
    data = request.get_json()
    new_status = data.get('status')
    valid = ['pending_payment', 'paid', 'shipped', 'completed', 'cancelled']
    if new_status not in valid:
        return jsonify({'success': False, 'message': '无效的订单状态'})
    db = get_db()
    db.execute("UPDATE orders SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_status, order_id))
    if new_status == 'paid':
        db.execute("UPDATE orders SET payment_time=CURRENT_TIMESTAMP WHERE id=?", (order_id,))
    db.commit()
    return jsonify({'success': True, 'message': '订单状态已更新'})


# ============================================================
# 配送管理 API
# ============================================================

@app.route('/api/admin/deliveries', methods=['GET'])
@admin_required
def api_deliveries():
    db = get_db()
    records = db.execute("""
        SELECT d.*, o.order_no, c.name as customer_name
        FROM delivery_records d
        LEFT JOIN orders o ON d.order_id = o.id
        LEFT JOIN customers c ON o.customer_id = c.id
        ORDER BY d.id DESC
    """).fetchall()
    items = [{
        'id': d['id'], 'order_id': d['order_id'], 'order_no': d['order_no'],
        'customer_name': d['customer_name'], 'express_company': d['express_company'],
        'tracking_number': d['tracking_number'], 'status': d['status'],
        'shipped_at': d['shipped_at'], 'delivered_at': d['delivered_at'],
        'notes': d['notes'], 'created_at': d['created_at']
    } for d in records]
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/deliveries', methods=['POST'])
@admin_required
def api_add_delivery():
    data = request.get_json()
    order_id = data.get('order_id')
    if not order_id:
        return jsonify({'success': False, 'message': '请选择订单'})
    db = get_db()

    # 更新订单状态为已发货
    db.execute("UPDATE orders SET status='shipped', updated_at=CURRENT_TIMESTAMP WHERE id=?", (order_id,))

    db.execute("""
        INSERT INTO delivery_records (order_id, express_company, tracking_number, status, shipped_at, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (order_id, data.get('express_company', ''), data.get('tracking_number', ''),
          data.get('status', 'shipping'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
          data.get('notes', '')))
    db.commit()
    return jsonify({'success': True, 'message': '配送信息已录入，订单已发货'})


@app.route('/api/admin/deliveries/<int:delivery_id>', methods=['PUT'])
@admin_required
def api_update_delivery(delivery_id):
    data = request.get_json()
    db = get_db()
    d = db.execute("SELECT * FROM delivery_records WHERE id = ?", (delivery_id,)).fetchone()
    if not d:
        return jsonify({'success': False, 'message': '配送记录不存在'}), 404

    updates = []
    params = []
    for field in ['express_company', 'tracking_number', 'status', 'notes']:
        if field in data:
            updates.append(f"{field}=?")
            params.append(data[field])
    if data.get('status') == 'delivered':
        updates.append("delivered_at=?")
        params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    if updates:
        params.append(delivery_id)
        db.execute(f"UPDATE delivery_records SET {', '.join(updates)} WHERE id=?", params)
        # 如果已签收，同步更新订单状态
        if data.get('status') == 'delivered':
            db.execute("UPDATE orders SET status='completed', updated_at=CURRENT_TIMESTAMP WHERE id=?", (d['order_id'],))
        db.commit()

    return jsonify({'success': True, 'message': '配送信息已更新'})


# ============================================================
# 快递地址 API
# ============================================================

@app.route('/api/admin/shipping-addresses', methods=['GET'])
@admin_required
def api_shipping_addresses():
    db = get_db()
    addrs = db.execute("SELECT * FROM shipping_addresses ORDER BY is_default DESC, id DESC").fetchall()
    items = [{
        'id': a['id'], 'name': a['name'], 'phone': a['phone'],
        'province': a['province'], 'city': a['city'], 'district': a['district'],
        'address': a['address'], 'is_default': a['is_default'], 'address_type': a['address_type'],
        'created_at': a['created_at']
    } for a in addrs]
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/shipping-addresses', methods=['POST'])
@admin_required
def api_add_shipping_address():
    data = request.get_json()
    if not data.get('name') or not data.get('phone') or not data.get('address'):
        return jsonify({'success': False, 'message': '请填写完整信息'})
    db = get_db()
    if data.get('is_default'):
        db.execute("UPDATE shipping_addresses SET is_default=0")
    db.execute("""
        INSERT INTO shipping_addresses (name, phone, province, city, district, address, is_default, address_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (data['name'], data['phone'], data.get('province', ''), data.get('city', ''),
          data.get('district', ''), data['address'], 1 if data.get('is_default') else 0,
          data.get('address_type', 'return')))
    db.commit()
    return jsonify({'success': True, 'message': '地址已添加'})


@app.route('/api/admin/shipping-addresses/<int:addr_id>', methods=['PUT'])
@admin_required
def api_update_shipping_address(addr_id):
    data = request.get_json()
    db = get_db()
    a = db.execute("SELECT * FROM shipping_addresses WHERE id = ?", (addr_id,)).fetchone()
    if not a:
        return jsonify({'success': False, 'message': '地址不存在'}), 404
    if data.get('is_default'):
        db.execute("UPDATE shipping_addresses SET is_default=0")
    db.execute("""
        UPDATE shipping_addresses SET name=?, phone=?, province=?, city=?, district=?,
        address=?, is_default=?, address_type=? WHERE id=?
    """, (data.get('name', a['name']), data.get('phone', a['phone']),
          data.get('province', a['province']), data.get('city', a['city']),
          data.get('district', a['district']), data.get('address', a['address']),
          1 if data.get('is_default') else 0, data.get('address_type', a['address_type']), addr_id))
    db.commit()
    return jsonify({'success': True, 'message': '地址已更新'})


@app.route('/api/admin/shipping-addresses/<int:addr_id>', methods=['DELETE'])
@admin_required
def api_delete_shipping_address(addr_id):
    db = get_db()
    db.execute("DELETE FROM shipping_addresses WHERE id = ?", (addr_id,))
    db.commit()
    return jsonify({'success': True, 'message': '地址已删除'})


# ============================================================
# 订单评价 API
# ============================================================

@app.route('/api/admin/reviews', methods=['GET'])
@admin_required
def api_reviews():
    db = get_db()
    reviews = db.execute("""
        SELECT r.*, o.order_no, c.name as customer_name
        FROM order_reviews r
        LEFT JOIN orders o ON r.order_id = o.id
        LEFT JOIN customers c ON r.customer_id = c.id
        ORDER BY r.id DESC
    """).fetchall()
    items = [{
        'id': r['id'], 'order_id': r['order_id'], 'order_no': r['order_no'],
        'customer_name': r['customer_name'], 'rating': r['rating'],
        'content': r['content'], 'images': json.loads(r['images'] or '[]'),
        'reply': r['reply'], 'reply_at': r['reply_at'], 'created_at': r['created_at']
    } for r in reviews]
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/reviews/<int:review_id>/reply', methods=['PUT'])
@admin_required
def api_reply_review(review_id):
    data = request.get_json()
    db = get_db()
    db.execute("UPDATE order_reviews SET reply=?, reply_at=CURRENT_TIMESTAMP WHERE id=?",
               (data.get('reply', ''), review_id))
    db.commit()
    return jsonify({'success': True, 'message': '已回复'})


# ============================================================
# 售后管理 API
# ============================================================

@app.route('/api/admin/after-sales', methods=['GET'])
@admin_required
def api_after_sales():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', '')
    as_type = request.args.get('type', '')

    query = """
        SELECT a.*, o.order_no, c.name as customer_name, c.phone as customer_phone
        FROM after_sales a
        LEFT JOIN orders o ON a.order_id = o.id
        LEFT JOIN customers c ON a.customer_id = c.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND a.status = ?"
        params.append(status)
    if as_type:
        query += " AND a.type = ?"
        params.append(as_type)

    count = db.execute(f"SELECT COUNT(*) FROM ({query})", params).fetchone()[0]
    offset = (page - 1) * per_page
    query += " ORDER BY a.id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    records = db.execute(query, params).fetchall()
    items = [{
        'id': a['id'], 'order_id': a['order_id'], 'order_no': a['order_no'],
        'customer_name': a['customer_name'], 'customer_phone': a['customer_phone'],
        'type': a['type'], 'reason': a['reason'], 'description': a['description'],
        'images': json.loads(a['images'] or '[]'), 'amount': a['amount'],
        'status': a['status'], 'handler_note': a['handler_note'], 'result': a['result'],
        'created_at': a['created_at'], 'updated_at': a['updated_at']
    } for a in records]

    # 统计
    stats = {}
    for s in ['pending', 'processing', 'completed', 'rejected']:
        stats[s] = db.execute("SELECT COUNT(*) FROM after_sales WHERE status = ?", (s,)).fetchone()[0]

    return jsonify({
        'success': True,
        'data': {'items': items, 'total': count, 'page': page, 'per_page': per_page, 'stats': stats}
    })


@app.route('/api/admin/after-sales/<int:as_id>', methods=['PUT'])
@admin_required
def api_handle_after_sale(as_id):
    data = request.get_json()
    db = get_db()
    a = db.execute("SELECT * FROM after_sales WHERE id = ?", (as_id,)).fetchone()
    if not a:
        return jsonify({'success': False, 'message': '售后单不存在'}), 404
    db.execute("""UPDATE after_sales SET status=?, handler_note=?, result=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
               (data.get('status', a['status']), data.get('handler_note', ''),
                data.get('result', ''), as_id))
    db.commit()
    return jsonify({'success': True, 'message': '处理成功'})


# ============================================================
# 申诉管理 API
# ============================================================

@app.route('/api/admin/appeals', methods=['GET'])
@admin_required
def api_appeals():
    db = get_db()
    appeals = db.execute("""
        SELECT ap.*, a.order_id, o.order_no, c.name as customer_name
        FROM appeals ap
        LEFT JOIN after_sales a ON ap.after_sale_id = a.id
        LEFT JOIN orders o ON a.order_id = o.id
        LEFT JOIN customers c ON ap.customer_id = c.id
        ORDER BY ap.id DESC
    """).fetchall()
    items = [{
        'id': ap['id'], 'after_sale_id': ap['after_sale_id'], 'order_no': ap['order_no'],
        'customer_name': ap['customer_name'], 'reason': ap['reason'],
        'description': ap['description'], 'images': json.loads(ap['images'] or '[]'),
        'status': ap['status'], 'handler_note': ap['handler_note'],
        'result': ap['result'], 'created_at': ap['created_at']
    } for ap in appeals]
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/appeals/<int:appeal_id>', methods=['PUT'])
@admin_required
def api_handle_appeal(appeal_id):
    data = request.get_json()
    db = get_db()
    ap = db.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,)).fetchone()
    if not ap:
        return jsonify({'success': False, 'message': '申诉不存在'}), 404
    db.execute("""UPDATE appeals SET status=?, handler_note=?, result=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
               (data.get('status', ap['status']), data.get('handler_note', ''),
                data.get('result', ''), appeal_id))
    db.commit()
    return jsonify({'success': True, 'message': '处理成功'})


# ============================================================
# 成员管理 API
# ============================================================

@app.route('/api/admin/members', methods=['GET'])
@admin_required
def api_members():
    db = get_db()
    members = db.execute("SELECT id, username, display_name, role, phone, email, store_role, avatar, status, created_at, last_login FROM users WHERE role='admin' OR store_role!='' ORDER BY id").fetchall()
    items = [{
        'id': m['id'], 'username': m['username'], 'display_name': m['display_name'],
        'role': m['role'], 'phone': m['phone'], 'email': m['email'],
        'store_role': m['store_role'], 'avatar': m['avatar'], 'status': m['status'],
        'created_at': m['created_at'], 'last_login': m['last_login']
    } for m in members]
    return jsonify({'success': True, 'data': items})


@app.route('/api/admin/members', methods=['POST'])
@admin_required
def api_add_member():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'})
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        return jsonify({'success': False, 'message': '用户名已存在'})
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    db.execute("""
        INSERT INTO users (username, password_hash, display_name, role, phone, email, store_role)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (username, password_hash, data.get('display_name', username), 'admin',
          data.get('phone', ''), data.get('email', ''), data.get('store_role', 'staff')))
    db.commit()
    return jsonify({'success': True, 'message': '成员已添加'})


@app.route('/api/admin/members/<int:member_id>', methods=['PUT'])
@admin_required
def api_update_member(member_id):
    data = request.get_json()
    db = get_db()
    m = db.execute("SELECT * FROM users WHERE id = ? AND (role='admin' OR store_role!='')", (member_id,)).fetchone()
    if not m:
        return jsonify({'success': False, 'message': '成员不存在'}), 404

    updates = []
    params = []
    for field in ['display_name', 'phone', 'email', 'store_role', 'status']:
        if field in data:
            updates.append(f"{field}=?")
            params.append(data[field])
    if data.get('password'):
        updates.append("password_hash=?")
        params.append(hashlib.sha256(data['password'].encode()).hexdigest())
    if updates:
        params.append(member_id)
        db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=?", params)
        db.commit()
    return jsonify({'success': True, 'message': '成员已更新'})


@app.route('/api/admin/members/<int:member_id>', methods=['DELETE'])
@admin_required
def api_delete_member(member_id):
    db = get_db()
    m = db.execute("SELECT * FROM users WHERE id = ? AND (role='admin' OR store_role!='')", (member_id,)).fetchone()
    if not m or m['role'] == 'admin' and m['username'] == 'admin':
        return jsonify({'success': False, 'message': '不能删除超级管理员'})
    db.execute("UPDATE users SET status='inactive' WHERE id = ?", (member_id,))
    db.commit()
    return jsonify({'success': True, 'message': '成员已停用'})


# ============================================================
# 支付接口 (预留)
# ============================================================

@app.route('/api/payment/create', methods=['POST'])
def api_payment_create():
    return jsonify({
        'success': True,
        'message': '支付接口预留 — 待接入微信支付/支付宝',
        'data': {'payment_id': f'PAY{int(time.time())}', 'amount': 0, 'status': 'unimplemented',
                 'methods_planned': ['wechat_pay', 'alipay']}
    })


@app.route('/api/payment/callback', methods=['POST'])
def api_payment_callback():
    return jsonify({'success': True, 'message': '支付回调接口预留'})


# ============================================================
# 商城设置 API
# ============================================================

@app.route('/api/settings', methods=['GET'])
def api_settings():
    db = get_db()
    settings = db.execute("SELECT * FROM store_settings").fetchall()
    result = {}
    for s in settings:
        result[s['key']] = s['value']
    return jsonify({'success': True, 'data': result})


@app.route('/api/settings', methods=['PUT'])
@admin_required
def api_update_settings():
    data = request.get_json()
    db = get_db()
    for k, v in data.items():
        existing = db.execute("SELECT * FROM store_settings WHERE key = ?", (k,)).fetchone()
        if existing:
            db.execute("UPDATE store_settings SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key=?", (str(v), k))
        else:
            db.execute("INSERT INTO store_settings (key, value) VALUES (?, ?)", (k, str(v)))
    db.commit()
    return jsonify({'success': True, 'message': '设置已保存'})


@app.route('/api/upload', methods=['POST'])
@admin_required
def api_upload():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有文件'})
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '文件名为空'})
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']:
        return jsonify({'success': False, 'message': '不支持的图片格式'})
    filename = f"{int(time.time() * 1000)}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    return jsonify({'success': True, 'data': {'url': f'/static/uploads/{filename}'}})


# ============================================================
# 公众号 AI 创作发布平台
# ============================================================

@app.route('/publish')
def publish_page():
    return read_template('publish.html')


@app.route('/api/publish/health', methods=['GET'])
def api_publish_health():
    """健康检查"""
    return jsonify({'success': True, 'status': 'ok'})


@app.route('/api/publish/fetch-url', methods=['POST'])
def api_publish_fetch_url():
    """抓取参考文章链接内容"""
    data = request.get_json()
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'success': False, 'message': '请输入链接'})
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode('utf-8', errors='replace')
        return jsonify({'success': True, 'html': html, 'length': len(html)})
    except Exception as e:
        return jsonify({'success': False, 'message': f'抓取失败: {str(e)}'})


@app.route('/api/publish/analyze-style', methods=['POST'])
def api_publish_analyze_style():
    """分析HTML排版风格"""
    data = request.get_json()
    html = data.get('html', '')
    url = data.get('url', '')
    if not html:
        return jsonify({'success': False, 'message': '请提供HTML内容'})
    try:
        from bs4 import BeautifulSoup
        import re
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # 提取颜色
        colors = set()
        text = html
        hex_colors = re.findall(r'#[0-9a-fA-F]{3,8}', text)
        rgb_colors = re.findall(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', text)
        colors.update(c.upper() for c in hex_colors[:10])
        colors.update(f'rgb({r},{g},{b})' for r,g,b in rgb_colors[:5])
        
        # 提取字体
        fonts = re.findall(r'font-family:\s*([^;"]+)', text)
        
        # 提取字号
        font_sizes = list(set(re.findall(r'font-size:\s*([^;"]+)', text)))
        
        # 格式化profile
        profile = {
            'fonts': list(set(f.strip().replace("'", "").replace('"', '') for f in fonts))[:5],
            'colors': list(colors)[:12],
            'font_sizes': font_sizes[:8],
            'bg_color': '#ffffff',
            'text_color': '#333333',
            'accent_color': list(colors)[0] if colors else '#534ab7',
            'line_height': '1.8',
            'heading_font_size': '18px',
            'body_font_size': '15px',
            'html_length': len(html)
        }
        
        return jsonify({'success': True, 'profile': profile})
    except ImportError:
        return jsonify({'success': False, 'message': 'BeautifulSoup未安装'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'分析失败: {str(e)}'})


@app.route('/api/publish/wechat-status', methods=['GET'])
def api_publish_wechat_status():
    """获取微信发布相关的配置状态"""
    # 从环境变量或store_settings读取微信配置
    db = get_db()
    settings = {}
    for row in db.execute("SELECT key, value FROM store_settings WHERE key LIKE 'wechat_%'").fetchall():
        settings[row['key']] = row['value']
    
    return jsonify({
        'success': True,
        'has_appid': bool(settings.get('wechat_appid', '')),
        'has_appsecret': bool(settings.get('wechat_appsecret', '')),
    })


@app.route('/api/publish/save-wechat-config', methods=['POST'])
def api_publish_save_wechat_config():
    """保存微信配置到store_settings"""
    data = request.get_json()
    db = get_db()
    for k in ['wechat_appid', 'wechat_appsecret', 'wechat_material_base']:
        if k in data and data[k]:
            existing = db.execute("SELECT id FROM store_settings WHERE key=?", (k,)).fetchone()
            if existing:
                db.execute("UPDATE store_settings SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key=?", (str(data[k]), k))
            else:
                db.execute("INSERT INTO store_settings (key, value) VALUES (?, ?)", (k, str(data[k])))
    db.commit()
    return jsonify({'success': True, 'message': '微信配置已保存'})


@app.route('/api/publish/create-draft', methods=['POST'])
def api_publish_create_draft():
    """创建微信公众号草稿"""
    data = request.get_json()
    appid = data.get('appid', '').strip()
    appsecret = data.get('appsecret', '').strip()
    article = data.get('article', {})
    
    if not appid or not appsecret:
        return jsonify({'success': False, 'message': '请先配置微信 AppID 和 AppSecret'})
    
    try:
        import requests
        
        # 1. 获取 access_token
        token_url = 'https://api.weixin.qq.com/cgi-bin/token'
        token_resp = requests.get(token_url, params={
            'grant_type': 'client_credential',
            'appid': appid,
            'secret': appsecret
        }, timeout=15).json()
        
        if 'access_token' not in token_resp:
            return jsonify({'success': False, 'message': f'获取token失败: {token_resp.get("errmsg", token_resp)}'})
        
        access_token = token_resp['access_token']
        
        # 2. 上传封面图 - 自动处理 URL/base64/本地文件，兜底生成占位图
        thumb_media_id = None
        images = data.get('images', [])
        
        def _get_thumb_file():
            import os as _os, base64, uuid
            from PIL import Image
            _os.makedirs('static/uploads', exist_ok=True)
            
            if images and images[0]:
                src = images[0]
                # 本地文件
                if _os.path.exists(src):
                    return src
                # base64 data URL
                if isinstance(src, str) and src.startswith('data:image/'):
                    try:
                        header, b64 = src.split(',', 1)
                        ext = header.split('/')[1].split(';')[0] or 'png'
                        path = _os.path.join('static', 'uploads', f'thb_{uuid.uuid4().hex[:8]}.{ext}')
                        with open(path, 'wb') as fw:
                            fw.write(base64.b64decode(b64))
                        return path
                    except:
                        pass
                # 远程 URL
                if src.startswith('http://') or src.startswith('https://'):
                    try:
                        r = requests.get(src, timeout=15)
                        if r.status_code == 200:
                            path = _os.path.join('static', 'uploads', f'thb_{uuid.uuid4().hex[:8]}.jpg')
                            with open(path, 'wb') as fw:
                                fw.write(r.content)
                            return path
                    except:
                        pass
            
            # 兜底：生成简洁占位封面（带标题文字提示）
            path = _os.path.join('static', 'uploads', f'cover_{uuid.uuid4().hex[:8]}.jpg')
            img = Image.new('RGB', (900, 500), (26, 173, 25))
            try:
                from PIL import ImageDraw, ImageFont
                draw = ImageDraw.Draw(img)
                title = (article.get('title','') or '公众号文章')[:20]
                try:
                    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 36)
                except:
                    font = ImageFont.load_default()
                bbox = draw.textbbox((0,0), title, font=font)
                tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
                draw.text(((900-tw)/2, (500-th)/2), title, fill='white', font=font)
            except:
                pass
            img.save(path, 'JPEG', quality=90)
            return path
        
        thumb_file = _get_thumb_file()
        if thumb_file and os.path.exists(thumb_file):
            upload_url = f'https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image'
            mime = 'image/png' if thumb_file.lower().endswith('.png') else 'image/jpeg'
            with open(thumb_file, 'rb') as f:
                files = {'media': (os.path.basename(thumb_file), f, mime)}
                upload_resp = requests.post(upload_url, files=files, timeout=60).json()
            if 'media_id' in upload_resp:
                thumb_media_id = upload_resp['media_id']
        
        # 3. 创建草稿
        draft_article = {
            'title': article.get('title', ''),
            'author': article.get('author', ''),
            'digest': article.get('digest', ''),
            'content': article.get('content', ''),
            'content_source_url': article.get('content_source_url', ''),
            'need_open_comment': 1,
            'only_fans_can_comment': 0,
        }
        
        if thumb_media_id:
            draft_article['thumb_media_id'] = thumb_media_id
        
        draft_data = json.dumps({'articles': [draft_article]}, ensure_ascii=False).encode('utf-8')
        draft_url = f'https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}'
        draft_resp = requests.post(draft_url, data=draft_data,
                                    headers={'Content-Type': 'application/json; charset=utf-8'},
                                    timeout=30).json()
        
        if 'media_id' not in draft_resp:
            return jsonify({
                'success': False,
                'message': f'创建草稿失败: {draft_resp.get("errmsg", str(draft_resp))}',
                'code': draft_resp.get('errcode', -1)
            })
        
        # 4. 尝试发布（可能失败，取决于认证状态）
        publish_result = None
        try:
            publish_url = f'https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token={access_token}'
            publish_data = json.dumps({'media_id': draft_resp['media_id']}, ensure_ascii=False).encode('utf-8')
            pub_resp = requests.post(publish_url, data=publish_data,
                                      headers={'Content-Type': 'application/json; charset=utf-8'},
                                      timeout=30).json()
            if 'msg_data_id' in pub_resp or pub_resp.get('errcode') == 0:
                publish_result = 'published'
            else:
                publish_result = f'auto_publish_failed: {pub_resp.get("errmsg", "")}'
        except:
            publish_result = 'publish_not_attempted'
        
        return jsonify({
            'success': True,
            'draft_media_id': draft_resp['media_id'],
            'publish_status': publish_result or 'draft_created'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'请求异常: {str(e)}'})


# ============================================================
# 生成记录 API
# ============================================================

@app.route('/api/publish/record-generation', methods=['POST'])
def api_record_generation():
    """记录用户的生成操作"""
    data = request.get_json()
    db = get_db()
    user_id = session.get('user_id')
    username = session.get('username', 'anonymous')
    
    db.execute("""
        INSERT INTO generation_records (user_id, username, action_type, title, detail, status, draft_media_id, ip_address)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        username,
        data.get('action_type', 'unknown'),
        data.get('title', ''),
        data.get('detail', ''),
        data.get('status', 'success'),
        data.get('draft_media_id', ''),
        request.remote_addr
    ))
    db.commit()
    return jsonify({'success': True, 'record_id': db.execute("SELECT last_insert_rowid()").fetchone()[0]})


@app.route('/api/admin/generation-records', methods=['GET'])
@admin_required
def api_generation_records():
    """管理员查看生成记录"""
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 30, type=int)
    action_type = request.args.get('action_type', '')
    username = request.args.get('username', '')
    
    query = "SELECT * FROM generation_records WHERE 1=1"
    params = []
    if action_type:
        query += " AND action_type = ?"
        params.append(action_type)
    if username:
        query += " AND username LIKE ?"
        params.append(f'%{username}%')
    
    count = db.execute(f"SELECT COUNT(*) FROM ({query})", params).fetchone()[0]
    offset = (page - 1) * per_page
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    
    records = db.execute(query, params).fetchall()
    items = [{
        'id': r['id'],
        'user_id': r['user_id'],
        'username': r['username'],
        'action_type': r['action_type'],
        'title': r['title'],
        'detail': r['detail'],
        'status': r['status'],
        'draft_media_id': r['draft_media_id'],
        'ip_address': r['ip_address'],
        'created_at': r['created_at'],
    } for r in records]
    
    return jsonify({
        'success': True,
        'data': {'items': items, 'total': count, 'page': page, 'per_page': per_page}
    })


# ============================================================
# 排版风格模板 API（服务端存储）
# ============================================================

@app.route('/api/publish/style-templates', methods=['GET'])
def api_style_templates_list():
    """获取所有风格模板"""
    db = get_db()
    templates = db.execute("""
        SELECT st.*, u.display_name as creator_name
        FROM style_templates st
        LEFT JOIN users u ON st.created_by = u.id
        ORDER BY st.id DESC
    """).fetchall()
    items = [{
        'id': t['id'],
        'name': t['name'],
        'profile': json.loads(t['profile_json'] or '{}'),
        'source_url': t['source_url'],
        'creator_name': t['creator_name'],
        'created_at': t['created_at'],
    } for t in templates]
    return jsonify({'success': True, 'data': items})


@app.route('/api/publish/style-templates', methods=['POST'])
def api_style_template_save():
    """保存风格模板"""
    data = request.get_json()
    name = data.get('name', '').strip()
    profile = data.get('profile', {})
    source_url = data.get('source_url', '')
    
    if not name:
        return jsonify({'success': False, 'message': '请输入模板名称'})
    if not profile:
        return jsonify({'success': False, 'message': '请提供排版风格数据'})
    
    db = get_db()
    user_id = session.get('user_id')
    
    # Check duplicate name
    existing = db.execute("SELECT id FROM style_templates WHERE name = ?", (name,)).fetchone()
    if existing:
        db.execute("UPDATE style_templates SET profile_json = ?, source_url = ?, created_by = ?, created_at = CURRENT_TIMESTAMP WHERE id = ?",
                   (json.dumps(profile, ensure_ascii=False), source_url, user_id, existing['id']))
        db.commit()
        return jsonify({'success': True, 'message': f'模板「{name}」已更新', 'id': existing['id']})
    
    db.execute("INSERT INTO style_templates (name, profile_json, source_url, created_by) VALUES (?, ?, ?, ?)",
               (name, json.dumps(profile, ensure_ascii=False), source_url, user_id))
    db.commit()
    return jsonify({
        'success': True,
        'message': f'模板「{name}」已保存',
        'id': db.execute("SELECT last_insert_rowid()").fetchone()[0]
    })


@app.route('/api/publish/style-templates/<int:template_id>', methods=['DELETE'])
def api_style_template_delete(template_id):
    """删除风格模板"""
    db = get_db()
    db.execute("DELETE FROM style_templates WHERE id = ?", (template_id,))
    db.commit()
    return jsonify({'success': True, 'message': '模板已删除'})


@app.route('/api/publish/my-default-style', methods=['GET'])
@login_required
def api_get_my_default_style():
    """获取当前用户默认排版模板"""
    db = get_db()
    user = db.execute("SELECT default_style_template FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    template_name = user['default_style_template'] if user else ''
    template = None
    if template_name:
        t = db.execute("SELECT * FROM style_templates WHERE name = ?", (template_name,)).fetchone()
        if t:
            template = {
                'id': t['id'],
                'name': t['name'],
                'profile': json.loads(t['profile_json'] or '{}'),
                'source_url': t['source_url'],
                'created_at': t['created_at']
            }
    return jsonify({'success': True, 'template_name': template_name, 'template': template})


@app.route('/api/publish/my-default-style', methods=['PUT'])
@login_required
def api_set_my_default_style():
    """设置当前用户默认排版模板"""
    data = request.get_json()
    template_name = data.get('template_name', '').strip()
    db = get_db()
    if template_name:
        # 校验模板存在
        t = db.execute("SELECT id FROM style_templates WHERE name = ?", (template_name,)).fetchone()
        if not t:
            return jsonify({'success': False, 'message': '模板不存在'})
    db.execute("UPDATE users SET default_style_template = ? WHERE id = ?", (template_name, session['user_id']))
    db.commit()
    return jsonify({'success': True, 'message': '默认模板已保存'})


# ============================================================
# AI 生成：新闻搜索 + DeepSeek 文章生成
# 支持 Tavily（默认）/ Bing（备选）/ RSS 抓取（兜底）
# ============================================================

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"
BING_SEARCH_URL = "https://api.bing.microsoft.com/v7.0/news/search"

# DeepSeek 默认 API Key —— 从环境变量 / .env 读取，切勿硬编码到源码
# 配置方式：项目根目录创建 .env 文件，写入 DEEPSEEK_API_KEY=你的key
DEFAULT_DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '')

# Tavily 默认 API Key —— 同上，从环境变量读取
DEFAULT_TAVILY_KEY = os.environ.get('TAVILY_API_KEY', '')

# RSS 新闻源（无需 API key，兜底方案）
RSS_FEEDS = [
    {"name": "IT之家", "url": "https://www.ithome.com/rss/"},
    {"name": "36氪", "url": "https://36kr.com/feed"},
    {"name": "少数派", "url": "https://sspai.com/feed"},
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss"},
]

def _get_ai_config():
    """从 store_settings 读取 AI 相关配置"""
    db = get_db()
    keys = ['deepseek_api_key', 'search_api_key', 'search_provider']
    config = {}
    for k in keys:
        row = db.execute("SELECT value FROM store_settings WHERE key=?", (k,)).fetchone()
        config[k] = row['value'] if row else ''
    # DeepSeek 默认 key（用户没配置时用）
    if not config.get('deepseek_api_key'):
        config['deepseek_api_key'] = DEFAULT_DEEPSEEK_KEY
    # 默认搜索提供商
    if not config.get('search_provider'):
        config['search_provider'] = 'tavily'
    # Tavily 默认 key（用户没配置时用）
    if not config.get('search_api_key') and config['search_provider'] == 'tavily':
        config['search_api_key'] = DEFAULT_TAVILY_KEY
    return config


def _search_news(query, config, count=5):
    """统一搜索入口：按 search_provider 分发"""
    provider = config.get('search_provider', 'tavily')
    api_key = config.get('search_api_key', '')

    if provider == 'tavily' and api_key:
        return _tavily_search(query, api_key, count)
    elif provider == 'bing' and api_key:
        return _bing_search_news(query, api_key, count)
    else:
        # 无 API key 时用 RSS 抓取兜底
        return _rss_search(query, count)


def _tavily_search(query, api_key, count=5):
    """调用 Tavily Search API"""
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {
        'query': query,
        'search_depth': 'basic',
        'include_domains': [],
        'max_results': count,
        'topic': 'news'
    }
    resp = requests.post(TAVILY_SEARCH_URL, headers=headers, json=payload, timeout=15)
    data = resp.json()

    if 'results' not in data:
        error_msg = data.get('detail', resp.text[:200]) if isinstance(data, dict) else str(data)[:200]
        raise Exception(f"Tavily 搜索失败: {error_msg}")

    results = []
    for item in data['results'][:count]:
        results.append({
            'title': item.get('title', ''),
            'description': item.get('content', '')[:200],
            'url': item.get('url', ''),
            'source': _extract_domain(item.get('url', '')),
            'published': ''
        })
    return results


def _bing_search_news(query, api_key, count=5):
    """调用 Bing News Search API 搜索中文新闻"""
    headers = {'Ocp-Apim-Subscription-Key': api_key}
    params = {
        'q': query,
        'mkt': 'zh-CN',
        'count': count,
        'freshness': 'Week'
    }
    resp = requests.get(BING_SEARCH_URL, headers=headers, params=params, timeout=15)
    data = resp.json()

    if 'value' not in data:
        error_msg = data.get('message', resp.text[:200]) if isinstance(data, dict) else str(data)[:200]
        raise Exception(f"Bing 搜索失败: {error_msg}")

    results = []
    for item in data['value'][:count]:
        results.append({
            'title': item.get('name', ''),
            'description': item.get('description', ''),
            'url': item.get('url', ''),
            'source': item.get('provider', [{}])[0].get('name', '') if item.get('provider') else '',
            'published': item.get('datePublished', '')
        })
    return results


def _rss_search(query, count=5):
    """RSS 抓取兜底：不需要任何 API key，从中文科技新闻源抓取"""
    import xml.etree.ElementTree as ET
    import re

    all_items = []
    for feed in RSS_FEEDS:
        try:
            resp = requests.get(feed['url'], headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            root = ET.fromstring(resp.content)

            ns = {'rss': 'http://purl.org/rss/1.0/', 'atom': 'http://www.w3.org/2005/Atom'}
            # RSS 2.0
            for item in root.iter('item'):
                title = item.find('title')
                desc = item.find('description')
                link = item.find('link')
                all_items.append({
                    'title': title.text.strip() if title is not None and title.text else '',
                    'description': _clean_html(desc.text[:300]) if desc is not None and desc.text else '',
                    'url': link.text.strip() if link is not None and link.text else '',
                    'source': feed['name'],
                    'published': ''
                })
        except Exception:
            continue

    # 基于关键词简单过滤排序
    if not all_items:
        raise Exception("RSS 抓取失败，所有源均无响应。请配置搜索 API Key（Tavily 或 Bing）")

    keywords = [w.strip().lower() for w in query.split() if len(w.strip()) > 1]
    scored = []
    for item in all_items:
        score = 0
        txt = (item['title'] + item['description']).lower()
        for kw in keywords:
            if kw in txt:
                score += 1
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    # 取前 count 条，不足则补未匹配的
    results = [item for s, item in scored if s > 0][:count]
    if len(results) < count:
        for s, item in scored:
            if s == 0 and len(results) < count:
                results.append(item)

    return results[:count]


def _extract_domain(url):
    """从 URL 提取域名"""
    import re
    m = re.search(r'https?://([^/]+)', url)
    return m.group(1) if m else ''


def _clean_html(text):
    """去除 HTML 标签"""
    import re
    return re.sub(r'<[^>]+>', '', text)


def _deepseek_generate(topic, news_results, style_profile, api_key):
    """调用 DeepSeek API 生成公众号文章 HTML"""
    # 构建新闻素材文本
    news_text = ""
    for i, news in enumerate(news_results, 1):
        news_text += f"【{i}】{news['title']}\n来源：{news['source']}\n摘要：{news['description']}\n\n"

    system_prompt = """你是一个专业的微信公众号科技资讯编辑。请根据提供的新闻素材，生成一篇排版精美的公众号文章。

严格要求：
1. 标题控制在20个中文字以内（64字节限制）
2. 摘要控制在40个中文字以内（120字节限制）
3. 正文500-1000字，语言流畅专业
4. 严禁使用任何emoji表情符号
5. 严禁使用「」等特殊引号，只用普通中文引号
6. HTML格式严格只用 section + p 标签，禁止嵌套多层div
7. 小标题用 <p style="font-size:17px;font-weight:bold;color:#2c3e50;margin:25px 0 12px 0;">标题</p>
8. 正文用 <p style="margin-bottom:15px;">内容</p>
9. 结尾加一段简短的编辑点评

请返回JSON格式：
{
  "title": "文章标题",
  "digest": "文章摘要",
  "content": "完整的HTML正文"
}"""

    if style_profile:
        system_prompt += f"\n\n参考排版风格：{json.dumps(style_profile, ensure_ascii=False)}"

    user_prompt = f"主题方向：{topic}\n\n新闻素材：\n{news_text}\n\n请生成公众号文章。"

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': 'deepseek-chat',
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        'temperature': 0.7,
        'max_tokens': 4096,
        'response_format': {'type': 'json_object'}
    }

    resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
    data = resp.json()

    if 'choices' not in data:
        error_msg = data.get('error', {}).get('message', resp.text[:200]) if isinstance(data, dict) else str(data)[:200]
        raise Exception(f"DeepSeek 生成失败: {error_msg}")

    result_text = data['choices'][0]['message']['content']
    return json.loads(result_text)


@app.route('/api/publish/ai-config', methods=['GET'])
def api_publish_ai_config_get():
    """获取 AI 配置（不返回完整 key）"""
    config = _get_ai_config()
    return jsonify({
        'success': True,
        'deepseek_configured': bool(config.get('deepseek_api_key')),
        'search_configured': bool(config.get('search_api_key')),
        'search_provider': config.get('search_provider', 'tavily'),
        'has_rss_fallback': True
    })


@app.route('/api/publish/ai-config', methods=['POST'])
def api_publish_ai_config_save():
    """保存 AI API 配置"""
    data = request.get_json()
    db = get_db()
    valid_keys = ['deepseek_api_key', 'search_api_key', 'search_provider']
    for k in valid_keys:
        if k in data and data[k]:
            existing = db.execute("SELECT id FROM store_settings WHERE key=?", (k,)).fetchone()
            if existing:
                db.execute("UPDATE store_settings SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key=?", (str(data[k]), k))
            else:
                db.execute("INSERT INTO store_settings (key, value) VALUES (?, ?)", (k, str(data[k])))
    db.commit()
    return jsonify({'success': True, 'message': 'AI配置已保存'})


@app.route('/api/publish/ai-generate', methods=['POST'])
def api_publish_ai_generate():
    """AI 自动生成公众号文章（新闻搜索 + DeepSeek 写作）
    搜索优先级: Tavily API > Bing API > RSS 兜底抓取
    DeepSeek: 使用默认 key，无需用户单独配置
    """
    data = request.get_json()
    topic = (data.get('topic') or '').strip()
    count = int(data.get('count', 5))

    if not topic:
        return jsonify({'success': False, 'message': '请输入文章主题或关键词'})

    config = _get_ai_config()
    deepseek_key = config.get('deepseek_api_key', '')

    if not deepseek_key:
        return jsonify({'success': False, 'message': 'DeepSeek API Key 未配置'})

    search_method = 'RSS 抓取（免费兜底）'
    if config.get('search_api_key'):
        search_method = f"{config['search_provider'].upper()} API"

    try:
        # 步骤1：搜索新闻（自动选择可用方式）
        news_results = _search_news(topic, config, count)
        if not news_results:
            return jsonify({'success': False, 'message': '未搜索到相关新闻，请换个关键词试试'})

        # 步骤2：DeepSeek 生成文章
        style_profile = data.get('style_profile', None)
        article = _deepseek_generate(topic, news_results, style_profile, deepseek_key)

        return jsonify({
            'success': True,
            'article': {
                'title': article.get('title', ''),
                'digest': article.get('digest', ''),
                'content': article.get('content', '')
            },
            'sources': news_results,
            'stats': {
                'news_count': len(news_results),
                'topic': topic,
                'search_method': search_method
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# ============================================================
# 管理后台路由：生成记录
# ============================================================



# ==================== 秀米模板排版 API ====================
@app.route('/api/publish/apply-xiumi-template', methods=['POST'])
def apply_xiumi_template():
    """应用秀米模板排版：解析模板HTML，将用户内容填入模板结构"""
    from bs4 import BeautifulSoup
    import re as _re
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '缺少数据'})

    template_url = data.get('template_url', '').strip()
    template_html = data.get('template_html', '').strip()
    title = data.get('title', '')
    sections = data.get('sections', [])
    images = data.get('images', [])
    digest = data.get('digest', '')

    try:
        # === 1. 获取模板 HTML ===
        if template_url:
            try:
                resp = requests.get(template_url, timeout=15, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                resp.encoding = 'utf-8'
                html = resp.text
            except Exception as e:
                return jsonify({'success': False, 'message': f'获取模板链接失败: {str(e)}'})
        elif template_html:
            html = template_html
        else:
            return jsonify({'success': False, 'message': '请提供模板链接或粘贴模板HTML代码'})

        # === 2. 解析模板结构 ===
        soup = BeautifulSoup(html, 'html.parser')

        # 提取 style 标签
        style_blocks = []
        for style_tag in soup.find_all('style'):
            style_blocks.append(style_tag.string or '')
            style_tag.decompose()
        combined_css = '\n'.join(style_blocks)

        # === 2.5 下载模板中的外部图片并转为 base64 内嵌（解决秀米 CDN 防盗链/跨域问题） ===
        import base64 as _b64
        import imghdr
        
        template_images = []
        
        def download_img_to_base64(img_url, timeout=8):
            """下载外部图片并返回 data URI，失败返回原 URL"""
            try:
                # 跳过已经是 data URI 的
                if img_url.startswith('data:'):
                    return img_url
                # 跳过明显的本地/占位 URL
                if not img_url.startswith('http'):
                    return img_url
                
                resp = requests.get(img_url, timeout=timeout, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://xiumi.us/',
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
                })
                if resp.status_code == 200:
                    content_type = resp.headers.get('Content-Type', 'image/png')
                    # 如果 Content-Type 不含 image，用 imghdr 检测
                    if 'image' not in content_type:
                        detected = imghdr.what(None, h=resp.content[:32])
                        if detected:
                            content_type = f'image/{detected}'
                    
                    b64 = _b64.b64encode(resp.content).decode('utf-8')
                    return f'data:{content_type};base64,{b64}'
            except Exception:
                pass
            return img_url  # 失败返回原 URL
        
        # 处理 <img> 标签
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src:
                new_src = download_img_to_base64(src)
                img['src'] = new_src
                template_images.append(new_src)
        
        # 处理内联 style 中的 background-image / background
        for tag in soup.find_all(style=True):
            style = tag.get('style', '')
            # 匹配 background-image: url(...) 或 background: url(...)
            def replace_bg_url(m):
                full = m.group(0)
                url_part = m.group(1)
                if url_part.startswith('http') and not url_part.startswith('data:'):
                    new = download_img_to_base64(url_part)
                    return full.replace(url_part, new)
                return full
            
            new_style = _re.sub(r'background(?:-image)?\s*:\s*url\([\'\"]?([^)\'\"]+)[\'\"]?\)', replace_bg_url, style)
            if new_style != style:
                tag['style'] = new_style

        body = soup.find('body') or soup

        # === 3. 构建模板块列表并分类 ===
        # 策略：以 section 为主要容器单位，每个 section 是一个逻辑块
        # 分析每个块的视觉特征判断其角色
        
        Role = {
            'TITLE': 1,       # 大标题（大字号+粗体+居中）
            'INTRO': 2,       # 引导语/摘要（紧接标题，中字号，通常灰色）
            'SUBTITLE': 3,    # 小标题（粗体，中等字号）
            'BODY': 4,        # 正文段落
            'QUOTE': 5,       # 引用（特殊边框或斜体）
            'IMAGE': 6,       # 图片块
            'DECORATION': 7,  # 装饰性元素（极短文本、特殊符号、分隔符等）
        }
        
        def px_val(style_str, prop):
            """从内联 style 中提取像素值"""
            if not style_str:
                return None
            m = _re.search(rf'{prop}\s*:\s*(\d+)px', style_str)
            return int(m.group(1)) if m else None
        
        def classify_block(container):
            """分析一个容器元素，判断其语义角色"""
            # 收集关键信息
            all_text = container.get_text(strip=True)
            all_text_lower = all_text.lower()
            text_len = len(all_text)
            
            # 检查是否包含图片
            imgs = container.find_all('img')
            has_img = len(imgs) > 0
            
            # 检查子元素的样式特征
            child_tags = container.find_all(['p', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div'])
            
            max_font_size = 0
            min_font_size = 999
            has_bold = False
            has_center = False
            has_italic = False
            has_left_border = False
            font_sizes = []
            
            # 也检查容器自身的样式
            container_style = container.get('style', '') or ''
            
            for tag in child_tags:
                style = (tag.get('style', '') or '').lower()
                fs = px_val(style, 'font-size')
                if fs:
                    font_sizes.append(fs)
                    max_font_size = max(max_font_size, fs)
                    min_font_size = min(min_font_size, fs)
                if 'font-weight' in style and 'bold' in style:
                    has_bold = True
                if 'text-align' in style and 'center' in style:
                    has_center = True
                if 'font-style' in style and 'italic' in style:
                    has_italic = True
                if 'border-left' in style:
                    has_left_border = True
            
            # 如果子元素没找到样式，用容器自身
            if not font_sizes:
                fs = px_val(container_style, 'font-size')
                if fs:
                    font_sizes.append(fs)
                    max_font_size = max(max_font_size, fs)
                    min_font_size = min(min_font_size, fs)
            
            avg_font = sum(font_sizes) / len(font_sizes) if font_sizes else 15
            
            # --- 分类决策 ---
            
            # 图片块
            if has_img and text_len < 30:
                return Role['IMAGE']
            
            # 装饰性元素：极短文本、纯特殊字符
            if text_len <= 3:
                return Role['DECORATION']
            if _re.match(r'^[\s\|·•●○◆◇▲△▼▽★☆♥♦♣♠\-\+=~@#\$%^&\*\(\)\[\]\{\}<>\/\\]+$', all_text):
                return Role['DECORATION']
            # 常见的装饰关键词
            deco_keywords = ['关注我们', '扫码', '长按', '阅读原文', '点击上方', '更多精彩']
            if any(kw in all_text for kw in deco_keywords) and text_len < 15:
                return Role['DECORATION']
            
            # 大标题：大字号(≥18px) + 粗体/居中
            if max_font_size >= 17 or (has_bold and has_center and text_len < 60):
                return Role['TITLE']
            
            # 小标题：中等字号(15-17px) + 粗体
            if has_bold and 13 <= avg_font <= 17 and text_len < 80:
                return Role['SUBTITLE']
            
            # 引用：左边框 或 斜体
            if has_left_border or has_italic:
                return Role['QUOTE']
            
            # 小字号(<13px)短文本 → 引导语/摘要
            if max_font_size < 13 and text_len < 200:
                return Role['INTRO']
            
            # 默认正文
            return Role['BODY']
        
        # === 4. 构建模板块 ===
        TemplateBlock = lambda container, role, idx: {
            'container': container,
            'role': role,
            'index': idx,
            'text': container.get_text(strip=True)[:60]
        }
        
        blocks = []
        sections = body.find_all('section')
        
        if sections:
            # 有 section 结构：每个 section 作为一个逻辑块
            for idx, sec in enumerate(sections):
                role = classify_block(sec)
                blocks.append(TemplateBlock(sec, role, idx))
        else:
            # 没有 section：以 div/p 为块
            for idx, el in enumerate(body.find_all(['div', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])):
                if el.get_text(strip=True):
                    role = classify_block(el)
                    blocks.append(TemplateBlock(el, role, idx))
        
        # 去重：连续相同角色的 BODY 块合并（秀米常把一个段落拆成多个 section）
        merged_blocks = []
        for blk in blocks:
            if merged_blocks and blk['role'] == Role['BODY'] and merged_blocks[-1]['role'] == Role['BODY']:
                # 合并：保留前一个容器，跳过当前
                continue
            merged_blocks.append(blk)
        blocks = merged_blocks
        
        # === 5. 按角色分组模板块，建立可用槽位 ===
        title_slots = [b for b in blocks if b['role'] == Role['TITLE']]
        intro_slots = [b for b in blocks if b['role'] == Role['INTRO']]
        subtitle_slots = [b for b in blocks if b['role'] == Role['SUBTITLE']]
        body_slots = [b for b in blocks if b['role'] == Role['BODY']]
        quote_slots = [b for b in blocks if b['role'] == Role['QUOTE']]
        image_slots = [b for b in blocks if b['role'] == Role['IMAGE']]
        
        # 记录分析结果用于返回
        block_summary = []
        for b in blocks:
            role_names = {1:'TITLE', 2:'INTRO', 3:'SUBTITLE', 4:'BODY', 5:'QUOTE', 6:'IMAGE', 7:'DECORATION'}
            block_summary.append(f"[{role_names.get(b['role'], '?')}] {b['text']}")
        
        # === 6. 准备用户内容，按类型分类 ===
        user_title = title
        user_digest = digest
        user_subtitles = []   # h2
        user_bodies = []      # p
        user_quotes = []      # blockquote
        user_images = []      # img
        for s in sections:
            t = s.get('type', 'p')
            txt = s.get('text', '').strip()
            if not txt and t != 'img':
                continue
            if t == 'h2':
                user_subtitles.append(txt)
            elif t == 'p':
                user_bodies.append(txt)
            elif t == 'blockquote':
                user_quotes.append(txt)
            elif t == 'img':
                user_images.append(txt)
        
        # === 7. 智能匹配填充 ===
        def fill_text_element(el, text, tag='span'):
            """安全地填充文本到元素，保留子元素结构"""
            text_spans = el.find_all(['span', 'p', 'a'])
            if text_spans:
                # 有子文本元素：填充最内层的文本节点
                for ts in text_spans:
                    if ts.string and len(ts.get_text(strip=True)) > 2:
                        ts.string = text
                        return
                # 所有子元素都太短，填第一个
                text_spans[0].string = text
            else:
                # 没有子元素，直接设置文本
                if el.string is not None:
                    el.string = text
                else:
                    # 清除内容后设置
                    for child in list(el.children):
                        if isinstance(child, str) or (hasattr(child, 'name') and child.name in ['span', 'p', 'a']):
                            child.extract()
                    el.append(text)
        
        def fill_block(block, text):
            """填充一个模板块的内容"""
            el = block['container']
            # 清除原有文本子元素中的文字
            for child in el.find_all(['span', 'p', 'a']):
                if child.string and len(child.get_text(strip=True)) > 1:
                    child.string = text
                    return
            # fallback：直接替换第一个文本子元素
            for child in el.descendants:
                if isinstance(child, str) and child.strip():
                    continue  # 跳过纯文本节点
                if hasattr(child, 'name') and child.name in ['span', 'p'] and child.string:
                    child.string = text
                    return
            # 最后兜底
            if el.string is not None:
                el.string = text
        
        filled_log = []
        
        # 1) 匹配大标题 → 第一个 TITLE 槽
        if user_title and title_slots:
            fill_block(title_slots[0], user_title)
            filled_log.append(f'标题 → TITLE[{title_slots[0]["index"]}]')
        
        # 2) 匹配摘要 → 第一个 INTRO 槽（没有的话用第二个 TITLE 槽，再没有用第一个 BODY）
        if user_digest:
            if intro_slots:
                fill_block(intro_slots[0], user_digest)
                filled_log.append(f'摘要 → INTRO[{intro_slots[0]["index"]}]')
            elif len(title_slots) > 1:
                fill_block(title_slots[1], user_digest)
                filled_log.append(f'摘要 → TITLE[{title_slots[1]["index"]}]（无INTRO槽）')
            elif body_slots:
                fill_block(body_slots[0], user_digest)
                filled_log.append(f'摘要 → BODY[{body_slots[0]["index"]}]（无INTRO槽）')
        
        # 3) 匹配小标题 → SUBTITLE 槽
        for i, st in enumerate(user_subtitles):
            if i < len(subtitle_slots):
                fill_block(subtitle_slots[i], st)
                filled_log.append(f'小标题 → SUBTITLE[{subtitle_slots[i]["index"]}]')
            elif body_slots:
                # 没有 SUBTITLE 槽了，用 BODY 兜底
                b = body_slots.pop(0)
                fill_block(b, st)
                # 加粗它
                for child in b['container'].find_all(['span', 'p']):
                    style = child.get('style', '') or ''
                    child['style'] = style + ';font-weight:bold;'
                filled_log.append(f'小标题 → BODY[{b["index"]}]（兜底加粗）')

        # 4) 匹配引用 → QUOTE 槽
        for i, qt in enumerate(user_quotes):
            if i < len(quote_slots):
                fill_block(quote_slots[i], qt)
                filled_log.append(f'引用 → QUOTE[{quote_slots[i]["index"]}]')
            elif body_slots:
                b = body_slots.pop(0)
                fill_block(b, qt)
                container = b['container']
                container['style'] = (container.get('style', '') or '') + ';border-left:3px solid #534ab7;padding-left:12px;color:#666;'
                filled_log.append(f'引用 → BODY[{b["index"]}]（兜底加边框）')
        
        # 5) 匹配图片 → IMAGE 槽
        img_idx = 0
        for i, img_text in enumerate(user_images):
            img_url = images[i] if i < len(images) else img_text
            if img_idx < len(image_slots):
                blk = image_slots[img_idx]
                el = blk['container']
                existing_imgs = el.find_all('img')
                if existing_imgs:
                    existing_imgs[0]['src'] = img_url
                else:
                    new_img = soup.new_tag('img', src=img_url)
                    new_img['style'] = 'max-width:100%;display:block;margin:0 auto;'
                    el.clear()
                    el.append(new_img)
                filled_log.append(f'图片 → IMAGE[{blk["index"]}]')
                img_idx += 1
            elif body_slots:
                b = body_slots.pop(0)
                el = b['container']
                new_img = soup.new_tag('img', src=img_url)
                new_img['style'] = 'max-width:100%;display:block;margin:0 auto;'
                el.clear()
                el.append(new_img)
                filled_log.append(f'图片 → BODY[{b["index"]}]（兜底）')
        
        # 6) 匹配正文 → BODY 槽（也是默认兜底）
        for i, bd in enumerate(user_bodies):
            if body_slots:
                b = body_slots.pop(0)
                fill_block(b, bd)
                filled_log.append(f'正文 → BODY[{b["index"]}]')
            else:
                # 完全没槽了，在 body 末尾追加新 section
                new_sec = soup.new_tag('section')
                new_sec['style'] = 'padding:10px 0;'
                p = soup.new_tag('p')
                p['style'] = 'font-size:15px;color:#3f3f3f;line-height:1.8;letter-spacing:1px;'
                p.string = bd
                new_sec.append(p)
                body.append(new_sec)
                filled_log.append(f'正文 → 末尾追加')
        
        # 7) 清空未被使用的 BODY/QUOTE 槽（保留 DECORATION）
        unused_roles = {Role['BODY'], Role['QUOTE'], Role['INTRO']}
        # 注意：TITLE 槽如果没匹配也保留，因为模板标题样式本身就是一种装饰
        for b in blocks:
            if b['role'] in unused_roles and b not in [blk for blk in blocks if blk in 
                (title_slots[:1] if user_title else []) +
                (title_slots[1:2] if user_digest and len(title_slots) > 1 else [])]:
                # 检查是否已被填充
                pass  # 我们不清除——模板结构更好保留
        
        # 清空未被匹配且是"占位文本"的槽
        # 找到所有被填充过的容器
        filled_containers = set()
        for b in blocks:
            for log_entry in filled_log:
                if f'[{b["index"]}]' in log_entry:
                    filled_containers.add(id(b['container']))
        
        for b in blocks:
            if id(b['container']) not in filled_containers and b['role'] in unused_roles:
                # 清空这个槽的文本
                for child in b['container'].find_all(['span', 'p']):
                    if child.string and len(child.get_text(strip=True)) > 1:
                        child.string = ''

        # === 7.5 清理 CSS 动画和 SVG 动画（消除秀米模板中的 loading 转圈效果）===
        
        # 1) 清除内联 animation 样式
        for tag in soup.find_all(style=True):
            style = tag.get('style', '')
            # 移除 animation: xxx 和 animation-name: xxx
            new_style = _re.sub(r'animation(?:-name|-duration|-delay|-iteration-count|-direction|-fill-mode|-timing-function)?\s*:\s*[^;]*;?', '', style)
            # 移除 transition
            new_style = _re.sub(r'transition(?:-property|-duration|-delay|-timing-function)?\s*:\s*[^;]*;?', '', new_style)
            # 清理多余分号
            new_style = _re.sub(r';\s*;+', ';', new_style).strip('; ')
            if new_style != style:
                if new_style:
                    tag['style'] = new_style
                else:
                    del tag['style']
        
        # 2) 清除 SVG 动画标签
        for anim_tag in soup.find_all(['animate', 'animateTransform', 'animateMotion']):
            anim_tag.decompose()
        
        # 3) 清理 combined_css 中的 @keyframes 和 animation 规则
        if combined_css:
            # 移除 @keyframes 块
            combined_css = _re.sub(r'@keyframes\s+\w+\s*\{[^}]*\}', '', combined_css, flags=_re.DOTALL)
            # 移除 animation 声明行
            combined_css = _re.sub(r'\s*animation(?:-[^:]+)?\s*:\s*[^;]*;?', '', combined_css)
            # 清理空行
            combined_css = '\n'.join(line for line in combined_css.split('\n') if line.strip())
        
        # 4) 二次扫描：找所有漏网的外部图片 URL（包括 data-src, srcset 等属性）
        for tag in soup.find_all(True):
            for attr in ['src', 'srcset', 'data-src', 'data-original', 'data-img']:
                val = tag.get(attr, '')
                if val and val.startswith('http') and not val.startswith('data:'):
                    # srcset 特殊处理：可能包含多个 URL
                    if attr == 'srcset':
                        parts = val.split(',')
                        new_parts = []
                        for part in parts:
                            url_match = _re.match(r'\s*(\S+)', part)
                            if url_match:
                                url = url_match.group(1)
                                if url.startswith('http') and not url.startswith('data:'):
                                    new_url = download_img_to_base64(url)
                                    part = part.replace(url, new_url)
                            new_parts.append(part)
                        tag[attr] = ','.join(new_parts)
                    else:
                        tag[attr] = download_img_to_base64(val)
        
        # 5) 处理秀米模板中常见的问题：给所有空 img 加兜底
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if not src or src.strip() == '' or src.startswith('http'):
                # 空 src 或还是外部链接 → 用 1x1 透明像素图代替
                img['src'] = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        
        # 6) 处理可能是 loading 圈的元素：带圆形边框+动画的 div
        # 秀米常见：border-radius:50% + border-top-color + animation: spin
        # 如果这些元素没有实质内容，直接移除
        for div in soup.find_all('div'):
            style = div.get('style', '')
            if 'border-radius' in style and '50%' in style:
                text = div.get_text(strip=True)
                imgs = div.find_all('img')
                if not text and not imgs:
                    # 这是一个纯装饰性的圆/圈，没有文字和图片 → 移除
                    div.decompose()

        # === 8. 输出最终 HTML ===
        # 重新插入 style
        if combined_css:
            style_tag = soup.new_tag('style')
            style_tag.string = combined_css
            head = soup.find('head')
            if head:
                head.insert(0, style_tag)
            else:
                body.insert_before(style_tag)

        result_html = str(soup)

        return jsonify({
            'success': True,
            'html': result_html,
            'template_images': template_images[:5],
            'filled_count': len(filled_log),
            'block_analysis': block_summary,
            'filled_log': filled_log,
            'slot_summary': {
                'title': len(title_slots),
                'intro': len(intro_slots),
                'subtitle': len(subtitle_slots),
                'body': len(body_slots),
                'quote': len(quote_slots),
                'image': len(image_slots),
                'decoration': sum(1 for b in blocks if b['role'] == Role['DECORATION'])
            }
        })

    except Exception as e:
        import traceback
        return jsonify({'success': False, 'message': f'模板处理异常: {str(e)}', 'traceback': traceback.format_exc()})
# ============================================================
# 内置排版模板库
# ============================================================

def _tm_build_content(title, intro, subtitles, bodies, quotes, images, tm_prefix):
    """通用内容构建器：根据内容列表生成对应class的HTML片段"""
    parts = []
    
    # 标题
    if title:
        parts.append(f'<div class="{tm_prefix}-title">{title}</div>')
    
    # 摘要
    if intro:
        parts.append(f'<div class="{tm_prefix}-intro">{intro}</div>')
    
    # 内容流：按原始顺序交替排列小标题、正文、引用、图片
    # 但为了简化，我们按类型分组，保持各组内部顺序
    si, bi, qi, ii = 0, 0, 0, 0
    # 先展示所有内容，小标题和正文穿插
    content_blocks = []
    
    # 合并所有内容为一个有序列表
    # 这里我们简单地按类型展示：小标题→正文→引用→图片
    for st in subtitles:
        content_blocks.append(('subtitle', st))
    for bd in bodies:
        content_blocks.append(('body', bd))
    for qt in quotes:
        content_blocks.append(('quote', qt))
    for img in images:
        content_blocks.append(('image', img))
    
    # 如果没有内容块但有标题/摘要，加个分割线
    if content_blocks:
        for ctype, cval in content_blocks:
            if ctype == 'subtitle':
                parts.append(f'<div class="{tm_prefix}-subtitle">{cval}</div>')
            elif ctype == 'body':
                parts.append(f'<div class="{tm_prefix}-p">{cval}</div>')
            elif ctype == 'quote':
                parts.append(f'<div class="{tm_prefix}-quote">{cval}</div>')
            elif ctype == 'image':
                parts.append(f'<img class="{tm_prefix}-img" src="{cval}" alt="">')
    
    return '\n'.join(parts)


def template_clean_minimal(title, intro, subtitles, bodies, quotes, images):
    """模板1：简约清新"""
    content = _tm_build_content(title, intro, subtitles, bodies, quotes, images, 'tm1')
    return f'''<div style="max-width:680px;margin:0 auto;padding:24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#fff;color:#333;line-height:1.8;">
<style>
.tm1-title{{font-size:28px;font-weight:700;color:#1a1a1a;margin-bottom:12px;line-height:1.3;}}
.tm1-intro{{font-size:14px;color:#666;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #eee;}}
.tm1-subtitle{{font-size:18px;font-weight:600;color:#2c3e50;margin:24px 0 12px;padding-left:12px;border-left:3px solid #3498db;}}
.tm1-p{{font-size:15px;color:#444;margin-bottom:16px;text-align:justify;}}
.tm1-quote{{margin:20px 0;padding:16px 20px;background:#f8f9fa;border-left:4px solid #3498db;color:#555;font-style:italic;}}
.tm1-img{{max-width:100%;border-radius:8px;margin:16px 0;display:block;}}
</style>
{content}
</div>'''


def template_magazine(title, intro, subtitles, bodies, quotes, images):
    """模板2：杂志风"""
    content = _tm_build_content(title, intro, subtitles, bodies, quotes, images, 'tm2')
    return f'''<div style="max-width:680px;margin:0 auto;font-family:Georgia,'Times New Roman',serif;background:#fff;">
<style>
.tm2-header{{text-align:center;padding:40px 24px 24px;background:#1a1a1a;color:#fff;}}
.tm2-title{{font-size:32px;font-weight:700;margin-bottom:16px;line-height:1.2;}}
.tm2-intro{{font-size:15px;color:#ccc;max-width:500px;margin:0 auto;}}
.tm2-body{{padding:32px 24px;background:#fff;}}
.tm2-subtitle{{font-size:22px;font-weight:700;color:#1a1a1a;margin:32px 0 16px;}}
.tm2-p{{font-size:16px;color:#333;line-height:1.9;margin-bottom:20px;text-align:justify;}}
.tm2-quote{{margin:28px 0;padding:20px 24px;background:#f5f5f5;border-left:4px solid #1a1a1a;font-style:italic;color:#555;}}
.tm2-img{{max-width:100%;margin:20px 0;display:block;}}
</style>
<div class="tm2-header">
  <div class="tm2-title">{title or '无标题'}</div>
  {f'<div class="tm2-intro">{intro}</div>' if intro else ''}
</div>
<div class="tm2-body">
  {_tm_build_content('', '', subtitles, bodies, quotes, images, 'tm2')}
</div>
</div>'''


def template_literary(title, intro, subtitles, bodies, quotes, images):
    """模板3：文艺风"""
    content = _tm_build_content(title, intro, subtitles, bodies, quotes, images, 'tm3')
    return f'''<div style="max-width:680px;margin:0 auto;padding:32px 24px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:#faf8f5;color:#4a3f35;">
<style>
.tm3-title{{font-size:26px;font-weight:600;color:#5c4033;margin-bottom:16px;text-align:center;}}
.tm3-intro{{font-size:13px;color:#8b7355;text-align:center;margin-bottom:24px;font-style:italic;}}
.tm3-subtitle{{font-size:17px;font-weight:600;color:#6b4423;margin:28px 0 12px;}}
.tm3-p{{font-size:15px;color:#5a4a3a;line-height:2;margin-bottom:16px;text-indent:2em;}}
.tm3-quote{{margin:24px 0;padding:16px 20px;background:#f5f0e8;border-left:3px solid #c9a86c;color:#6b5b4f;font-style:italic;}}
.tm3-img{{max-width:100%;border-radius:4px;margin:16px 0;display:block;box-shadow:0 2px 8px rgba(0,0,0,0.08);}}
.tm3-divider{{text-align:center;margin:24px 0;color:#c9a86c;font-size:18px;letter-spacing:8px;}}
</style>
{content}
<div class="tm3-divider">* * *</div>
</div>'''


def template_business(title, intro, subtitles, bodies, quotes, images):
    """模板4：商务风"""
    content = _tm_build_content(title, intro, subtitles, bodies, quotes, images, 'tm4')
    return f'''<div style="max-width:680px;margin:0 auto;padding:24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#fff;">
<style>
.tm4-header{{background:linear-gradient(135deg,#1e3a5f 0%,#2c5282 100%);padding:32px 24px;color:#fff;border-radius:8px 8px 0 0;}}
.tm4-title{{font-size:26px;font-weight:700;margin-bottom:8px;}}
.tm4-intro{{font-size:13px;color:#a0c4e8;}}
.tm4-body{{padding:24px;background:#fff;}}
.tm4-subtitle{{font-size:17px;font-weight:600;color:#1e3a5f;margin:24px 0 12px;display:flex;align-items:center;}}
.tm4-subtitle::before{{content:'';display:inline-block;width:4px;height:18px;background:#2c5282;margin-right:10px;border-radius:2px;}}
.tm4-p{{font-size:14px;color:#4a5568;line-height:1.8;margin-bottom:14px;}}
.tm4-quote{{margin:20px 0;padding:14px 18px;background:#edf2f7;border-left:3px solid #2c5282;color:#4a5568;}}
.tm4-img{{max-width:100%;border-radius:6px;margin:14px 0;display:block;border:1px solid #e2e8f0;}}
.tm4-footer{{text-align:center;padding:16px;font-size:12px;color:#a0aec0;border-top:1px solid #e2e8f0;margin-top:24px;}}
</style>
<div class="tm4-header">
  <div class="tm4-title">{title or '无标题'}</div>
  {f'<div class="tm4-intro">{intro}</div>' if intro else ''}
</div>
<div class="tm4-body">
  {_tm_build_content('', '', subtitles, bodies, quotes, images, 'tm4')}
</div>
<div class="tm4-footer">本内容仅供阅读参考</div>
</div>'''


def template_card(title, intro, subtitles, bodies, quotes, images):
    """模板5：卡片风"""
    # 卡片风需要特殊处理：每个内容块一个卡片
    cards = []
    
    # 标题卡片
    if title:
        header = f'<div style="font-size:22px;font-weight:700;color:#1a202c;margin-bottom:8px;">{title}</div>'
        if intro:
            header += f'<div style="font-size:13px;color:#718096;">{intro}</div>'
        cards.append(f'<div style="background:#fff;border-radius:12px;padding:24px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">{header}</div>')
    
    # 内容卡片
    for st in subtitles:
        cards.append(f'<div style="background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,0.08);"><div style="font-size:16px;font-weight:600;color:#2d3748;margin-bottom:8px;">{st}</div></div>')
    for bd in bodies:
        cards.append(f'<div style="background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,0.08);"><div style="font-size:14px;color:#4a5568;line-height:1.7;">{bd}</div></div>')
    for qt in quotes:
        cards.append(f'<div style="background:#f7fafc;border-radius:12px;padding:16px 20px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,0.08);border-left:3px solid #667eea;"><div style="font-size:14px;color:#4a5568;font-style:italic;">{qt}</div></div>')
    for img in images:
        cards.append(f'<div style="background:#fff;border-radius:12px;padding:12px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,0.08);"><img src="{img}" style="max-width:100%;border-radius:8px;display:block;"></div>')
    
    return f'''<div style="max-width:680px;margin:0 auto;padding:16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f7fafc;">
{chr(10).join(cards)}
</div>'''


def template_dark(title, intro, subtitles, bodies, quotes, images):
    """模板6：深色风"""
    content = _tm_build_content(title, intro, subtitles, bodies, quotes, images, 'tm6')
    return f'''<div style="max-width:680px;margin:0 auto;padding:24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;">
<style>
.tm6-title{{font-size:28px;font-weight:700;color:#f8fafc;margin-bottom:12px;line-height:1.3;}}
.tm6-intro{{font-size:14px;color:#94a3b8;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #1e293b;}}
.tm6-subtitle{{font-size:18px;font-weight:600;color:#60a5fa;margin:24px 0 12px;}}
.tm6-p{{font-size:15px;color:#cbd5e1;line-height:1.8;margin-bottom:16px;}}
.tm6-quote{{margin:20px 0;padding:16px 20px;background:#1e293b;border-left:3px solid #60a5fa;color:#94a3b8;font-style:italic;border-radius:0 8px 8px 0;}}
.tm6-img{{max-width:100%;border-radius:8px;margin:16px 0;display:block;border:1px solid #1e293b;}}
</style>
{content}
</div>'''


# 模板注册表
BUILTIN_TEMPLATES = {
    1: {'name': '简约清新', 'category': '通用', 'func': template_clean_minimal, 'desc': '白色背景，简洁线条，适合科技与商业文章'},
    2: {'name': '杂志风', 'category': '长文', 'func': template_magazine, 'desc': '大标题深色头图，经典杂志排版，适合深度长文'},
    3: {'name': '文艺风', 'category': '生活', 'func': template_literary, 'desc': '暖色调米色背景，适合生活随笔与情感文章'},
    4: {'name': '商务风', 'category': '企业', 'func': template_business, 'desc': '蓝色系渐变头图，专业商务感，适合行业分析'},
    5: {'name': '卡片风', 'category': '现代', 'func': template_card, 'desc': '每个段落独立卡片，现代扁平设计，适合清单与资讯'},
    6: {'name': '深色风', 'category': '科技', 'func': template_dark, 'desc': '深蓝黑背景，适合科技类文章与夜间阅读'},
}


@app.route('/api/publish/built-in-templates', methods=['GET'])
def get_builtin_templates():
    """获取内置排版模板列表"""
    return jsonify({
        'success': True,
        'templates': [
            {'id': k, 'name': v['name'], 'category': v['category'], 'desc': v['desc']}
            for k, v in BUILTIN_TEMPLATES.items()
        ]
    })


@app.route('/api/publish/apply-built-in-template', methods=['POST'])
def apply_builtin_template():
    """应用内置排版模板"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '缺少数据'})
    
    template_id = data.get('template_id')
    title = data.get('title', '')
    digest = data.get('digest', '')
    sections = data.get('sections', [])
    images = data.get('images', [])
    
    if template_id not in BUILTIN_TEMPLATES:
        return jsonify({'success': False, 'message': f'模板ID {template_id} 不存在'})
    
    template = BUILTIN_TEMPLATES[template_id]
    
    # 分类用户内容
    subtitles = []
    bodies = []
    quotes = []
    content_images = []
    
    for s in sections:
        t = s.get('type', 'p')
        txt = s.get('text', '').strip()
        if t == 'h2' and txt:
            subtitles.append(txt)
        elif t == 'p' and txt:
            bodies.append(txt)
        elif t == 'blockquote' and txt:
            quotes.append(txt)
        elif t == 'img' and txt:
            content_images.append(txt)
    
    # 合并图片：sections中的img + images数组
    all_images = content_images + [img for img in images if img not in content_images]
    
    try:
        html = template['func'](title, digest, subtitles, bodies, quotes, all_images)
        return jsonify({
            'success': True,
            'html': html,
            'template_name': template['name'],
            'template_id': template_id,
            'stats': {
                'subtitles': len(subtitles),
                'bodies': len(bodies),
                'quotes': len(quotes),
                'images': len(all_images)
            }
        })
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'message': f'模板生成失败: {str(e)}', 'traceback': traceback.format_exc()})


@app.route('/admin/generation-records')
@admin_required
def admin_generation_records():
    return read_template('admin/generation_records.html')


# ============================================================
# 用户自定义文章模板 API
# ============================================================

@app.route('/api/article-templates', methods=['GET'])
@login_required
def list_article_templates():
    """获取模板列表：普通用户看自己的+公共的，管理员看全部"""
    db = get_db()
    uid = session['user_id']
    is_admin = session.get('role') == 'admin'

    if is_admin:
        rows = db.execute(
            'SELECT id, name, description, thumbnail, created_by, author_name, is_public, created_at, updated_at '
            'FROM article_templates ORDER BY is_public DESC, updated_at DESC'
        ).fetchall()
    else:
        rows = db.execute(
            'SELECT id, name, description, thumbnail, created_by, author_name, is_public, created_at, updated_at '
            'FROM article_templates WHERE created_by=? OR is_public=1 ORDER BY is_public DESC, updated_at DESC',
            (uid,)
        ).fetchall()

    templates = []
    for r in rows:
        templates.append({
            'id': r['id'],
            'name': r['name'],
            'description': r['description'] or '',
            'thumbnail': r['thumbnail'] or '',
            'created_by': r['created_by'],
            'author_name': r['author_name'] or '',
            'is_public': bool(r['is_public']) if r['is_public'] is not None else False,
            'is_owner': r['created_by'] == uid,
            'can_edit': r['created_by'] == uid or is_admin,
            'created_at': r['created_at'],
            'updated_at': r['updated_at']
        })
    return jsonify({'success': True, 'templates': templates, 'is_admin': is_admin})


@app.route('/api/article-templates/<int:tid>', methods=['GET'])
@login_required
def get_article_template(tid):
    """获取单个模板详情（owner/admin/公共均可访问）"""
    db = get_db()
    uid = session['user_id']
    is_admin = session.get('role') == 'admin'

    r = db.execute('SELECT * FROM article_templates WHERE id=?', (tid,)).fetchone()
    if not r:
        return jsonify({'success': False, 'message': '模板不存在'})

    # 权限：owner、admin、或公共模板 → 允许
    is_public = bool(r['is_public']) if r['is_public'] is not None else False
    is_owner = r['created_by'] == uid
    if not (is_owner or is_admin or is_public):
        return jsonify({'success': False, 'message': '无权访问此模板'})

    return jsonify({
        'success': True,
        'template': {
            'id': r['id'],
            'name': r['name'],
            'description': r['description'] or '',
            'blocks_json': r['blocks_json'],
            'thumbnail': r['thumbnail'] or '',
            'created_by': r['created_by'],
            'author_name': r['author_name'] or '',
            'is_public': is_public,
            'is_owner': is_owner,
            'can_edit': is_owner or is_admin,
            'is_admin': is_admin,
            'created_at': r['created_at'],
            'updated_at': r['updated_at']
        }
    })


@app.route('/api/article-templates/save', methods=['POST'])
@login_required
def save_article_template():
    """保存（新建或更新）模板 - 绑定当前用户"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '缺少数据'})
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': '请输入模板名称'})
    blocks_json = json.dumps(data.get('blocks', []), ensure_ascii=False)
    description = (data.get('description') or '').strip()
    thumbnail = data.get('thumbnail', '')
    tid = data.get('id')
    uid = session['user_id']
    is_admin = session.get('role') == 'admin'
    db = get_db()
    # 获取用户显示名
    user_row = db.execute('SELECT display_name, username FROM users WHERE id=?', (uid,)).fetchone()
    author_name = (user_row['display_name'] or user_row['username']) if user_row else ''

    if tid:
        # 更新：校验权限（owner或admin）
        existing = db.execute('SELECT created_by FROM article_templates WHERE id=?', (tid,)).fetchone()
        if not existing:
            return jsonify({'success': False, 'message': '模板不存在'})
        if existing['created_by'] != uid and not is_admin:
            return jsonify({'success': False, 'message': '无权编辑他人模板'})
        db.execute(
            'UPDATE article_templates SET name=?, description=?, blocks_json=?, thumbnail=?, author_name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
            (name, description, blocks_json, thumbnail, author_name, tid)
        )
        db.commit()
        return jsonify({'success': True, 'message': '模板已更新', 'id': tid})
    else:
        cur = db.execute(
            'INSERT INTO article_templates (name, description, blocks_json, thumbnail, created_by, author_name, is_public) VALUES (?, ?, ?, ?, ?, ?, 0)',
            (name, description, blocks_json, thumbnail, uid, author_name)
        )
        db.commit()
        return jsonify({'success': True, 'message': '模板已保存', 'id': cur.lastrowid})


@app.route('/api/article-templates/<int:tid>', methods=['DELETE'])
@login_required
def delete_article_template(tid):
    """删除模板（owner或admin）"""
    uid = session['user_id']
    is_admin = session.get('role') == 'admin'
    db = get_db()
    existing = db.execute('SELECT created_by FROM article_templates WHERE id=?', (tid,)).fetchone()
    if not existing:
        return jsonify({'success': False, 'message': '模板不存在'})
    if existing['created_by'] != uid and not is_admin:
        return jsonify({'success': False, 'message': '无权删除他人模板'})
    db.execute('DELETE FROM article_templates WHERE id=?', (tid,))
    db.commit()
    return jsonify({'success': True, 'message': '模板已删除'})


@app.route('/api/article-templates/<int:tid>/publish', methods=['POST'])
@admin_required
def publish_article_template(tid):
    """管理员将模板发布为公共模板"""
    db = get_db()
    existing = db.execute('SELECT id, is_public FROM article_templates WHERE id=?', (tid,)).fetchone()
    if not existing:
        return jsonify({'success': False, 'message': '模板不存在'})
    db.execute('UPDATE article_templates SET is_public=1, updated_at=CURRENT_TIMESTAMP WHERE id=?', (tid,))
    db.commit()
    return jsonify({'success': True, 'message': '已发布为公共模板，所有用户均可使用'})


@app.route('/api/article-templates/<int:tid>/unpublish', methods=['POST'])
@admin_required
def unpublish_article_template(tid):
    """管理员取消公共模板"""
    db = get_db()
    existing = db.execute('SELECT id, is_public FROM article_templates WHERE id=?', (tid,)).fetchone()
    if not existing:
        return jsonify({'success': False, 'message': '模板不存在'})
    db.execute('UPDATE article_templates SET is_public=0, updated_at=CURRENT_TIMESTAMP WHERE id=?', (tid,))
    db.commit()
    return jsonify({'success': True, 'message': '已取消公共发布'})


@app.route('/api/article-templates/<int:tid>/apply', methods=['POST'])
@login_required
def apply_article_template(tid):
    """应用用户自定义模板到文章内容"""
    db = get_db()
    r = db.execute('SELECT * FROM article_templates WHERE id=?', (tid,)).fetchone()
    if not r:
        return jsonify({'success': False, 'message': '模板不存在'})

    data = request.get_json() or {}
    title = data.get('title', '')
    digest = data.get('digest', '')
    sections = data.get('sections', [])
    images = data.get('images', [])

    try:
        blocks = json.loads(r['blocks_json'])
    except Exception:
        blocks = []

    # 分类用户内容
    user_titles = [title] if title else []
    user_subtitles = [s['text'] for s in sections if s.get('type') == 'h2' and s.get('text', '').strip()]
    user_bodies = [s['text'] for s in sections if s.get('type') == 'p' and s.get('text', '').strip()]
    user_quotes = [s['text'] for s in sections if s.get('type') == 'blockquote' and s.get('text', '').strip()]
    user_images = list(images)
    user_intro = [digest] if digest else []

    # 指针
    ptrs = {'title': 0, 'subtitle': 0, 'body': 0, 'quote': 0, 'image': 0, 'intro': 0}
    pools = {
        'title': user_titles,
        'subtitle': user_subtitles,
        'intro': user_intro,
        'body': user_bodies,
        'quote': user_quotes,
        'image': user_images,
    }

    def take(block_type):
        """从对应池取下一个内容，用完则降级到body"""
        # 先找精确匹配
        for bt in [block_type, 'body']:
            pool = pools.get(bt, [])
            idx = ptrs.get(bt, 0)
            if idx < len(pool):
                ptrs[bt] = idx + 1
                return pool[idx]
        return None

    # 构建HTML
    html_parts = []
    for blk in blocks:
        btype = blk.get('type', 'text')
        props = blk.get('props', {})

        if btype == 'divider':
            style_str = props.get('style', 'solid')
            color = props.get('color', '#ddd')
            thickness = props.get('thickness', 1)
            html_parts.append(f'<hr style="border:none;border-top:{thickness}px {style_str} {color};margin:{props.get("margin", 20)}px 0;">')
            continue

        if btype == 'image':
            img_src = take('image')
            if not img_src:
                # 保留模板原始图片（如果有）
                img_src = props.get('src', '')
            if img_src:
                width = props.get('width', '100%')
                radius = props.get('borderRadius', 8)
                align = props.get('align', 'center')
                margin = '0 auto' if align == 'center' else f'margin-{align}:0'
                html_parts.append(f'<img src="{img_src}" style="max-width:{width};border-radius:{radius}px;display:block;{margin};" />')
            continue

        # 文字类块
        text = ''
        if btype == 'title':
            text = take('title') or take('subtitle') or ''
        elif btype == 'subtitle':
            text = take('subtitle') or take('body') or ''
        elif btype == 'quote':
            text = take('quote') or take('body') or ''
        elif btype == 'intro':
            text = take('intro') or take('body') or ''
        else:
            text = take('body') or ''

        if not text:
            text = props.get('placeholder', '')

        # 构建样式
        styles = []
        if props.get('fontSize'):
            styles.append(f'font-size:{props["fontSize"]}px')
        if props.get('fontColor'):
            styles.append(f'color:{props["fontColor"]}')
        if props.get('fontWeight') and props['fontWeight'] != 'normal':
            styles.append(f'font-weight:{props["fontWeight"]}')
        if props.get('fontStyle') and props['fontStyle'] != 'normal':
            styles.append(f'font-style:{props["fontStyle"]}')
        if props.get('textAlign'):
            styles.append(f'text-align:{props["textAlign"]}')
        if props.get('lineHeight'):
            styles.append(f'line-height:{props["lineHeight"]}')
        if props.get('letterSpacing'):
            styles.append(f'letter-spacing:{props["letterSpacing"]}px')
        if props.get('backgroundColor') and props['backgroundColor'] != 'transparent':
            styles.append(f'background-color:{props["backgroundColor"]}')
        if props.get('padding'):
            styles.append(f'padding:{props["padding"]}px')
        if props.get('borderRadius'):
            styles.append(f'border-radius:{props["borderRadius"]}px')
        if props.get('marginTop'):
            styles.append(f'margin-top:{props["marginTop"]}px')
        if props.get('marginBottom'):
            styles.append(f'margin-bottom:{props["marginBottom"]}px')
        if btype == 'quote':
            border_color = props.get('borderColor', '#534ab7')
            styles.append(f'border-left:3px solid {border_color}')
            styles.append('padding-left:12px')
        style_attr = ';'.join(styles)

        tag = 'p'
        if btype == 'title':
            tag = 'h2'
        elif btype == 'subtitle':
            tag = 'h3'
        elif btype == 'quote':
            tag = 'blockquote'

        html_parts.append(f'<{tag} style="{style_attr}">{text}</{tag}>')

    result_html = '\n'.join(html_parts)
    filled = sum(1 for v in ptrs.values() if v > 0)

    return jsonify({
        'success': True,
        'html': result_html,
        'filled_count': filled,
        'template_name': r['name']
    })


# ============================================================
# 启动
# ============================================================

if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print("  百货商城系统已启动")
    print("  访问地址: http://0.0.0.0:5000")
    print("  管理员: admin / admin123")
    print("  顾客: customer1 / 123456")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
