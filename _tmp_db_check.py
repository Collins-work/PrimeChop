import sqlite3
conn = sqlite3.connect('primechop.db')
cur = conn.cursor()
print(cur.execute('SELECT name FROM sqlite_master WHERE type="table" ORDER BY name').fetchall())
conn.close()
