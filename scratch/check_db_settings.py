import sys
sys.path.append(r"d:\JARVIS M7")
from core.database import db

# Let's inspect all settings
with db.conn:
    cursor = db.conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    print("Database Settings:")
    for row in rows:
        print(f"  {row[0]} = {repr(row[1])}")
