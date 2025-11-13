import sqlite3

conn = sqlite3.connect("medicines.db")
cursor = conn.cursor()

# ❌ Delete old table
cursor.execute("DROP TABLE IF EXISTS users")

# ✅ Create correct one
cursor.execute("""
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
)
""")

conn.commit()
conn.close()
print("✅ Fixed! Users table recreated with 'password_hash' column.")
