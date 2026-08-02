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
import random
import urllib.parse
import uuid
import shutil
import threading
from datetime import datetime, timedelta
from functools import wraps
import requests
from flask import Flask, request, jsonify, session, redirect, url_for, g, send_file

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
        g.db.execute("PRAGMA busy_timeout=5000")
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

        CREATE TABLE IF NOT EXISTS saved_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT '',
            digest TEXT DEFAULT '',
            source TEXT DEFAULT '',
            sections_json TEXT DEFAULT '[]',
            images_json TEXT DEFAULT '[]',
            formatted_html TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );

        -- 初始化默认模板配色
        INSERT OR IGNORE INTO app_config (key, value) VALUES ('template_colors', '{}');

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

        -- 微信发布：定时发布任务
        CREATE TABLE IF NOT EXISTS scheduled_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            digest TEXT DEFAULT '',
            content TEXT DEFAULT '',
            author TEXT DEFAULT '',
            schedule_time TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            type TEXT DEFAULT 'single',
            detail TEXT DEFAULT '',
            published_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- 微信发布：批量发布队列
        CREATE TABLE IF NOT EXISTS publish_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            digest TEXT DEFAULT '',
            content TEXT DEFAULT '',
            author TEXT DEFAULT '',
            status TEXT DEFAULT 'queued',
            detail TEXT DEFAULT '',
            published_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- 微信发布：发布行为日志（用于后台数据分析）
        CREATE TABLE IF NOT EXISTS publish_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT CURRENT_TIMESTAMP,
            channel TEXT DEFAULT '',
            title TEXT DEFAULT '',
            status TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            type TEXT DEFAULT 'article'
        );

        -- 内置固定排版模板（可在后台「内置模板管理」增删改查）
        CREATE TABLE IF NOT EXISTS builtin_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT '通用',
            description TEXT DEFAULT '',
            accent TEXT DEFAULT '#888888',
            bg TEXT DEFAULT '#f0f0f0',
            style_json TEXT DEFAULT '{}',
            body_json TEXT DEFAULT '{}',
            header_html TEXT DEFAULT '',
            footer_html TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        "ALTER TABLE article_templates ADD COLUMN template_type TEXT DEFAULT 'style'",
        # 微信定时/批量发布：到时动作（publish=发布 / draft=仅建草稿）+ 草稿 media_id
        "ALTER TABLE scheduled_posts ADD COLUMN mode TEXT DEFAULT 'publish'",
        "ALTER TABLE scheduled_posts ADD COLUMN media_id TEXT DEFAULT ''",
        "ALTER TABLE publish_queue ADD COLUMN mode TEXT DEFAULT 'publish'",
        "ALTER TABLE publish_queue ADD COLUMN media_id TEXT DEFAULT ''",
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

    # 内置固定排版模板：首次启动写入数据库（后台可增删改查）
    seed_builtin_templates(c)

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
                return jsonify({'success': False, 'message': '请先登录', 'need_login': True}), 401
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
# 应用中心 - 系统注册表
# 新增一个独立系统/网页，只需在此添加一项，工作台会自动展示
# role: 'all' 表示所有登录用户可见，'admin' 仅管理员可见
# ============================================================
APP_REGISTRY = [
    {'id': 'mall', 'name': '商城系统', 'desc': '浏览商品、购物车与订单管理', 'icon': '🛒', 'url': '/store', 'role': 'all'},
    {'id': 'publish', 'name': 'AI创作公众号', 'desc': 'AI 生成并发布公众号文章到草稿箱', 'icon': '✍️', 'url': '/publish', 'role': 'all'},
    {'id': 'admin', 'name': '管理后台', 'desc': '统一管理商城与发布数据', 'icon': '⚙️', 'url': '/admin', 'role': 'admin'},
]


# ============================================================
# 页面路由
# ============================================================

@app.route('/')
def index():
    """5000 端口首页 = 统一登录入口（登录后直达工作台）"""
    if 'user_id' in session:
        return redirect(url_for('portal'))
    return read_template('login.html')


@app.route('/store')
@login_required
def store_home():
    """商城系统首页 - 需登录后通过工作台进入"""
    log_visit('store')
    return read_template('store/index.html')


@app.route('/portal')
@login_required
def portal():
    """应用中心 / 工作台 - 登录后选择进入哪个系统"""
    return read_template('portal.html')


@app.route('/api/portal/apps')
@login_required
def api_portal_apps():
    """返回当前用户可见的系统列表（按角色过滤）"""
    role = session.get('role', 'customer')
    apps = [a for a in APP_REGISTRY if a['role'] in ('all', role)]
    return jsonify({
        'success': True,
        'apps': apps,
        'user': {
            'display_name': session.get('display_name', ''),
            'role': role
        }
    })


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
def admin_portal():
    return read_template('admin/portal.html')


@app.route('/admin/mall')
@admin_required
def admin_mall_dashboard():
    return read_template('admin/dashboard.html')


@app.route('/admin/wechat')
@admin_required
def admin_wechat_console():
    return read_template('admin/wechat.html')


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


@app.route('/admin/template-designer')
@admin_required
def admin_template_designer():
    """管理员可视化拖拽创作模块（可发布模板给所有用户）"""
    return read_template('admin/template_designer.html')


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


@app.route('/api/publish/upload-reference', methods=['POST'])
@login_required
def api_publish_upload_reference():
    """上传 AI 生成的参考资料：图片或文档。

    图片：保存到 static/uploads，返回本地文件名供生成时调用视觉接口描述。
    文档（txt/md/json/csv/pdf）：提取文本内容返回。
    返回: {success, data:{url, name, ftype, text, filename}}
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有文件'})
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '文件名为空'})

    original = file.filename
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
    safe_base = re.sub(r'[^A-Za-z0-9_\-]', '', original.rsplit('.', 1)[0])[:40] or 'ref'
    filename = f"{safe_base}_{int(time.time() * 1000)}.{ext}" if ext else f"{safe_base}_{int(time.time() * 1000)}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    url = f'/static/uploads/{filename}'

    IMG_EXT = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']
    DOC_EXT = ['txt', 'md', 'markdown', 'json', 'csv', 'log', 'text', 'pdf']

    if ext in IMG_EXT:
        return jsonify({'success': True, 'data': {
            'url': url, 'name': original, 'ftype': 'image', 'text': '', 'filename': filename
        }})
    elif ext in DOC_EXT:
        text = ''
        try:
            if ext == 'pdf':
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(filepath)
                    text = '\n'.join((p.extract_text() or '') for p in reader.pages)
                except Exception:
                    text = ''  # PDF 解析依赖 pypdf，未安装或解析失败则跳过
            else:
                # 优先 UTF-8；Windows 记事本默认 GBK，失败回退 GBK，再回退忽略
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        text = f.read()
                except (UnicodeDecodeError, UnicodeError):
                    try:
                        with open(filepath, 'r', encoding='gbk') as f:
                            text = f.read()
                    except Exception:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            text = f.read()
        except Exception:
            text = ''
        text = text[:6000]
        return jsonify({'success': True, 'data': {
            'url': url, 'name': original, 'ftype': 'doc', 'text': text, 'filename': filename
        }})
    else:
        # 不支持的类型：仍保存并返回，但标记为未知，提示用户
        return jsonify({'success': False, 'message': f'不支持的参考资料格式：.{ext}（仅支持图片与 txt/md/json/csv/pdf 文档）'})


# ============================================================
# 公众号 AI 创作发布平台
# ============================================================

@app.route('/publish')
@login_required
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


@app.route('/api/publish/my-records', methods=['GET'])
@login_required
def api_my_records():
    """获取当前用户的发布记录（用于历史面板展示）"""
    db = get_db()
    uid = session['user_id']
    rows = db.execute("""
        SELECT id, action_type, title, status, draft_media_id, created_at
        FROM generation_records WHERE user_id=? AND action_type IN ('create_draft','save_draft','ai_generate')
        ORDER BY created_at DESC LIMIT 50
    """, (uid,)).fetchall()
    records = [{
        'id': r['id'],
        'type': r['action_type'],
        'title': r['title'] or '',
        'status': r['status'],
        'draft_media_id': r['draft_media_id'] or '',
        'created_at': r['created_at']
    } for r in rows]
    return jsonify({'success': True, 'records': records})


@app.route('/api/publish/save-draft', methods=['POST'])
@login_required
def api_save_draft():
    """保存草稿到服务器（含完整 sections/images/排版HTML），支持新建和更新"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '缺少数据'})
    db = get_db()
    uid = session['user_id']
    draft_id = data.get('id')
    title = (data.get('title') or '').strip()
    digest = (data.get('digest') or '').strip()
    source = (data.get('source') or '').strip()
    sections_json = json.dumps(data.get('sections', []), ensure_ascii=False)
    images_json = json.dumps(data.get('images', []), ensure_ascii=False)
    formatted_html = data.get('formatted_html') or ''

    if draft_id:
        # 更新已有草稿（只更新自己名下的）
        row = db.execute('SELECT id FROM saved_drafts WHERE id=? AND user_id=?', (draft_id, uid)).fetchone()
        if not row:
            return jsonify({'success': False, 'message': '草稿不存在或无权修改'})
        db.execute("""
            UPDATE saved_drafts SET title=?, digest=?, source=?, sections_json=?, images_json=?, formatted_html=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (title, digest, source, sections_json, images_json, formatted_html, draft_id))
    else:
        cursor = db.execute("""
            INSERT INTO saved_drafts (user_id, title, digest, source, sections_json, images_json, formatted_html)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (uid, title, digest, source, sections_json, images_json, formatted_html))
        draft_id = cursor.lastrowid
    db.commit()
    return jsonify({'success': True, 'id': draft_id})


@app.route('/api/publish/my-drafts', methods=['GET'])
@login_required
def api_my_drafts():
    """获取当前用户的草稿列表（含标题和时间，不含完整内容）"""
    db = get_db()
    uid = session['user_id']
    rows = db.execute("""
        SELECT id, title, digest, source, created_at, updated_at
        FROM saved_drafts WHERE user_id=? ORDER BY updated_at DESC
    """, (uid,)).fetchall()
    drafts = [{
        'id': r['id'],
        'title': r['title'] or '',
        'digest': r['digest'] or '',
        'source': r['source'] or '',
        'created_at': r['created_at'],
        'updated_at': r['updated_at']
    } for r in rows]
    return jsonify({'success': True, 'drafts': drafts})


@app.route('/api/publish/my-drafts/<int:draft_id>', methods=['GET'])
@login_required
def api_get_my_draft(draft_id):
    """获取单个草稿完整内容"""
    db = get_db()
    uid = session['user_id']
    is_admin = session.get('role') == 'admin'
    row = db.execute("""
        SELECT * FROM saved_drafts WHERE id=?
    """, (draft_id,)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '草稿不存在'})
    if row['user_id'] != uid and not is_admin:
        return jsonify({'success': False, 'message': '无权访问此草稿'})
    return jsonify({
        'success': True,
        'draft': {
            'id': row['id'],
            'title': row['title'] or '',
            'digest': row['digest'] or '',
            'source': row['source'] or '',
            'sections': json.loads(row['sections_json'] or '[]'),
            'images': json.loads(row['images_json'] or '[]'),
            'formatted_html': row['formatted_html'] or '',
            'created_at': row['created_at'],
            'updated_at': row['updated_at']
        }
    })


@app.route('/api/publish/my-drafts/<int:draft_id>', methods=['DELETE'])
@login_required
def api_delete_my_draft(draft_id):
    """删除草稿"""
    db = get_db()
    uid = session['user_id']
    row = db.execute('SELECT id FROM saved_drafts WHERE id=? AND user_id=?', (draft_id, uid)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '草稿不存在或无权删除'})
    db.execute('DELETE FROM saved_drafts WHERE id=?', (draft_id,))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/template-colors', methods=['GET'])
def api_get_template_colors():
    """获取内置模板配色（无需登录，用于前端加载）"""
    db = get_db()
    row = db.execute("SELECT value FROM app_config WHERE key='template_colors'").fetchone()
    if row and row['value']:
        try: data = json.loads(row['value'])
        except: data = {}
    else:
        data = {}
    return jsonify({'success': True, 'colors': data})


@app.route('/api/admin/template-colors', methods=['POST'])
@admin_required
def api_save_template_colors():
    """保存内置模板配色（管理员）"""
    data = request.get_json()
    if not data or 'colors' not in data:
        return jsonify({'success': False, 'message': '缺少配色数据'})
    db = get_db()
    db.execute("REPLACE INTO app_config (key, value) VALUES (?, ?)",
               ('template_colors', json.dumps(data['colors'], ensure_ascii=False)))
    db.commit()
    return jsonify({'success': True})


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

# HuggingFace 视觉描述接口 Token（可选）。留空则匿名调用免费接口（有速率限制）。
# 配置方式：项目根目录 .env 写入 HF_API_TOKEN=你的token，可显著提升稳定性。
HF_API_TOKEN = os.environ.get('HF_API_TOKEN', '')

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


def with_retry(fn, *args, retries=3, backoff=1.5, what='操作', **kwargs):
    """指数退避重试：失败重试最多 retries 次，间隔 backoff*2^尝试 秒。用于抓取/生成等外部调用。"""
    last = None
    for i in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last = e
            if i < retries - 1:
                time.sleep(backoff * (2 ** i))
    raise last


def _search_news(query, config, count=5):
    """统一搜索入口：按 search_provider 分发；失败自动重试并降级到 RSS 兜底。"""
    provider = config.get('search_provider', 'tavily')
    api_key = config.get('search_api_key', '')

    try:
        if provider == 'tavily' and api_key:
            return with_retry(_tavily_search, query, api_key, count, retries=3, what='Tavily搜索')
        elif provider == 'bing' and api_key:
            return with_retry(_bing_search_news, query, api_key, count, retries=3, what='Bing搜索')
    except Exception:
        pass
    # 降级：RSS 抓取兜底（无需 API key）
    return with_retry(_rss_search, query, count, retries=2, what='RSS抓取')


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


def _deepseek_generate(topic, news_results, style_profile, api_key,
                       image_mode='auto', image_style='tech', max_images=4, skip_images=False,
                       reference_text='', user_image_count=0, word_count=0, image_count=0):
    """调用 DeepSeek API 生成公众号文章（结构化 blocks 输出）

    返回 dict: {title, digest, content(纯文字HTML兜底), blocks:[...]}
    blocks 元素:
      {"type":"h2"/"p"/"blockquote", "text":"..."}
      {"type":"image", "caption":"中文图注", "prompt":"English image-gen prompt"}

    reference_text: 用户提供的参考资料（参考图描述 + 文档文本 + 历史案例），作为写作依据。
    """
    # 构建新闻素材文本
    news_text = ""
    for i, news in enumerate(news_results, 1):
        news_text += f"【{i}】{news['title']}\n来源：{news['source']}\n摘要：{news['description']}\n\n"

    # 是否让模型产出图片块
    # 用户勾选了参考图作为正文图时，即使 skip_images 也要产出 image 块（位置由模型规划，内容用用户图回填）
    # 字数 / 图片数量 由调用方通过 word_count / image_count 指定（>0 时生效）
    force_images = (user_image_count > 0) or (image_count > 0)
    allow_images = force_images or ((not skip_images) and image_mode in ('auto', 'gallery', 'cover_only'))
    if user_image_count > 0:
        max_images = max(max_images, user_image_count)
    if image_count > 0:
        max_images = max(max_images, image_count)

    system_prompt = """你是一个专业的微信公众号科技资讯编辑。请根据提供的新闻素材，生成一篇排版精美的公众号文章。

严格要求：
1. 标题控制在20个中文字以内（64字节限制）
2. 摘要控制在40个中文字以内（120字节限制）
3. 正文500-1000字，语言流畅专业
4. 严禁使用任何emoji表情符号
5. 严禁使用「」等特殊引号，只用普通中文引号
6. 结尾加一段简短的编辑点评

请按"语义段落"结构化组织文章，返回 JSON：
{
  "title": "文章标题",
  "digest": "文章摘要",
  "blocks": [
    {"type": "h2", "text": "小标题"},
    {"type": "p", "text": "一段正文"},
    {"type": "blockquote", "text": "引用内容"},
    {"type": "image", "caption": "该段对应的中文图注", "prompt": "English prompt describing the visual for THIS section, no text in image"}
  ]
}
block 类型只允许 h2 / p / blockquote / image 四种。
普通正文段落用 type=p，小标题用 type=h2，引用用 type=blockquote。"""

    if allow_images:
        # 图片插入规则：按语义分段，每个相对独立的话题结束后插一张图
        if image_mode == 'gallery':
            system_prompt += (f"\n\n【配图模式：图集】以图片为主。每个 block 尽量是 image 类型"
                              f"（配简短中文 caption），正文文字尽量精简。最多插入 {max_images} 张图。")
        elif image_mode == 'cover_only':
            system_prompt += "\n\n【配图模式：仅封面】只在文章最开头插入 1 个 image 块作为封面图，正文不再插其他图。"
        else:
            system_prompt += (f"\n\n【配图模式：自动】将文章按语义分成若干小节；每个相对独立的话题/小节结束后，"
                              f"插入一个 image 块，其 prompt 用英语描述该小节的核心画面（不要出现文字），"
                              f"caption 用中文写该图注。不要每句都配图，一张图对应一个完整话题即可。最多插入 {max_images} 张图。")
    if user_image_count > 0:
        system_prompt += (f"\n\n【图片来源：用户真实图片】你必须插入恰好 {user_image_count} 个 image 块，"
                          f"这些图片由用户直接提供（你不需要、也不会生成图片，只需规划它们的位置）。"
                          f"把这 {user_image_count} 个 image 块分散插入到不同话题小节结束后，穿插在正文不同位置，不要堆在开头或结尾；"
                          f"每个 image 块的 caption 用中文写该图对应的图注，prompt 用英语描述该图应有的画面（仅用于备选，不实际生成）。")
    else:
        system_prompt += "\n\n【配图模式：纯文字 / 用户已提供图片】不要输出任何 image 块，只输出 h2 / p / blockquote 文字块。"

    if image_count > 0:
        system_prompt += (f"\n\n【图片数量控制】你必须插入恰好 {image_count} 个 image 块，"
                          f"caption 用中文写图注，prompt 用英语描述该图应有的画面（不要出现文字），"
                          f"把它们分散插入到不同话题小节结束后，不要堆在开头或结尾。")

    system_prompt += """

最后请再用 blocks 拼出一段完整 HTML 正文放入 content 字段（仅文字，section + p 标签，禁止多层 div），用于兜底。

content 文字块示例：
小标题 <p style="font-size:17px;font-weight:bold;color:#2c3e50;margin:25px 0 12px 0;">标题</p>
正文 <p style="margin-bottom:15px;">内容</p>"""

    if style_profile:
        system_prompt += f"\n\n参考排版风格：{json.dumps(style_profile, ensure_ascii=False)}"

    if reference_text:
        system_prompt += ("\n\n【参考资料】用户额外提供了参考素材（可能是参考图片的画面描述、参考文档内容、以往案例文章，或参考网页文章）。"
                          "请充分理解这些参考资料的主题、风格与要点，使生成文章在主题契合度、行文风格、专业度上与之呼应；"
                          "若参考资料中包含【参考网页文章】及其【图片位置要求】，你必须严格参照该文的行文风格"
                          "（小标题用法、语气、段落节奏）并在对应小节/话题结束后按其所要求的图片位置插入 image 块；"
                          "但必须基于真实新闻素材写作，不得编造参考资料与新闻中均无依据的事实。")
        user_prompt = f"主题方向：{topic}\n\n新闻素材：\n{news_text}\n\n参考资料：\n{reference_text}\n\n请生成公众号文章。"
    else:
        user_prompt = f"主题方向：{topic}\n\n新闻素材：\n{news_text}\n\n请生成公众号文章。"

    # 字数控制：按输入字数调整正文字数要求与输出 token 上限
    if word_count and word_count > 0:
        system_prompt = system_prompt.replace(
            '正文500-1000字', '正文约 %d 字（控制在 %d±15%% 范围内）' % (word_count, word_count))
        max_tokens = max(4096, min(8000, int(word_count) * 2 + 1500))
    else:
        max_tokens = 4096

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
        'max_tokens': max_tokens,
        'response_format': {'type': 'json_object'}
    }

    resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
    data = resp.json()

    if 'choices' not in data:
        error_msg = data.get('error', {}).get('message', resp.text[:200]) if isinstance(data, dict) else str(data)[:200]
        raise Exception(f"DeepSeek 生成失败: {error_msg}")

    result = json.loads(data['choices'][0]['message']['content'])

    # 兜底：若模型没返回 blocks，尝试从 content 解析为单一 p 块
    blocks = result.get('blocks')
    if not isinstance(blocks, list) or not blocks:
        content = result.get('content', '')
        blocks = [{'type': 'p', 'text': content}] if content else []

    # 组装 content（仅文字块，图片块交给前端/后端后续注入）
    html = '<section style="font-size:15px;color:#3f3f3f;line-height:1.8;">\n'
    for b in blocks:
        t = b.get('type')
        txt = (b.get('text') or '').strip()
        if t == 'h2':
            html += f'<p style="font-size:17px;font-weight:bold;color:#2c3e50;margin:25px 0 12px 0;">{txt}</p>\n'
        elif t == 'blockquote':
            html += f'<blockquote style="border-left:3px solid #534ab7;padding:8px 12px;margin:12px 0;background:#f8f9fa;color:#666;border-radius:0 6px 6px 0;">{txt}</blockquote>\n'
        elif t == 'image':
            continue  # 图片块不进兜底 content
        else:
            if txt:
                html += f'<p style="margin-bottom:15px;">{txt}</p>\n'
    html += '</section>'
    result['content'] = result.get('content') or html
    result['blocks'] = blocks
    return result


def _fill_user_images(blocks, user_images):
    """把用户勾选的真实图片回填进 image 块：按顺序填充；数量不匹配时增减 image 块。

    - user_images: 有序的真实图片 URL 列表（用户勾选的参考图）
    - 返回处理后的 blocks（image 块带 resolved_url 字段，前端据此直接渲染，不再调用生图接口）
    """
    if not user_images:
        return blocks
    blocks = list(blocks or [])
    image_idxs = [i for i, b in enumerate(blocks) if isinstance(b, dict) and b.get('type') == 'image']
    n_need = len(user_images)
    n_have = len(image_idxs)
    # 1) 顺序填充已有的 image 块
    for k, idx in enumerate(image_idxs):
        if k < n_need:
            blocks[idx]['resolved_url'] = user_images[k]
    # 2) 用户图多于 image 块：在最后一个非 image 块之后追加
    if n_need > n_have:
        extra = user_images[n_have:]
        last = len(blocks) - 1
        while last >= 0 and blocks[last].get('type') == 'image':
            last -= 1
        insert_at = last + 1 if last >= 0 else len(blocks)
        for url in extra:
            blocks.insert(insert_at, {'type': 'image', 'caption': '', 'prompt': '', 'resolved_url': url})
            insert_at += 1
    # 3) 用户图少于 image 块：丢弃末尾多余的空 image 块
    elif n_need < n_have:
        drop = set(image_idxs[n_need:])
        blocks = [b for i, b in enumerate(blocks) if i not in drop]
    return blocks


def _pollinations_image(prompt, image_style='tech'):
    """调用 Pollinations 免费文生图接口，返回本地临时 PNG 路径。

    Pollinations 无需 API Key，云服务器可直接 HTTP 调用。
    """
    style_suffix = {
        'tech': ' tech style, blue purple gradient, clean, modern, futuristic, no text',
        'realistic': ' realistic photo, cinematic lighting, no text',
        'flat': ' flat illustration, minimal vector, no text',
    }.get(image_style, ' clean composition, no text')
    full_prompt = (prompt or 'technology abstract') + style_suffix
    full_prompt = full_prompt[:1500]

    url = 'https://image.pollinations.ai/prompt/' + urllib.parse.quote(full_prompt) \
          + '?width=1280&height=720&nologo=true&model=flux&seed=' + str(random.randint(1, 999999))
    resp = requests.get(url, timeout=60)
    if resp.status_code != 200 or not resp.content:
        raise Exception(f'Pollinations 返回异常: HTTP {resp.status_code}')

    import tempfile, uuid
    path = os.path.join(tempfile.gettempdir(), f'poll_{uuid.uuid4().hex[:8]}.png')
    with open(path, 'wb') as f:
        f.write(resp.content)
    return path


HF_CAPTION_MODEL = 'Salesforce/blip-image-captioning-base'


def _hf_image_caption(image_bytes):
    """用 HuggingFace 免费图像描述接口为图片生成粗略文字描述（无需 Key 即可匿名调用）。

    返回图片的英文画面描述字符串；若接口不可用（401/403/429/超时/空）则优雅返回空串，
    调用方据此跳过图片分析、仅用文字素材生成，不阻断主流程。
    """
    url = f'https://api-inference.huggingface.co/models/{HF_CAPTION_MODEL}'
    headers = {'Content-Type': 'application/octet-stream'}
    if HF_API_TOKEN:
        headers['Authorization'] = f'Bearer {HF_API_TOKEN}'
    try:
        resp = requests.post(url, headers=headers, data=image_bytes, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get('generated_text'):
                return data[0]['generated_text'].strip()
        return ''
    except Exception:
        return ''


def _fetch_web_article(url, timeout=20):
    """抓取网页文章，分析其行文风格与图片插入位置，供 DeepSeek 参照创作。

    返回 dict: {url, title, summary, image_positions:[第N个p段之后...], style:{...}}
    失败（超时/非 http/解析失败）返回 None，调用方应优雅跳过、不阻断生成。
    """
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        if not (url.startswith('http://') or url.startswith('https://')):
            return None
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return None
        resp.encoding = resp.apparent_encoding or 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside',
                         'noscript', 'svg', 'form', 'button', 'iframe']):
            tag.decompose()

        # 标题
        title = ''
        og = soup.find('meta', attrs={'property': 'og:title'}) or soup.find('meta', attrs={'name': 'og:title'})
        if og and og.get('content'):
            title = og['content'].strip()
        if not title:
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text(strip=True)
        if not title and soup.title:
            title = soup.title.get_text(strip=True)
        title = (title or '').strip()

        # 主内容容器（优先 article/main，回退 body）
        container = soup.find('article') or soup.find('main') or soup.body
        if not container:
            return None

        para_count = 0
        image_positions = []
        text_parts = []
        for el in container.descendants:
            name = getattr(el, 'name', None)
            if name in ('p', 'h2', 'h3'):
                txt = el.get_text(strip=True)
                if not txt or len(txt) < 2:
                    continue
                if name in ('h2', 'h3'):
                    text_parts.append('【小标题】' + txt)
                else:
                    text_parts.append(txt)
                    para_count += 1
            elif name == 'img':
                src = (el.get('data-src') or el.get('src') or el.get('data-original')
                       or el.get('data-lazy-src') or '')
                if not src or src.startswith('data:'):
                    continue
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(url, src)
                image_positions.append(para_count)

        p_count = para_count
        h2_count = sum(1 for t in text_parts if t.startswith('【小标题】'))
        img_count = len(image_positions)
        total = p_count + h2_count
        density = (img_count / total) if total else 0
        if density >= 0.3:
            dens_label = '高（图文密集）'
        elif density >= 0.1:
            dens_label = '中（图文相间）'
        else:
            dens_label = '低（以文字为主）'
        summary = ' '.join(t.replace('【小标题】', '') for t in text_parts)[:1500]

        return {
            'url': url,
            'title': title or '(无标题)',
            'summary': summary,
            'image_positions': image_positions,
            'style': {
                'paragraph_count': p_count,
                'subtitle_count': h2_count,
                'image_count': img_count,
                'image_density': dens_label,
                'image_positions': image_positions,
            }
        }
    except Exception as e:
        app.logger.warning(f'_fetch_web_article failed for {url}: {e}')
        return None


def _build_reference_text(references, use_history, user_id, web_articles=None):
    """把用户上传的参考图/文档与历史案例拼成一段文字，供 DeepSeek 参考。

    图片经 HuggingFace 免费接口生成粗略画面描述；文档直接取文本；历史案例取该用户最近的生成记录。
    """
    parts = []

    def _pos_desc(positions):
        if not positions:
            return '无配图'
        items = []
        for p in positions:
            items.append('开头' if p == 0 else f'第{p}段之后')
        return '、'.join(items)

    # 网页参考（AI 自动打开网址分析文章风格与图片位置）
    for wa in (web_articles or [])[:5]:
        if not wa:
            continue
        s = wa.get('style', {}) or {}
        positions = wa.get('image_positions', []) or []
        pos_desc = _pos_desc(positions)
        style_line = (f"风格特征：共 {s.get('paragraph_count', 0)} 个正文段、"
                      f"{s.get('subtitle_count', 0)} 个小标题、配图 {s.get('image_count', 0)} 张"
                      f"（密度 {s.get('image_density', '')}）；图片分别出现在 {pos_desc}。")
        web_part = (
            f"【参考网页文章】链接：{wa.get('url', '')}\n"
            f"标题：《{wa.get('title', '')}》\n"
            f"{style_line}\n"
            f"正文摘要（请体会其行文语气、段落节奏与小标题用法）：\n{wa.get('summary', '')[:1200]}\n"
            f"【图片位置要求】请严格参照该文的配图节奏来插入配图：在你文章对应的小节/话题结束后插入 image 块，"
            f"使图片位置分布尽量与该文一致（即大约 {pos_desc}）。不要改变主题，只借鉴其风格与配图节奏。"
        )
        parts.append(web_part)

    img_idx = 0
    for ref in (references or [])[:8]:
        ftype = ref.get('ftype')
        if ftype == 'image':
            fn = ref.get('filename')
            caption = ''
            if fn:
                path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
                if os.path.exists(path):
                    try:
                        with open(path, 'rb') as f:
                            caption = _hf_image_caption(f.read())
                    except Exception:
                        caption = ''
            img_idx += 1
            if caption:
                parts.append(f"参考图{img_idx}（画面描述）：{caption}")
            else:
                parts.append(f"参考图{img_idx}：用户上传的参考图片（当前环境未能自动识别画面，请结合主题理解）。")
        elif ftype == 'doc':
            name = ref.get('name', '文档')
            text = (ref.get('text') or '').strip()
            if text:
                parts.append(f"参考文档《{name}》：\n{text[:4000]}")
    if use_history and user_id:
        try:
            db = get_db()
            rows = db.execute(
                "SELECT title, detail FROM generation_records WHERE user_id=? AND status='success' ORDER BY id DESC LIMIT 3",
                (user_id,)
            ).fetchall()
            for i, r in enumerate(rows, 1):
                detail = (r['detail'] or '').strip()[:1500]
                parts.append(f"历史案例{i}（标题：{r['title']}）：\n{detail}")
        except Exception:
            pass
    text = '\n\n'.join(parts).strip()
    return text[:12000]


@app.route('/api/publish/generate-images', methods=['POST'])
def api_publish_generate_images():
    """根据图片提示词逐张生成配图（Pollinations 免费接口），上传微信返回 URL。

    请求体: {appid, appsecret, image_style, images:[{index, prompt}]}
    返回: {success, results:[{index, url, preview_url}], errors:[{index, message}]}

    注意：url 是微信 URL（发布草稿用），preview_url 是本服务器预览 URL（浏览器 <img> 用）。
    微信 URL 有 Referer 防盗链，不能直接在浏览器 <img> 中显示。
    """
    data = request.get_json()
    appid = (data.get('appid') or '').strip()
    appsecret = (data.get('appsecret') or '').strip()
    image_style = data.get('image_style', 'tech')
    img_list = data.get('images', []) or []

    if not appid or not appsecret:
        return jsonify({'success': False, 'message': '请先配置微信 AppID 和 AppSecret'})
    if not img_list:
        return jsonify({'success': True, 'results': [], 'errors': []})

    # 确保预览图目录存在
    preview_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'generated_images')
    os.makedirs(preview_dir, exist_ok=True)

    try:
        # 获取 access_token
        token_resp = requests.get('https://api.weixin.qq.com/cgi-bin/token', params={
            'grant_type': 'client_credential', 'appid': appid, 'secret': appsecret
        }, timeout=15).json()
        if 'access_token' not in token_resp:
            return jsonify({'success': False, 'message': f'获取token失败: {token_resp.get("errmsg", token_resp)}'})
        access_token = token_resp['access_token']
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取token失败: {str(e)}'})

    results = []
    errors = []
    for item in img_list:
        idx = item.get('index')
        prompt = (item.get('prompt') or '').strip()
        if not prompt:
            errors.append({'index': idx, 'message': '空的图片提示词'})
            continue
        try:
            # 1. Pollinations 生图 → 本地临时文件
            local_path = _pollinations_image(prompt, image_style)

            # 2. 复制一份到 static/generated_images/ 用于浏览器预览（绕过微信防盗链）
            preview_filename = f'gen_{uuid.uuid4().hex[:12]}.png'
            preview_path = os.path.join(preview_dir, preview_filename)
            shutil.copy2(local_path, preview_path)
            preview_url = f'/static/generated_images/{preview_filename}'

            # 3. 上传到微信内容图（uploadimg 返回可引用 URL，仅用于发布草稿）
            with open(local_path, 'rb') as f:
                up = requests.post(
                    'https://api.weixin.qq.com/cgi-bin/media/uploadimg',
                    params={'access_token': access_token},
                    files={'media': (os.path.basename(local_path), f, 'image/png')},
                    timeout=60
                ).json()
            if 'url' not in up:
                errors.append({'index': idx, 'message': f'微信上传失败: {up.get("errmsg", up)}'})
                continue
            results.append({'index': idx, 'url': up['url'], 'preview_url': preview_url})
        except Exception as e:
            errors.append({'index': idx, 'message': str(e)})

    return jsonify({'success': True, 'results': results, 'errors': errors})


# ===================== 本地图片上传到微信 CDN（复制/发布给公众号用） =====================
_WX_IMG_CACHE = {}  # 本地图片路径 -> 微信 url 缓存，避免重复上传

@app.route('/api/publish/upload-to-wechat', methods=['POST'])
@login_required
def api_publish_upload_to_wechat():
    """把本网站（static/uploads 或 static/generated_images）的图片上传到微信内容图 CDN，
    返回微信可引用的 url。微信公众号只认自家 CDN 图片，粘贴外链会被防盗链/抓取限制挡掉，
    所以复制/发布前必须把本地图片换成微信 url（mmbiz.qpic.cn）。"""
    import requests
    from urllib.parse import urlparse
    data = request.get_json() or {}
    url = (data.get('url') or '').strip()
    filename = (data.get('filename') or '').strip()

    local_path = None
    if filename:
        p1 = os.path.join('static', 'uploads', os.path.basename(filename))
        p2 = os.path.join('static', 'generated_images', os.path.basename(filename))
        if os.path.exists(p1):
            local_path = p1
        elif os.path.exists(p2):
            local_path = p2
    elif url:
        if url.startswith('http://') or url.startswith('https://'):
            parsed = urlparse(url)
            rel = parsed.path.lstrip('/')
            cand = rel
            if os.path.exists(cand):
                local_path = cand
        else:
            cand = url.lstrip('/')
            if os.path.exists(cand):
                local_path = cand

    if not local_path or not os.path.exists(local_path):
        return jsonify({'success': False, 'message': '找不到本地图片文件: ' + str(url or filename)})

    if local_path in _WX_IMG_CACHE:
        return jsonify({'success': True, 'url': _WX_IMG_CACHE[local_path]})

    # 读取微信凭据
    db = get_db()
    row = db.execute("SELECT value FROM store_settings WHERE key='wechat_appid'").fetchone()
    appid = row['value'] if row else ''
    row = db.execute("SELECT value FROM store_settings WHERE key='wechat_appsecret'").fetchone()
    appsecret = row['value'] if row else ''
    if not appid or not appsecret:
        return jsonify({'success': False, 'message': '未配置微信 AppID/AppSecret'})

    try:
        token_resp = requests.get('https://api.weixin.qq.com/cgi-bin/token',
                                  params={'grant_type': 'client_credential', 'appid': appid, 'secret': appsecret},
                                  timeout=15).json()
        if 'access_token' not in token_resp:
            return jsonify({'success': False, 'message': '获取微信token失败: ' + token_resp.get('errmsg', str(token_resp))})
        access_token = token_resp['access_token']

        ext = local_path.lower()
        if ext.endswith('.png'):
            mime = 'image/png'
        elif ext.endswith(('.jpg', '.jpeg')):
            mime = 'image/jpeg'
        elif ext.endswith('.gif'):
            mime = 'image/gif'
        else:
            mime = 'image/png'
        with open(local_path, 'rb') as f:
            up = requests.post('https://api.weixin.qq.com/cgi-bin/media/uploadimg',
                               params={'access_token': access_token},
                               files={'media': (os.path.basename(local_path), f, mime)},
                               timeout=60).json()
        if 'url' not in up:
            return jsonify({'success': False, 'message': '微信上传失败: ' + up.get('errmsg', str(up))})
        _WX_IMG_CACHE[local_path] = up['url']
        return jsonify({'success': True, 'url': up['url']})
    except Exception as e:
        return jsonify({'success': False, 'message': '上传异常: ' + str(e)})


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

    # 配图参数
    image_mode = data.get('image_mode', 'auto')          # auto / none / gallery / cover_only
    image_style = data.get('image_style', 'tech')        # tech / realistic / flat
    max_images = int(data.get('max_images', 4))
    has_user_images = bool(data.get('has_user_images', False))  # 用户已提供图片则不AI生图
    # 字数 / 图片数量（>0 时生效；图片数>0 且模式为 none 时强制生图）
    word_count = int(data.get('word_count', 0) or 0)
    image_count = int(data.get('image_count', 0) or 0)
    if image_count > 0 and image_mode == 'none':
        image_mode = 'auto'

    # 参考资料（上传的参考图/文档）、历史案例、参考网页
    references = data.get('references', []) or []        # [{ftype, text, filename, name}]
    use_history = bool(data.get('use_history', False))
    web_urls = data.get('web_urls', []) or []
    # 用户勾选「用作正文图」的参考图（有序的真实图片 URL）；非空时 AI 不再自动生图，改用这些图
    selected_images = data.get('selected_images', []) or []
    if not isinstance(selected_images, list):
        selected_images = []
    selected_images = [str(u).strip() for u in selected_images if str(u).strip()]
    user_image_count = len(selected_images)

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
        # 步骤1：搜索新闻（自动选择可用方式，含重试与降级）
        news_results = _search_news(topic, config, count)
        # 降级（沉淀 Coze「素材为空自动抓科技新闻」fallback）：首次无结果时自动补抓科技新闻
        if not news_results:
            news_results = _search_news('科技 人工智能 数码 新能源 芯片', config, count)
        if not news_results:
            return jsonify({'success': False, 'message': '未搜索到相关新闻，请换个关键词或配置搜索 API Key'})

        # 步骤1.4：抓取用户提供的参考网页，分析其风格与图片位置
        web_articles = []
        for u in (web_urls or [])[:5]:
            u = (u or '').strip()
            if u:
                art = _fetch_web_article(u)
                if art:
                    web_articles.append(art)
        # 步骤1.5：构建参考资料文本（参考图描述 + 文档文本 + 历史案例 + 参考网页）
        reference_text = _build_reference_text(references, use_history, session.get('user_id'), web_articles=web_articles)

        # 步骤2：DeepSeek 生成文章（结构化 blocks）
        style_profile = data.get('style_profile', None)
        skip_images = has_user_images or (image_mode == 'none') or bool(selected_images)
        article = with_retry(_deepseek_generate,
            topic, news_results, style_profile, deepseek_key,
            image_mode=image_mode, image_style=image_style,
            max_images=max_images, skip_images=skip_images,
            reference_text=reference_text, user_image_count=user_image_count,
            word_count=word_count, image_count=image_count,
            retries=3, what='DeepSeek生成'
        )
        # 若用户勾选了参考图作为正文图：把真实图片回填进 image 块（不调生图接口）
        if selected_images:
            article['blocks'] = _fill_user_images(article.get('blocks', []), selected_images)

        return jsonify({
            'success': True,
            'article': {
                'title': article.get('title', ''),
                'digest': article.get('digest', ''),
                'content': article.get('content', ''),
                'blocks': article.get('blocks', [])
            },
            'sources': news_results,
            'stats': {
                'news_count': len(news_results),
                'topic': topic,
                'search_method': search_method,
                'image_generated': (not skip_images),
                'user_images_used': len(selected_images),
                'reference_used': bool(reference_text),
                'reference_count': len(references) + (1 if use_history else 0) + len(web_articles),
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


def _build_auto_schedule_content(article, image_style, appid, appsecret):
    """把 AI 生成的 blocks 拼成微信安全写法 HTML，并把配图（Pollinations 生成）上传到微信永久素材库。

    返回 (html, cover_mid)。cover_mid 为第一张图的永久素材 media_id（用作草稿封面 thumb_media_id）；
    无图或未配置微信时 cover_mid=''（_do_publish 会回退默认封面）。
    """
    import wechat_scheduler as _ws
    blocks = article.get('blocks', []) or []
    html = '<section style="font-size:15px;color:#3f3f4f;line-height:1.8;">\n'
    cover_mid = ''
    has_wx = bool(appid) and bool(appsecret)
    for b in blocks:
        t = b.get('type')
        if t == 'h2':
            html += '<p style="font-size:17px;font-weight:bold;color:#2c3e50;margin:25px 0 12px 0;">%s</p>\n' % (b.get('text', '') or '').strip()
        elif t == 'blockquote':
            html += '<blockquote style="border-left:3px solid #534ab7;padding:8px 12px;margin:12px 0;background:#f8f9fa;color:#666;border-radius:0 6px 6px 0;">%s</blockquote>\n' % (b.get('text', '') or '').strip()
        elif t == 'image':
            if not has_wx:
                continue
            try:
                local = _pollinations_image(b.get('prompt', ''), image_style)
                url, mid = _ws._wx_upload_local(local, appid, appsecret)
                if not cover_mid:
                    cover_mid = mid
                html += '<p style="margin:12px 0;text-align:center;"><img src="%s" style="max-width:100%%;border-radius:8px;"></p>\n' % url
                try:
                    os.remove(local)
                except Exception:
                    pass
            except Exception:
                continue
        else:
            txt = (b.get('text', '') or '').strip()
            if txt:
                html += '<p style="margin-bottom:15px;">%s</p>\n' % txt
    html += '</section>'
    if not has_wx:
        # 未配置微信则无法上传配图，退回纯文字兜底 content
        html = article.get('content') or html
    return html, cover_mid


@app.route('/api/publish/schedule-auto', methods=['POST'])
def api_publish_schedule_auto():
    """⚡ 全自动：输入主题+图片数量+字数，自动搜新闻→AI写稿→配图→创建定时任务。

    到设定时间由调度器自动建草稿/发布（按所选 mode）。生成阶段即把配图上传到微信素材库并嵌入正文，
    实现真正「全自动」无需人工排版。
    """
    import wechat_scheduler as _ws
    data = request.get_json() or {}
    topic = (data.get('topic') or '').strip()
    word_count = int(data.get('word_count', 0) or 0)
    image_count = int(data.get('image_count', 0) or 0)
    image_style = data.get('image_style', 'tech')
    schedule_time = (data.get('schedule_time') or '').strip()
    mode = data.get('mode', 'publish')
    author = (data.get('author') or '').strip()
    if not topic:
        return jsonify({'success': False, 'message': '请输入文章主题'})
    if not schedule_time:
        return jsonify({'success': False, 'message': '请选择发布时间'})
    # datetime-local(YYYY-MM-DDTHH:MM) -> DB 格式(YYYY-MM-DD HH:MM:SS)
    schedule_time = schedule_time.replace('T', ' ')
    if len(schedule_time) == 16:
        schedule_time += ':00'

    config = _get_ai_config()
    deepseek_key = config.get('deepseek_api_key', '')
    if not deepseek_key:
        return jsonify({'success': False, 'message': 'DeepSeek API Key 未配置'})

    try:
        news = _search_news(topic, config, 5)
        if not news:
            news = _search_news('科技 人工智能 数码 新能源 芯片', config, 5)
        if not news:
            return jsonify({'success': False, 'message': '未搜索到相关新闻，请换个关键词'})

        article = with_retry(_deepseek_generate, topic, news, None, deepseek_key,
                             image_mode='auto', image_style=image_style,
                             max_images=max(1, image_count) if image_count > 0 else 4,
                             skip_images=False, word_count=word_count, image_count=image_count,
                             retries=3, what='DeepSeek生成')

        # 微信配置（用于把配图上传到微信素材库）
        row = get_db().execute("SELECT value FROM store_settings WHERE key='wechat_appid'").fetchone()
        appid = row['value'] if row else ''
        row = get_db().execute("SELECT value FROM store_settings WHERE key='wechat_appsecret'").fetchone()
        appsecret = row['value'] if row else ''

        content, cover_mid = _build_auto_schedule_content(article, image_style, appid, appsecret)
        pid = _ws.create_scheduled_post(
            article.get('title', ''), article.get('digest', ''), content, schedule_time,
            author=author, ptype='single', mode=mode, cover_media_id=cover_mid)
        return jsonify({
            'success': True,
            'id': pid,
            'article': {
                'title': article.get('title', ''),
                'digest': article.get('digest', ''),
                'content': article.get('content', ''),
                'blocks': article.get('blocks', [])
            },
            'message': '已生成并创建定时任务（ID %s）' % pid
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# ============================================================
# 管理后台路由：生成记录
# ============================================================



# ============================================================
# 微信发布增强：W2 外部素材抓取 / W3 移动端预览 / W1 定时批量 / W5 分析
# ============================================================

@app.route('/api/publish/fetch-materials', methods=['POST'])
def api_publish_fetch_materials():
    """W2：从外部抓取素材到网页。按关键词或 URL 拉取新闻/文章作为可选参考资料；
    无搜索 API Key 时自动用 RSS 兜底（_search_news 内部已含重试+降级）。"""
    data = request.get_json() or {}
    query = (data.get('query') or '').strip()
    urls = data.get('urls') or []
    if not query and not urls:
        return jsonify({'success': False, 'message': '请输入关键词或粘贴文章链接'})
    config = _get_ai_config()
    materials = []
    try:
        if query:
            for it in _search_news(query, config, int(data.get('count', 8) or 8)):
                materials.append({
                    'title': it.get('title', ''),
                    'url': it.get('url', ''),
                    'source': it.get('source', ''),
                    'description': (it.get('description') or '')[:200],
                    'kind': 'news'
                })
        for u in (urls or [])[:5]:
            u = (u or '').strip()
            if u.startswith('http'):
                art = _fetch_web_article(u)
                if art:
                    materials.append({
                        'title': art.get('title', ''),
                        'url': u,
                        'source': _extract_domain(u),
                        'description': (art.get('summary') or '')[:200],
                        'kind': 'article'
                    })
    except Exception as e:
        return jsonify({'success': False, 'message': '抓取失败: ' + str(e)})
    return jsonify({'success': True, 'materials': materials})


@app.route('/api/publish/preview-frame', methods=['POST'])
def api_publish_preview_frame():
    """W3：返回一篇「移动端自包含」的预览文档，供 iframe 内嵌模拟手机查看。
    正文 html 已是内联样式、微信安全写法；此处仅在外层包一个 375px 容器（预览框本身非发布内容）。"""
    data = request.get_json() or {}
    html = data.get('html', '')
    doc = ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
           '<meta name="viewport" content="width=device-width,initial-scale=1">'
           '<style>html,body{margin:0;padding:0;background:#fff;}'
           '.wx-phone{padding:14px;}</style></head>'
           '<body><div class="wx-phone">' + html + '</div></body></html>')
    return doc, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/api/publish/schedule-create', methods=['POST'])
def api_publish_schedule_create():
    """W1：创建定时发布任务。content 应为已含微信 CDN 图地址的最终 HTML。"""
    import wechat_scheduler
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    content = data.get('content', '')
    schedule_time = (data.get('schedule_time') or '').strip()
    if not title or not content:
        return jsonify({'success': False, 'message': '标题与内容不能为空'})
    if not schedule_time:
        return jsonify({'success': False, 'message': '请选择发布时间'})
    pid = wechat_scheduler.create_scheduled_post(
        title, data.get('digest', ''), content, schedule_time,
        author=data.get('author', ''), ptype=data.get('type', 'single'),
        mode=(data.get('mode') or 'publish'))
    return jsonify({'success': True, 'id': pid, 'message': '定时任务已创建'})


@app.route('/api/publish/schedule-list', methods=['GET'])
def api_publish_schedule_list():
    import wechat_scheduler
    return jsonify({'success': True, 'list': wechat_scheduler.list_scheduled()})


@app.route('/api/publish/schedule-cancel', methods=['POST'])
def api_publish_schedule_cancel():
    import wechat_scheduler
    data = request.get_json() or {}
    pid = data.get('id')
    if pid:
        wechat_scheduler.cancel_scheduled(pid)
    return jsonify({'success': True})


@app.route('/api/publish/schedule-resolve', methods=['POST'])
def api_publish_schedule_resolve():
    """W6：处理「发布失败但草稿已建好」的待决任务。

    action:
      'keep_draft' -> 草稿已在公众号草稿箱，仅标记为已转草稿（status='draft'）
      'clear'      -> 删除该条任务记录（清空此条内容）
    table: scheduled_posts（默认）或 publish_queue
    """
    import wechat_scheduler
    data = request.get_json() or {}
    pid = data.get('id')
    action = data.get('action')
    table = data.get('table', 'scheduled_posts')
    if not pid or action not in ('keep_draft', 'clear'):
        return jsonify({'success': False, 'message': '参数错误'})
    ok, msg = wechat_scheduler.resolve_scheduled(pid, action, table)
    return jsonify({'success': ok, 'message': msg})


@app.route('/api/publish/batch-enqueue', methods=['POST'])
def api_publish_batch_enqueue():
    """W1：批量发布入队。items: [{title,digest,content,author}]"""
    import wechat_scheduler
    data = request.get_json() or {}
    items = data.get('items') or []
    if not isinstance(items, list) or not items:
        return jsonify({'success': False, 'message': '请提交至少一个发布项'})
    ids = wechat_scheduler.enqueue_batch(items)
    return jsonify({'success': True, 'ids': ids, 'message': '已加入批量发布队列'})


@app.route('/api/publish/batch-list', methods=['GET'])
def api_publish_batch_list():
    import wechat_scheduler
    return jsonify({'success': True, 'list': wechat_scheduler.list_queue()})


@app.route('/api/publish/log-event', methods=['POST'])
def api_publish_log_event():
    """W5：前端在「复制到微信/手动发布」时上报一次日志。"""
    import wechat_scheduler
    data = request.get_json() or {}
    wechat_scheduler.log_publish(
        data.get('channel', 'manual'), data.get('title', ''),
        data.get('status', 'success'), data.get('detail', ''),
        data.get('type', 'article'))
    return jsonify({'success': True})


@app.route('/api/admin/publish-analytics', methods=['GET'])
def api_admin_publish_analytics():
    import wechat_scheduler
    return jsonify({'success': True, 'data': wechat_scheduler.get_analytics()})


@app.route('/admin/publish-analytics')
def admin_publish_analytics():
    return read_template('admin/publish_analytics.html')


# ==================== 秀米模板排版 API ====================
def _inline_css(soup, css):
    """把 <style> 里的 class/id/element 选择器 CSS 内联到对应元素。
    微信发布时会整体剥掉 <style> 块，故必须把样式落到元素 inline style 上才保留。
    跳过伪类/伪元素（:hover/::before 等微信不支持）。"""
    import re as _re
    if not css:
        return
    # 去掉 @media / @font-face / @keyframes 等块（微信不支持）
    css = _re.sub(r'@media[^{]*\{.*?\}\s*\}', '', css, flags=_re.DOTALL)
    css = _re.sub(r'@font-face\s*\{.*?\}', '', css, flags=_re.DOTALL)
    for raw in css.split('}'):
        raw = raw.strip()
        if '{' not in raw:
            continue
        sel, _, decls = raw.partition('{')
        sel = sel.strip()
        decls = decls.strip()
        if not sel or not decls or ':' not in decls:
            continue
        # 微信不支持的伪类/伪元素，跳过
        if any(t in sel for t in (':hover', ':before', ':after', ':focus',
                                   ':active', ':visited', ':first-child', ':nth', '::')):
            continue
        try:
            els = soup.select(sel)
        except Exception:
            continue
        for el in els:
            cur = (el.get('style') or '').rstrip().rstrip(';')
            merged = (cur + '; ' + decls).strip().strip(';')
            merged = _re.sub(r';\s*;+', ';', merged).strip('; ')
            if merged:
                el['style'] = merged


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
        # 微信会整体剥掉 <style> 块，故把 class 样式内联到元素上（不再保留 <style> 标签），
        # 否则模板的 class 排版在公众号里会全部丢失。
        _inline_css(soup, combined_css)

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

def _img_pair(val):
    """从图片值提取 {preview, wx} 两个URL。
    - string       -> preview=wx=该串（用户图/外部图）
    - {src,url}    -> preview=src(浏览器预览)，wx=url(微信发布)
    """
    if isinstance(val, str):
        return {'preview': val, 'wx': val}
    if isinstance(val, dict):
        preview = val.get('src') or val.get('url') or ''
        wx = val.get('url') or val.get('src') or ''
        return {'preview': preview, 'wx': wx}
    s = str(val) if val else ''
    return {'preview': s, 'wx': s}


# ============================================================
# 内置排版模板 —— 六套差异化视觉风格
# 重要约束：微信公众号草稿编辑器会完整剥掉 <style> 与 CSS class，
# 仅保留元素的「行内 style」。此外 paste handler 对普通段落的 style="color"
# 较苛刻，故正文颜色统一用 <font color> 兜底；标题/引用/卡片用 <section> 行内样式。
# 每套模板在「配色 / 标题装饰 / 引用样式 / 是否卡片化」上均不同，杜绝雷同。
# ============================================================

def _h2_section(val, cfg):
    """小标题块。deco: bar(左侧色条) / underline(下划线) / center(居中+装饰线) / pill(色带) / plain"""
    deco = cfg.get('deco', 'bar')
    color = cfg.get('color', '#333')
    accent = cfg.get('accent', color)
    size = cfg.get('size', '18px')
    if deco == 'bar':
        return (f'<section style="border-left:4px solid {accent};padding:5px 0 5px 12px;'
                f'margin:26px 0 12px;font-size:{size};font-weight:bold;line-height:1.6;color:{color};">'
                f'{val}</section>')
    if deco == 'underline':
        return (f'<section style="margin:26px 0 6px;font-size:{size};font-weight:bold;line-height:1.7;'
                f'color:{color};border-bottom:2px solid {accent};padding-bottom:8px;">{val}</section>')
    if deco == 'center':
        return (f'<section style="text-align:center;margin:28px 0 4px;font-size:{size};font-weight:bold;'
                f'color:{color};line-height:1.7;">{val}</section>'
                f'<section style="text-align:center;margin:0 0 14px;font-size:14px;letter-spacing:6px;'
                f'color:{accent};">— · —</section>')
    if deco == 'pill':
        return (f'<section style="background-color:{accent};color:#ffffff;text-align:center;'
                f'margin:26px 0 14px;padding:9px 16px;border-radius:22px;font-size:15px;font-weight:bold;'
                f'letter-spacing:1px;line-height:1.6;">{val}</section>')
    return (f'<section style="margin:26px 0 12px;font-size:{size};font-weight:bold;line-height:1.6;'
            f'color:{color};">{val}</section>')


def _quote_section(val, cfg):
    """引用块。deco: tint(底色+左边条) / plain(居中斜体带引号)"""
    deco = cfg.get('deco', 'tint')
    color = cfg.get('color', '#666')
    bg = cfg.get('bg', '#f5f5f5')
    accent = cfg.get('accent', color)
    italic = 'italic' if cfg.get('italic') else 'normal'
    if deco == 'plain':
        return (f'<section style="text-align:center;margin:18px 0;font-style:{italic};'
                f'color:{color};line-height:1.9;font-size:15px;">“ {val} ”</section>')
    return (f'<section style="background-color:{bg};border-left:4px solid {accent};'
            f'padding:14px 18px;border-radius:10px;margin:18px 0;font-style:{italic};'
            f'color:{color};line-height:1.9;font-size:15px;">{val}</section>')


def _body_section(val, cfg, extra=''):
    color = cfg.get('color', '#333')
    size = cfg.get('size', '15px')
    lh = cfg.get('lh', '1.85')
    margin = cfg.get('margin', '0 0 14px')
    style = f'{extra}font-size:{size};line-height:{lh};margin:{margin};'
    return f'<section style="{style}"><font color="{color}">{val}</font></section>'


def _img_section(val, img_style, wrap=''):
    pair = _img_pair(val)
    if pair['preview'] or pair['wx']:
        inner = f'<img src="{pair["preview"]}" data-wx="{pair["wx"]}" style="{img_style}" alt="">'
        if wrap:
            return f'<section style="{wrap}text-align:center;">{inner}</section>'
        return f'<section style="text-align:center;margin:16px 0;">{inner}</section>'
    return ''


def _render_body(ordered_sections, st):
    """按原始顺序渲染正文块（图片保留在正文中的分布位置）。
    st 字段：
      body         -> {color,size,lh,margin} 正文
      h2           -> {deco,color,accent,size} 小标题
      quote        -> {deco,color,bg,accent,italic} 引用
      img          -> img 行内 style 字符串
      body_section -> 可选，给每段正文外加的 section 样式（如卡片背景）
      img_wrap     -> 可选，给图片外加的 section 样式（如卡片背景）
    """
    body_cfg = st.get('body', {})
    h2_cfg = st.get('h2', {})
    quote_cfg = st.get('quote', {})
    img_style = st.get('img', 'max-width:100%;border-radius:10px;display:block;margin:0 auto;')
    body_extra = st.get('body_section', '')
    img_wrap = st.get('img_wrap', '')
    out = []
    for s in ordered_sections:
        t = s.get('type', 'p')
        val = s.get('value', '')
        if t == 'h2' and val:
            out.append(_h2_section(val, h2_cfg))
        elif t == 'blockquote' and val:
            out.append(_quote_section(val, quote_cfg))
        elif t == 'img':
            out.append(_img_section(val, img_style, img_wrap))
        elif val:
            out.append(_body_section(val, body_cfg, body_extra))
    return '\n'.join(out)


# ---------- 模板1：简约清新（薄荷绿 / 留白 / 白色底） ----------
def template_clean_minimal(title, intro, ordered_sections):
    st = {
        'body': {'color': '#374151', 'size': '15px', 'lh': '1.9'},
        'h2': {'deco': 'bar', 'color': '#0d9488', 'accent': '#14b8a6', 'size': '18px'},
        'quote': {'deco': 'tint', 'color': '#047857', 'bg': '#ecfdf5', 'accent': '#14b8a6', 'italic': True},
        'img': 'max-width:100%;border-radius:12px;display:block;margin:0 auto;box-shadow:0 6px 16px rgba(20,184,166,0.12);',
    }
    return f'<section style="background-color:#ffffff;padding:6px;">\n{_render_body(ordered_sections, st)}\n</section>'


# ---------- 模板2：杂志风（编辑红 / 暖纸底 / 下划线标题） ----------
def template_magazine(title, intro, ordered_sections):
    st = {
        'body': {'color': '#3a3a3a', 'size': '15.5px', 'lh': '1.95'},
        'h2': {'deco': 'underline', 'color': '#1a1a1a', 'accent': '#dc2626', 'size': '20px'},
        'quote': {'deco': 'plain', 'color': '#9a3412', 'italic': True},
        'img': 'max-width:100%;border-radius:2px;display:block;margin:0 auto;',
    }
    return f'<section style="background-color:#fdfaf6;padding:6px;">\n{_render_body(ordered_sections, st)}\n</section>'


# ---------- 模板3：文艺风（陶土橙 / 米色底 / 居中标题） ----------
def template_literary(title, intro, ordered_sections):
    st = {
        'body': {'color': '#5b4a3a', 'size': '15.5px', 'lh': '2.0'},
        'h2': {'deco': 'center', 'color': '#92400e', 'accent': '#d97706', 'size': '18px'},
        'quote': {'deco': 'plain', 'color': '#a16207', 'italic': True},
        'img': 'max-width:100%;border-radius:14px;display:block;margin:0 auto;',
    }
    return f'<section style="background-color:#fbf3e7;padding:6px;">\n{_render_body(ordered_sections, st)}\n</section>'


# ---------- 模板4：商务风（商务蓝 / 白底 / 蓝色左条标题） ----------
def template_business(title, intro, ordered_sections):
    st = {
        'body': {'color': '#374151', 'size': '15px', 'lh': '1.9'},
        'h2': {'deco': 'bar', 'color': '#1e3a5f', 'accent': '#2563eb', 'size': '18px'},
        'quote': {'deco': 'tint', 'color': '#1e40af', 'bg': '#eff6ff', 'accent': '#2563eb', 'italic': False},
        'img': 'max-width:100%;border-radius:8px;display:block;margin:0 auto;',
    }
    return f'<section style="background-color:#ffffff;padding:6px;">\n{_render_body(ordered_sections, st)}\n</section>'


# ---------- 模板5：卡片风（靛蓝 / 浅灰蓝底 / 段落独立卡片） ----------
def template_card(title, intro, ordered_sections):
    st = {
        'body': {'color': '#374151', 'size': '15px', 'lh': '1.85'},
        'h2': {'deco': 'bar', 'color': '#4338ca', 'accent': '#6366f1', 'size': '18px'},
        'quote': {'deco': 'tint', 'color': '#4338ca', 'bg': '#eef2ff', 'accent': '#6366f1', 'italic': True},
        'img': 'max-width:100%;border-radius:10px;display:block;margin:0 auto;',
        'body_section': 'background-color:#ffffff;border:1px solid #e5e7eb;border-radius:12px;padding:14px 16px;',
        'img_wrap': 'background-color:#ffffff;border:1px solid #e5e7eb;border-radius:12px;padding:8px;',
    }
    return f'<section style="background-color:#f5f7fb;padding:16px;">\n{_render_body(ordered_sections, st)}\n</section>'


# ---------- 模板6：深色科技风（青蓝霓虹 / 近黑底 / 每块独立深色卡片） ----------
# 关键：微信会剥掉最外层 section 背景，所以每块自带深色背景，保证粘贴后仍是深色风格。
def template_dark(title, intro, ordered_sections):
    st = {
        'body': {'color': '#cbd5e1', 'size': '15px', 'lh': '1.9'},
        'h2': {'deco': 'bar', 'color': '#38bdf8', 'accent': '#38bdf8', 'size': '18px'},
        'quote': {'deco': 'tint', 'color': '#94a3b8', 'bg': '#1e293b', 'accent': '#38bdf8', 'italic': True},
        'img': 'max-width:100%;border-radius:10px;display:block;margin:0 auto;border:1px solid #334155;',
        'body_section': 'background-color:#111827;border:1px solid #1f2937;border-radius:12px;padding:14px 16px;',
        'img_wrap': 'background-color:#111827;border:1px solid #1f2937;border-radius:12px;padding:8px;',
    }
    return f'<section style="background-color:#0f172a;padding:20px;border-radius:14px;">\n{_render_body(ordered_sections, st)}\n</section>'


# ---------- 模板7：党政风（党建红 / 金色 / 和平鸽 + 五角星装饰） ----------
# 微信会剥掉渐变(gradient)与伪元素(::before)，且禁止 emoji(草稿箱乱码)，
# 故装饰一律用纯色实心底 + 内联 SVG（五角星/和平鸽），白字用 <font color>。
def _party_star_svg(size=26):
    # 规范五角星顶点（外接圆 r=10，中心 12,12，交替外/内半径）
    pts = "12,2 14.35,15.24 21.51,15.09 15.80,10.76 17.88,3.91 12,8 6.12,3.91 8.20,10.76 2.49,15.09 9.65,15.24"
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
            f'<polygon points="{pts}" fill="#f6c453"/></svg>')


def _party_dove_svg(size=30):
    # 简化和平鸽剪影（金色），朝右飞翔姿态
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
            '<path d="M2 13c1.5-2 4-3 6.5-2.5 1.2-2.3 3.8-3.8 6.8-3.5.8-1.6 2.4-2.8 4.4-3 '
            '.4-1.4 1.5-2.5 3-2.8-1 .8-1.6 1.9-1.7 3.1-.9.2-1.7.7-2.3 1.4-1.7-1-3.8-1.4-6-1 '
            '-2.2.4-4 1.6-5.1 3.4-1.4-.4-2.9-.4-4.3.1-1.4.5-2.6 1.4-3.5 2.6 1-.2 2-.2 3 0z" fill="#f6c453"/></svg>')


def template_party(title, intro, ordered_sections):
    st = {
        'body': {'color': '#3a2e2e', 'size': '15.5px', 'lh': '1.95'},
        'h2': {'deco': 'bar', 'color': '#9e1b1b', 'accent': '#c8102e', 'size': '18px'},
        'quote': {'deco': 'tint', 'color': '#9e1b1b', 'bg': '#fbeaed', 'accent': '#c8102e', 'italic': False},
        'img': 'max-width:100%;border-radius:8px;display:block;margin:0 auto;border:3px solid #c8102e;padding:4px;background-color:#ffffff;',
    }
    # 顶部红色横幅：和平鸽 + 金色五角星 + 标题（微信安全的纯色 + 内联 SVG）
    banner = (
        '<section style="background-color:#c8102e;padding:20px 16px;margin:0 0 8px;text-align:center;border-radius:6px;">'
        '<div style="display:flex;justify-content:center;align-items:center;gap:14px;margin-bottom:10px;">'
        f'{_party_dove_svg(30)}{_party_star_svg(26)}{_party_dove_svg(30)}'
        '</div>'
        '<div style="color:#f6c453;font-size:12px;letter-spacing:3px;font-weight:bold;line-height:1.6;">党 建 学 习 · 政 策 解 读</div>'
        '</section>'
    )
    return f'{banner}\n<section style="background-color:#ffffff;padding:6px;">\n{_render_body(ordered_sections, st)}\n</section>'


# ---------- 模板8：数字一大·初心之旅（淡黄底 / 红字 / 石库门 + 红船 + 日出东方） ----------
# 主题元素取自中共一大纪念馆：石库门（青红砖拱形门楣，一大会址）、南湖红船（红船精神）、
# "日出东方——从石库门到天安门"、1921·兴业路76号、金色五角星。
# 微信安全：纯色 + 行内样式 + 内联 SVG，无渐变/伪元素/emoji；每块自带淡黄底防止外层背景被剥。
def _yida_shikumen_svg(width=150, height=96):
    # 简化石库门：红砖门框 + 半圆拱形门楣（含放射状楣饰）+ 金色门环双扇黑门
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 150 96" xmlns="http://www.w3.org/2000/svg">'
            # 砖墙底
            '<rect x="0" y="10" width="150" height="86" fill="#b5533c"/>'
            # 砖缝（横线）
            '<rect x="0" y="26" width="150" height="2" fill="#9e3f2c"/>'
            '<rect x="0" y="44" width="150" height="2" fill="#9e3f2c"/>'
            '<rect x="0" y="62" width="150" height="2" fill="#9e3f2c"/>'
            '<rect x="0" y="80" width="150" height="2" fill="#9e3f2c"/>'
            # 门楣拱形（外圈石灰色，内圈金色放射楣饰）
            '<path d="M35 52 A40 40 0 0 1 115 52 L115 60 L35 60 Z" fill="#e8dcc8"/>'
            '<path d="M42 54 A33 33 0 0 1 108 54 L108 60 L42 60 Z" fill="#c8102e"/>'
            '<path d="M75 22 L78 34 L72 34 Z" fill="#f6c453"/>'
            '<path d="M57 27 L63 38 L58 41 Z" fill="#f6c453"/>'
            '<path d="M93 27 L92 41 L87 38 Z" fill="#f6c453"/>'
            # 门柱
            '<rect x="35" y="56" width="10" height="40" fill="#e8dcc8"/>'
            '<rect x="105" y="56" width="10" height="40" fill="#e8dcc8"/>'
            # 双扇黑门 + 金色门环
            '<rect x="47" y="58" width="27" height="38" fill="#2b2b2b"/>'
            '<rect x="76" y="58" width="27" height="38" fill="#3a3a3a"/>'
            '<circle cx="66" cy="76" r="3.5" fill="#f6c453"/>'
            '<circle cx="84" cy="76" r="3.5" fill="#f6c453"/>'
            '</svg>')


def _yida_boat_svg(width=140, height=64):
    # 简化南湖红船：单层舱体 + 弧形船底 + 水波纹
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 140 64" xmlns="http://www.w3.org/2000/svg">'
            # 舱顶
            '<rect x="42" y="8" width="56" height="6" rx="3" fill="#9e1b1b"/>'
            # 舱体（含金色格窗）
            '<rect x="46" y="14" width="48" height="18" fill="#c8102e"/>'
            '<rect x="51" y="18" width="8" height="9" fill="#f6c453"/>'
            '<rect x="66" y="18" width="8" height="9" fill="#f6c453"/>'
            '<rect x="81" y="18" width="8" height="9" fill="#f6c453"/>'
            # 船身（弧形船底）
            '<path d="M18 34 L122 34 L106 48 L34 48 Z" fill="#8c1515"/>'
            # 水波（三段弧线）
            '<path d="M10 56 Q22 50 34 56 Q46 62 58 56 Q70 50 82 56 Q94 62 106 56 Q118 50 130 56" '
            'stroke="#d98e8e" stroke-width="3" fill="none" stroke-linecap="round"/>'
            '</svg>')


def _yida_sun_svg(width=120, height=44):
    # 日出东方：金色半日 + 放射光芒
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 120 44" xmlns="http://www.w3.org/2000/svg">'
            '<path d="M40 42 A20 20 0 0 1 80 42 Z" fill="#f6c453"/>'
            '<rect x="57" y="4" width="6" height="12" rx="3" fill="#f6c453"/>'
            '<rect x="30" y="12" width="6" height="12" rx="3" fill="#f6c453" transform="rotate(-40 33 18)"/>'
            '<rect x="84" y="12" width="6" height="12" rx="3" fill="#f6c453" transform="rotate(40 87 18)"/>'
            '<rect x="12" y="30" width="6" height="12" rx="3" fill="#f6c453" transform="rotate(-72 15 36)"/>'
            '<rect x="102" y="30" width="6" height="12" rx="3" fill="#f6c453" transform="rotate(72 105 36)"/>'
            '</svg>')


def template_yida(title, intro, ordered_sections):
    st = {
        # 用户要求：字体红色（正文用可读性较好的深红）
        'body': {'color': '#a11d1d', 'size': '15.5px', 'lh': '1.95'},
        # 红色色带小标题（与党政风的左条区分）
        'h2': {'deco': 'pill', 'color': '#ffffff', 'accent': '#c8102e', 'size': '16px'},
        'quote': {'deco': 'tint', 'color': '#8c1515', 'bg': '#fdeecb', 'accent': '#c8102e', 'italic': False},
        # 用户要求：图片方框红色
        'img': 'max-width:100%;border-radius:4px;display:block;margin:0 auto;border:3px solid #c8102e;padding:4px;background-color:#fff9ec;',
        # 每块自带淡黄底，粘贴到微信后淡黄背景不丢失
        'body_section': 'background-color:#fdf6e0;border-radius:8px;padding:12px 14px;',
        'img_wrap': 'background-color:#fdf6e0;border-radius:8px;padding:10px;',
    }
    # 头部：横幅图片（红色底+金星+金色大字"数字一大·初心之旅"+副标题）
    # 用图片而非纯文本 div，避免微信粘贴时样式被剥导致标题不显示
    banner = (
        '<section style="margin:0 0 10px;border-radius:6px;overflow:hidden;">'
        '<img src="/static/uploads/yida_banner.png" alt="数字一大·初心之旅"'
        ' style="width:100%;display:block;border-radius:6px;" />'
        '</section>'
    )
    # 副横幅：石库门场景（淡黄底卡片，日出东方 + 石库门）
    shikumen = (
        '<section style="background-color:#fdf6e0;border:2px solid #c8102e;border-radius:8px;'
        'padding:16px 12px 14px;margin:0 0 10px;text-align:center;">'
        f'<div>{_yida_sun_svg(120, 44)}</div>'
        f'<div style="margin-top:2px;">{_yida_shikumen_svg(150, 96)}</div>'
        '<div style="color:#8c1515;font-size:13px;letter-spacing:2px;margin-top:10px;font-weight:bold;line-height:1.7;">日出东方 · 从石库门到天安门</div>'
        '</section>'
    )
    # 尾部：南湖红船（淡黄底卡片）
    boat = (
        '<section style="background-color:#fdf6e0;border:2px solid #c8102e;border-radius:8px;'
        'padding:16px 12px 12px;margin:10px 0 0;text-align:center;">'
        f'<div>{_yida_boat_svg(140, 64)}</div>'
        '<div style="color:#8c1515;font-size:13px;letter-spacing:2px;margin-top:8px;font-weight:bold;line-height:1.7;">南湖红船 · 初心不改 砥砺前行</div>'
        '<div style="color:#b5533c;font-size:11px;letter-spacing:1px;margin-top:4px;line-height:1.6;">星火初燃 · 伟大的开端</div>'
        '</section>'
    )
    body = f'<section style="background-color:#fdf6e0;padding:10px;border-radius:8px;">\n{_render_body(ordered_sections, st)}\n</section>'
    return f'{banner}\n{shikumen}\n{body}\n{boat}'


# ============================================================
# 内置固定排版模板：数据驱动定义（用于初始化 / 种子到 builtin_templates 表）
# 管理员可在后台「内置模板管理」对这些模板增删改查；渲染统一走 render_builtin_from_record
# ============================================================

def _party_banner_html():
    """党建风顶部红色横幅（和平鸽 + 金色五角星 + 标题）。"""
    return (
        '<section style="background-color:#c8102e;padding:20px 16px;margin:0 0 8px;text-align:center;border-radius:6px;">'
        '<div style="display:flex;justify-content:center;align-items:center;gap:14px;margin-bottom:10px;">'
        f'{_party_dove_svg(30)}{_party_star_svg(26)}{_party_dove_svg(30)}'
        '</div>'
        '<div style="color:#f6c453;font-size:12px;letter-spacing:3px;font-weight:bold;line-height:1.6;">党 建 学 习 · 政 策 解 读</div>'
        '</section>'
    )


def _yida_header_html():
    """数字一大：头图横幅 + 石库门场景（淡黄底卡片）。"""
    banner = (
        '<section style="margin:0 0 10px;border-radius:6px;overflow:hidden;">'
        '<img src="/static/uploads/yida_banner.png" alt="数字一大·初心之旅"'
        ' style="width:100%;display:block;border-radius:6px;" />'
        '</section>'
    )
    shikumen = (
        '<section style="background-color:#fdf6e0;border:2px solid #c8102e;border-radius:8px;'
        'padding:16px 12px 14px;margin:0 0 10px;text-align:center;">'
        f'<div>{_yida_sun_svg(120, 44)}</div>'
        f'<div style="margin-top:2px;">{_yida_shikumen_svg(150, 96)}</div>'
        '<div style="color:#8c1515;font-size:13px;letter-spacing:2px;margin-top:10px;font-weight:bold;line-height:1.7;">日出东方 · 从石库门到天安门</div>'
        '</section>'
    )
    return banner + '\n' + shikumen


def _yida_footer_html():
    """数字一大：尾部南湖红船（淡黄底卡片）。"""
    return (
        '<section style="background-color:#fdf6e0;border:2px solid #c8102e;border-radius:8px;'
        'padding:16px 12px 12px;margin:10px 0 0;text-align:center;">'
        f'<div>{_yida_boat_svg(140, 64)}</div>'
        '<div style="color:#8c1515;font-size:13px;letter-spacing:2px;margin-top:8px;font-weight:bold;line-height:1.7;">南湖红船 · 初心不改 砥砺前行</div>'
        '<div style="color:#b5533c;font-size:11px;letter-spacing:1px;margin-top:4px;line-height:1.6;">星火初燃 · 伟大的开端</div>'
        '</section>'
    )


BUILTIN_TEMPLATE_SEED = [
    {
        'name': '简约清新', 'category': '通用',
        'desc': '薄荷绿点缀 · 大量留白，清爽通透，适合科技与生活方式',
        'accent': '#14b8a6', 'bg': '#e8f4f8',
        'st': {'body': {'color': '#374151', 'size': '15px', 'lh': '1.9'},
               'h2': {'deco': 'bar', 'color': '#0d9488', 'accent': '#14b8a6', 'size': '18px'},
               'quote': {'deco': 'tint', 'color': '#047857', 'bg': '#ecfdf5', 'accent': '#14b8a6', 'italic': True},
               'img': 'max-width:100%;border-radius:12px;display:block;margin:0 auto;box-shadow:0 6px 16px rgba(20,184,166,0.12);'},
        'body': {'bg': '#ffffff', 'padding': '6px', 'extra': ''},
        'header_html': '', 'footer_html': '',
    },
    {
        'name': '杂志风', 'category': '长文',
        'desc': '编辑红下划线标题 · 暖纸底，经典杂志感，适合深度长文',
        'accent': '#dc2626', 'bg': '#fdfaf6',
        'st': {'body': {'color': '#3a3a3a', 'size': '15.5px', 'lh': '1.95'},
               'h2': {'deco': 'underline', 'color': '#1a1a1a', 'accent': '#dc2626', 'size': '20px'},
               'quote': {'deco': 'plain', 'color': '#9a3412', 'italic': True},
               'img': 'max-width:100%;border-radius:2px;display:block;margin:0 auto;'},
        'body': {'bg': '#fdfaf6', 'padding': '6px', 'extra': ''},
        'header_html': '', 'footer_html': '',
    },
    {
        'name': '文艺风', 'category': '生活',
        'desc': '陶土橙居中标题 · 米色底，温润文艺，适合随笔与情感',
        'accent': '#d97706', 'bg': '#fbf3e7',
        'st': {'body': {'color': '#5b4a3a', 'size': '15.5px', 'lh': '2.0'},
               'h2': {'deco': 'center', 'color': '#92400e', 'accent': '#d97706', 'size': '18px'},
               'quote': {'deco': 'plain', 'color': '#a16207', 'italic': True},
               'img': 'max-width:100%;border-radius:14px;display:block;margin:0 auto;'},
        'body': {'bg': '#fbf3e7', 'padding': '6px', 'extra': ''},
        'header_html': '', 'footer_html': '',
    },
    {
        'name': '商务风', 'category': '企业',
        'desc': '商务蓝左条标题 · 白底，专业克制，适合行业分析',
        'accent': '#2563eb', 'bg': '#ffffff',
        'st': {'body': {'color': '#374151', 'size': '15px', 'lh': '1.9'},
               'h2': {'deco': 'bar', 'color': '#1e3a5f', 'accent': '#2563eb', 'size': '18px'},
               'quote': {'deco': 'tint', 'color': '#1e40af', 'bg': '#eff6ff', 'accent': '#2563eb', 'italic': False},
               'img': 'max-width:100%;border-radius:8px;display:block;margin:0 auto;'},
        'body': {'bg': '#ffffff', 'padding': '6px', 'extra': ''},
        'header_html': '', 'footer_html': '',
    },
    {
        'name': '卡片风', 'category': '现代',
        'desc': '靛蓝描边 · 每段独立卡片，现代扁平，适合清单与资讯',
        'accent': '#6366f1', 'bg': '#f5f7fb',
        'st': {'body': {'color': '#374151', 'size': '15px', 'lh': '1.85'},
               'h2': {'deco': 'bar', 'color': '#4338ca', 'accent': '#6366f1', 'size': '18px'},
               'quote': {'deco': 'tint', 'color': '#4338ca', 'bg': '#eef2ff', 'accent': '#6366f1', 'italic': True},
               'img': 'max-width:100%;border-radius:10px;display:block;margin:0 auto;',
               'body_section': 'background-color:#ffffff;border:1px solid #e5e7eb;border-radius:12px;padding:14px 16px;',
               'img_wrap': 'background-color:#ffffff;border:1px solid #e5e7eb;border-radius:12px;padding:8px;'},
        'body': {'bg': '#f5f7fb', 'padding': '16px', 'extra': ''},
        'header_html': '', 'footer_html': '',
    },
    {
        'name': '深色科技', 'category': '科技',
        'desc': '青蓝霓虹 · 近黑底深色卡片，适合科技类与夜间阅读',
        'accent': '#38bdf8', 'bg': '#0f172a',
        'st': {'body': {'color': '#cbd5e1', 'size': '15px', 'lh': '1.9'},
               'h2': {'deco': 'bar', 'color': '#38bdf8', 'accent': '#38bdf8', 'size': '18px'},
               'quote': {'deco': 'tint', 'color': '#94a3b8', 'bg': '#1e293b', 'accent': '#38bdf8', 'italic': True},
               'img': 'max-width:100%;border-radius:10px;display:block;margin:0 auto;border:1px solid #334155;',
               'body_section': 'background-color:#111827;border:1px solid #1f2937;border-radius:12px;padding:14px 16px;',
               'img_wrap': 'background-color:#111827;border:1px solid #1f2937;border-radius:12px;padding:8px;'},
        'body': {'bg': '#0f172a', 'padding': '20px', 'extra': 'border-radius:14px;'},
        'header_html': '', 'footer_html': '',
    },
    {
        'name': '党政风', 'category': '党政',
        'desc': '党建红 + 金色五角星与和平鸽装饰，庄重端正，适合党建宣传与政策解读',
        'accent': '#c8102e', 'bg': '#c8102e',
        'st': {'body': {'color': '#3a2e2e', 'size': '15.5px', 'lh': '1.95'},
               'h2': {'deco': 'bar', 'color': '#9e1b1b', 'accent': '#c8102e', 'size': '18px'},
               'quote': {'deco': 'tint', 'color': '#9e1b1b', 'bg': '#fbeaed', 'accent': '#c8102e', 'italic': False},
               'img': 'max-width:100%;border-radius:8px;display:block;margin:0 auto;border:3px solid #c8102e;padding:4px;background-color:#ffffff;'},
        'body': {'bg': '#ffffff', 'padding': '6px', 'extra': ''},
        'header_html': _party_banner_html(), 'footer_html': '',
    },
    {
        'name': '数字一大·初心之旅', 'category': '党政',
        'desc': '淡黄底红字 · 石库门/南湖红船/日出东方元素，适合党建题材与红色主题宣传',
        'accent': '#c8102e', 'bg': '#fdf6e0',
        'st': {'body': {'color': '#a11d1d', 'size': '15.5px', 'lh': '1.95'},
               'h2': {'deco': 'pill', 'color': '#ffffff', 'accent': '#c8102e', 'size': '16px'},
               'quote': {'deco': 'tint', 'color': '#8c1515', 'bg': '#fdeecb', 'accent': '#c8102e', 'italic': False},
               'img': 'max-width:100%;border-radius:4px;display:block;margin:0 auto;border:3px solid #c8102e;padding:4px;background-color:#fff9ec;',
               'body_section': 'background-color:#fdf6e0;border-radius:8px;padding:12px 14px;',
               'img_wrap': 'background-color:#fdf6e0;border-radius:8px;padding:10px;'},
        'body': {'bg': '#fdf6e0', 'padding': '10px', 'extra': 'border-radius:8px;'},
        'header_html': _yida_header_html(), 'footer_html': _yida_footer_html(),
    },
]


def render_builtin_from_record(rec, ordered_sections):
    """根据 builtin_templates 表记录渲染排版 HTML（通用渲染器）。"""
    import json
    if not isinstance(rec, dict):
        rec = dict(rec)
    st = json.loads(rec['style_json'] or '{}')
    body = json.loads(rec['body_json'] or '{}')
    header_html = rec.get('header_html') or ''
    footer_html = rec.get('footer_html') or ''
    bg = body.get('bg', '#ffffff')
    padding = body.get('padding', '6px')
    extra = body.get('extra', '')
    body_style = f"background-color:{bg};padding:{padding};" + (extra if extra else '')
    inner = _render_body(ordered_sections, st)
    body_section = f'<section style="{body_style}">\n{inner}\n</section>'
    return f'{header_html}\n{body_section}\n{footer_html}'.strip()


def seed_builtin_templates(c):
    """首次启动把内置模板写入 builtin_templates 表（仅当表为空时）。"""
    import json
    c.execute("SELECT COUNT(*) FROM builtin_templates")
    if c.fetchone()[0] > 0:
        return
    for d in BUILTIN_TEMPLATE_SEED:
        c.execute(
            """INSERT INTO builtin_templates
               (name, category, description, accent, bg, style_json, body_json, header_html, footer_html, is_active)
               VALUES (?,?,?,?,?,?,?,?,?,1)""",
            (d['name'], d['category'], d['desc'], d['accent'], d['bg'],
             json.dumps(d['st'], ensure_ascii=False),
             json.dumps(d['body'], ensure_ascii=False),
             d.get('header_html', ''), d.get('footer_html', ''))
        )


@app.route('/api/publish/built-in-templates', methods=['GET'])
def get_builtin_templates():
    """获取内置排版模板列表（仅返回启用中的）"""
    db = get_db()
    rows = db.execute(
        "SELECT id, name, category, description, accent, bg, is_active "
        "FROM builtin_templates WHERE is_active = 1 ORDER BY id"
    ).fetchall()
    templates = [{
        'id': r['id'], 'name': r['name'], 'category': r['category'],
        'desc': r['description'], 'accent': r['accent'] or '#888', 'bg': r['bg'] or '#f0f0f0'
    } for r in rows]
    return jsonify({'success': True, 'templates': templates})


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
    
    try:
        template_id = int(template_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '模板ID 无效'})

    db = get_db()
    rec = db.execute("SELECT * FROM builtin_templates WHERE id = ?", (template_id,)).fetchone()
    if not rec:
        return jsonify({'success': False, 'message': f'模板ID {template_id} 不存在'})
    template_name = rec['name']

    # 按原始顺序构建内容块（保留图片在正文中的分布位置）
    ordered_sections = []
    for s in sections:
        t = s.get('type', 'p')
        val = s.get('text', '')
        if t == 'img':
            # 保留完整图片值（string 或 {src,url}），交给 _img_pair 处理
            ordered_sections.append({'type': 'img', 'value': val})
        else:
            val = (val or '').strip() if isinstance(val, str) else val
            if val:
                ordered_sections.append({'type': t, 'value': val})

    try:
        html = render_builtin_from_record(rec, ordered_sections)
        return jsonify({
            'success': True,
            'html': html,
            'template_name': template_name,
            'template_id': template_id,
            'stats': {
                'subtitles': sum(1 for s in ordered_sections if s['type'] == 'h2'),
                'bodies': sum(1 for s in ordered_sections if s['type'] == 'p'),
                'quotes': sum(1 for s in ordered_sections if s['type'] == 'blockquote'),
                'images': sum(1 for s in ordered_sections if s['type'] == 'img')
            }
        })
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'message': f'模板生成失败: {str(e)}', 'traceback': traceback.format_exc()})


# ============================================================
# 管理员：内置固定排版模板 增删改查
# ============================================================

def _norm_json(v, default='{}'):
    """把风格/正文区配置统一成 JSON 字符串（接受 dict 或已序列化字符串）。"""
    import json
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if v is None or v == '':
        return default
    return v


@app.route('/api/admin/builtin-templates', methods=['GET'])
@admin_required
def admin_list_builtin_templates():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, category, description, accent, bg, is_active, created_at, updated_at "
        "FROM builtin_templates ORDER BY id"
    ).fetchall()
    items = [{
        'id': r['id'], 'name': r['name'], 'category': r['category'],
        'description': r['description'], 'accent': r['accent'] or '#888',
        'bg': r['bg'] or '#f0f0f0', 'is_active': r['is_active'],
        'created_at': r['created_at'], 'updated_at': r['updated_at']
    } for r in rows]
    return jsonify({'success': True, 'templates': items})


@app.route('/api/admin/builtin-templates/<int:tid>', methods=['GET'])
@admin_required
def admin_get_builtin_template(tid):
    db = get_db()
    r = db.execute("SELECT * FROM builtin_templates WHERE id = ?", (tid,)).fetchone()
    if not r:
        return jsonify({'success': False, 'message': '模板不存在'})
    return jsonify({
        'success': True,
        'template': {
            'id': r['id'], 'name': r['name'], 'category': r['category'],
            'description': r['description'], 'accent': r['accent'], 'bg': r['bg'],
            'style_json': r['style_json'], 'body_json': r['body_json'],
            'header_html': r['header_html'], 'footer_html': r['footer_html'],
            'is_active': r['is_active']
        }
    })


@app.route('/api/admin/builtin-templates', methods=['POST'])
@admin_required
def admin_create_builtin_template():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': '请输入模板名称'})
    db = get_db()
    cur = db.execute(
        """INSERT INTO builtin_templates
           (name, category, description, accent, bg, style_json, body_json, header_html, footer_html, is_active)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (name, data.get('category', '通用'), data.get('description', ''),
         data.get('accent', '#888888'), data.get('bg', '#f0f0f0'),
         _norm_json(data.get('style_json')), _norm_json(data.get('body_json')),
         data.get('header_html', ''), data.get('footer_html', ''),
         1 if data.get('is_active', 1) else 0)
    )
    db.commit()
    return jsonify({'success': True, 'id': cur.lastrowid, 'message': '模板已创建'})


@app.route('/api/admin/builtin-templates/<int:tid>', methods=['PUT'])
@admin_required
def admin_update_builtin_template(tid):
    data = request.get_json() or {}
    db = get_db()
    r = db.execute("SELECT id FROM builtin_templates WHERE id = ?", (tid,)).fetchone()
    if not r:
        return jsonify({'success': False, 'message': '模板不存在'})
    db.execute(
        """UPDATE builtin_templates SET
           name=?, category=?, description=?, accent=?, bg=?, style_json=?, body_json=?,
           header_html=?, footer_html=?, is_active=?, updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (data.get('name', '未命名'), data.get('category', '通用'), data.get('description', ''),
         data.get('accent', '#888888'), data.get('bg', '#f0f0f0'),
         _norm_json(data.get('style_json')), _norm_json(data.get('body_json')),
         data.get('header_html', ''), data.get('footer_html', ''),
         1 if data.get('is_active', 1) else 0, tid)
    )
    db.commit()
    return jsonify({'success': True, 'message': '模板已更新'})


@app.route('/api/admin/builtin-templates/<int:tid>', methods=['DELETE'])
@admin_required
def admin_delete_builtin_template(tid):
    db = get_db()
    db.execute("DELETE FROM builtin_templates WHERE id = ?", (tid,))
    db.commit()
    return jsonify({'success': True, 'message': '模板已删除'})


@app.route('/api/admin/builtin-templates/preview', methods=['POST'])
@admin_required
def admin_preview_builtin_template():
    """用当前编辑中的配置渲染一段示例，供后台实时预览（不落库）。"""
    data = request.get_json() or {}
    fake = {
        'name': '预览模板', 'category': '通用', 'description': '',
        'accent': data.get('accent', '#888888'), 'bg': data.get('bg', '#ffffff'),
        'style_json': _norm_json(data.get('style_json')),
        'body_json': _norm_json(data.get('body_json')),
        'header_html': data.get('header_html', ''),
        'footer_html': data.get('footer_html', ''),
        'is_active': 1,
    }
    sample = [
        {'type': 'h2', 'value': '示例小标题：一段副标题文字'},
        {'type': 'p', 'value': '这是一段示例正文，用于预览当前模板的字体颜色、字号、行高与段落间距效果，确保排版符合预期。'},
        {'type': 'blockquote', 'value': '这是一段示例引用文字，通常用于强调观点或金句。'},
        {'type': 'img', 'value': 'http://example.com/sample.png'},
    ]
    html = render_builtin_from_record(fake, sample)
    return jsonify({'success': True, 'html': html})


@app.route('/admin/builtin-templates')
@admin_required
def admin_builtin_templates():
    return read_template('admin/builtin_templates.html')


@app.route('/admin/generation-records')
@admin_required
def admin_generation_records():
    return read_template('admin/generation_records.html')


@app.route('/download-wechat-extension')
@login_required
def download_wechat_extension():
    """动态把 wechat_extension 目录打包成 zip 供用户下载，本地加载到浏览器即可用。"""
    import io, zipfile
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wechat_extension')
    if not os.path.isdir(base):
        return jsonify({'success': False, 'message': '扩展目录不存在'}), 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(base):
            for f in files:
                fp = os.path.join(root, f)
                z.write(fp, os.path.relpath(fp, base))
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name='wechat_paste_extension.zip')


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
            'SELECT id, name, description, thumbnail, created_by, author_name, is_public, created_at, updated_at, template_type, blocks_json '
            'FROM article_templates ORDER BY is_public DESC, updated_at DESC'
        ).fetchall()
    else:
        rows = db.execute(
            'SELECT id, name, description, thumbnail, created_by, author_name, is_public, created_at, updated_at, template_type, blocks_json '
            'FROM article_templates WHERE created_by=? OR is_public=1 ORDER BY is_public DESC, updated_at DESC',
            (uid,)
        ).fetchall()

    templates = []
    for r in rows:
        blocks = []
        try:
            blocks = json.loads(r['blocks_json'] or '[]')
        except Exception:
            blocks = []
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
            'template_type': r['template_type'] or 'style',
            'blocks': blocks,
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
    template_type = (data.get('template_type') or 'style').strip()
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
            'UPDATE article_templates SET name=?, description=?, blocks_json=?, thumbnail=?, author_name=?, template_type=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
            (name, description, blocks_json, thumbnail, author_name, template_type, tid)
        )
        db.commit()
        return jsonify({'success': True, 'message': '模板已更新', 'id': tid})
    else:
        cur = db.execute(
            'INSERT INTO article_templates (name, description, blocks_json, thumbnail, created_by, author_name, is_public, template_type) VALUES (?, ?, ?, ?, ?, ?, 0, ?)',
            (name, description, blocks_json, thumbnail, uid, author_name, template_type)
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

    def _extract_url(val):
        """从图片值中提取 URL 字符串（兼容 string 和 {src,url} 对象格式）"""
        if isinstance(val, str):
            return val
        if isinstance(val, dict):
            return val.get('url') or val.get('src') or ''
        return str(val) if val else ''

    try:
        blocks = json.loads(r['blocks_json'])
    except Exception:
        blocks = []

    # 分类用户内容（图片保留完整对象 {src,url}，交给 _img_pair 处理）
    user_titles = [title] if title else []
    user_subtitles = [s['text'] for s in sections if s.get('type') == 'h2' and (s.get('text') or '').strip()]
    user_bodies = [s['text'] for s in sections if s.get('type') == 'p' and (s.get('text') or '').strip()]
    user_quotes = [s['text'] for s in sections if s.get('type') == 'blockquote' and (s.get('text') or '').strip()]
    user_images = [img for img in images if img]
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
            raw = take('image')
            if raw is None:
                # 保留模板原始图片（如果有）
                pair = {'preview': props.get('src', ''), 'wx': props.get('src', '')}
            else:
                pair = _img_pair(raw)
            src = pair['preview'] or pair['wx']
            if src:
                width = props.get('width', '100%')
                radius = props.get('borderRadius', 8)
                align = props.get('align', 'center')
                margin = '0 auto' if align == 'center' else f'margin-{align}:0'
                html_parts.append(f'<img src="{src}" data-wx="{pair["wx"] or src}" style="max-width:{width};border-radius:{radius}px;display:block;{margin};" />')
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
    # 启动微信公众号定时/批量发布内置调度器（后台守护线程，每30秒扫描到期任务）
    try:
        import wechat_scheduler
        wechat_scheduler.init_scheduler(app)
    except Exception as e:
        print('[warn] 调度器启动失败:', e)
    print("=" * 50)
    print("  百货商城系统已启动")
    print("  访问地址: http://0.0.0.0:5000")
    print("  管理员: admin / admin123")
    print("  顾客: customer1 / 123456")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
