import sqlite3
conn = sqlite3.connect('primechop.db')
cur = conn.cursor()
for t in ['vendors','menu_items','orders']:
    print(f'--- {t} columns ---')
    for row in cur.execute(f'PRAGMA table_info({t})').fetchall():
        print(row)
conn.close()
