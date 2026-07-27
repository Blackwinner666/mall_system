# -*- coding: utf-8 -*-
import requests, sys

BASE = 'http://152.136.246.33:5000'

s = requests.Session()

# 1. Login
print("1. 登录测试...")
r = s.post(f'{BASE}/api/auth/login', json={'username': 'admin', 'password': 'admin123'})
js = r.json()
print(f"   {'OK' if js.get('success') else 'FAIL'}: {js.get('message', '')} (user={js.get('user',{}).get('username','')})")

# 2. Admin pages (authenticated)
pages = {
    '/admin': '首页 Dashboard',
    '/admin/store': '店铺管理',
    '/admin/products': '商品管理',
    '/admin/orders': '订单管理',
    '/admin/after-sales': '售后管理',
}
print("\n2. 管理页面测试...")
for path, name in pages.items():
    r = s.get(f'{BASE}{path}')
    ok = 'dashboard' in r.text.lower() or 'admin' in r.text.lower() or '管理' in r.text or '店铺' in r.text
    print(f"   {name} ({path}): Status={r.status_code}, Len={len(r.text)}, HasContent={'OK' if ok else 'CHECK'}")

# 3. API endpoints
apis = {
    '/api/admin/analytics': '经营数据',
    '/api/admin/brands': '品牌管理',
    '/api/products': '商品列表',
    '/api/categories': '商品分类',
    '/api/admin/collections': '商品合集',
    '/api/orders': '订单列表',
    '/api/admin/deliveries': '配送管理',
    '/api/admin/shipping-addresses': '快递地址',
    '/api/admin/reviews': '订单评价',
    '/api/admin/after-sales': '售后处理',
    '/api/admin/appeals': '申诉管理',
    '/api/admin/members': '成员管理',
    '/api/admin/announcements': '公告管理',
    '/api/admin/activities': '活动管理',
    '/api/admin/store-blocks': '主页模块',
}
print("\n3. API 端点测试...")
all_ok = True
for path, name in apis.items():
    r = s.get(f'{BASE}{path}')
    ok = r.status_code == 200
    if not ok:
        all_ok = False
    status = 'OK' if ok else f'FAIL ({r.status_code})'
    print(f"   {name}: {status}")

print(f"\n{'='*50}")
print(f"结果: {'全部通过!' if all_ok else '存在失败项，需修复'}")
print(f"{'='*50}")
