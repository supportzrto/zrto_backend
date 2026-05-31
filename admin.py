import sqlite3

conn = sqlite3.connect("test.db")  # ✅ FIX HERE
cursor = conn.cursor()

email = "ashokcivil27@gmail.com"

cursor.execute(
    "UPDATE users SET role = 'admin' WHERE email = ?",
    (email,)
)

cursor.execute("""
INSERT INTO early_access (full_name, email, brand_name, monthly_orders)
VALUES (?, ?, ?, ?)
""", ("Ashok", "test@gmail.com", "My Brand", "500-2000"))

conn.commit()


cursor.execute("SELECT email, role FROM users WHERE email = ?", (email,))

cursor.execute("ALTER TABLE early_access ADD COLUMN phone VARCHAR")

cursor.execute("PRAGMA table_info(early_access)")


conn.close()

print("✅ User upgraded to admin")