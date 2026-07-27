import sqlite3
db = sqlite3.connect(r"C:\mall_system\mall.db")
cur = db.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

cur.execute("PRAGMA table_info(products)")
cols = [(r[1], r[2]) for r in cur.fetchall()]
print("Products cols:", cols)

# Check if detail_html exists
cur.execute("PRAGMA table_info(products)")
has_detail = any('detail_html' in r for r in cur.fetchall())
print("Has detail_html:", has_detail)
db.close()
