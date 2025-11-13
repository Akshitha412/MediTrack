import sqlite3

conn = sqlite3.connect("medicines.db")
cursor = conn.cursor()

# Add user_id column if it doesn’t exist
try:
    cursor.execute("ALTER TABLE medicine ADD COLUMN user_id INTEGER")
    print("✅ user_id column added to medicine table.")
except sqlite3.OperationalError:
    print("⚠️ user_id column already exists.")

conn.commit()
conn.close()
