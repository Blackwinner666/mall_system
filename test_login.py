# -*- coding: utf-8 -*-
import requests

base = 'http://127.0.0.1:5000'

# Test login
print("=== Test Login ===")
r = requests.post(f'{base}/api/auth/login', json={
    'username': 'admin',
    'password': 'admin123'
})
print(f'Status: {r.status_code}')
try:
    print(f'Body: {r.json()}')
except:
    print(f'Body: {r.text[:200]}')

# Test dashboard API
print("\n=== Test Dashboard ===")
r = requests.get(f'{base}/api/dashboard/stats')
print(f'Status: {r.status_code}')
try:
    print(f'Body: {r.json()}')
except:
    print(f'Body: {r.text[:200]}')

# Test store API
print("\n=== Test Store Brands ===")
r = requests.get(f'{base}/api/store/brands')
print(f'Status: {r.status_code}')
try:
    print(f'Body: {r.json()}')
except:
    print(f'Body: {r.text[:200]}')

# Test product list
print("\n=== Test Products ===")
r = requests.get(f'{base}/api/products/list')
print(f'Status: {r.status_code}')
try:
    print(f'Body: {r.json()}')
except:
    print(f'Body: {r.text[:200]}')

# Test orders
print("\n=== Test Orders ===")
r = requests.get(f'{base}/api/orders/list')
print(f'Status: {r.status_code}')
try:
    print(f'Body: {r.json()}')
except:
    print(f'Body: {r.text[:200]}')

# Test after_sales
print("\n=== Test AfterSales ===")
r = requests.get(f'{base}/api/after-sales/list')
print(f'Status: {r.status_code}')
try:
    print(f'Body: {r.json()}')
except:
    print(f'Body: {r.text[:200]}')

# Test admin pages
pages = ['/admin', '/admin/store', '/admin/products', '/admin/orders', '/admin/after-sales']
print("\n=== Test Admin Pages ===")
for p in pages:
    r = requests.get(f'{base}{p}')
    print(f'{p}: {r.status_code} (len={len(r.text)})')

print("\n=== ALL DONE ===")
