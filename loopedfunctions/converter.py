import sqlite3

db = sqlite3.connect('storage.db')

with open('contacted.csv', 'w') as f:
    f.write(','.join(map(lambda t: str(t[0]), db.execute('SELECT nation_id FROM nations_contacted').fetchall())))
