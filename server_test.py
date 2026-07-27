import sys
sys.path.insert(0, r"C:\mall_system")
import traceback
try:
    from app import app
    with app.test_client() as client:
        resp = client.post('/api/auth/login', json={'username':'admin','password':'admin123'})
        print('Status:', resp.status_code)
        if resp.status_code != 200:
            print('Body:', resp.data.decode()[:2000])
except Exception as e:
    traceback.print_exc()
