import sqlite3

conn = sqlite3.connect("users.db")
cursor = conn.cursor()

# Check existing columns
cursor.execute("PRAGMA table_info(users)")
columns = [col[1] for col in cursor.fetchall()]

if "api_purchased" not in columns:
    cursor.execute("ALTER TABLE users ADD COLUMN api_purchased BOOLEAN DEFAULT 0")
    print("✅ Column added")
else:
    print("⚠️ Column already exists, skipping")

conn.commit()
conn.close()