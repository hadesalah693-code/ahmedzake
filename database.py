import sqlite3
import os
from datetime import datetime
from config import DATA_DIR, ADMIN_USERNAME, ADMIN_PASSWORD
from auth import hash_password

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(DATA_DIR, "wisam.db")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
BACKUPS_DIR = os.path.join(DATA_DIR, "backups")

ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".txt", ".zip", ".rar",
}


def get_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            customer_phone TEXT DEFAULT '',
            service_type TEXT NOT NULL DEFAULT '',
            description TEXT DEFAULT '',
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL CHECK(payment_method IN ('cash', 'card', 'transfer')),
            status TEXT NOT NULL DEFAULT 'completed' CHECK(status IN ('pending', 'completed', 'cancelled')),
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            service_type TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount REAL NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS order_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_type TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL CHECK(payment_method IN ('cash', 'card', 'transfer')),
            notes TEXT DEFAULT '',
            expense_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT DEFAULT '',
            role TEXT NOT NULL CHECK(role IN ('admin', 'employee', 'accountant')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        INSERT OR IGNORE INTO settings (key, value) VALUES
            ('office_name', 'الوسام للخدمات الجامعية'),
            ('office_phone', ''),
            ('office_address', ''),
            ('currency', 'د.ع'),
            ('last_backup', '');
    """)
    conn.commit()

    # تحديث الاسم القديم إن وُجد
    conn.execute(
        "UPDATE settings SET value = 'الوسام للخدمات الجامعية' WHERE key = 'office_name' AND value = 'مكتب الوسام'"
    )

    # إضافة الخدمات الافتراضية
    count = conn.execute("SELECT COUNT(*) as c FROM services").fetchone()["c"]
    if count == 0:
        now = datetime.now().isoformat()
        defaults = ["ترجمة", "طباعة", "تصوير مستندات", "تخليص معاملات", "أخرى"]
        for i, name in enumerate(defaults):
            conn.execute(
                "INSERT INTO services (name, sort_order, is_active, created_at) VALUES (?, ?, 1, ?)",
                (name, i, now),
            )

    # Migrate old single-service orders to order_items
    orders_without_items = conn.execute("""
        SELECT o.id, o.service_type, o.description, o.amount
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        WHERE oi.id IS NULL AND o.service_type != ''
    """).fetchall()

    for order in orders_without_items:
        conn.execute(
            """INSERT INTO order_items (order_id, service_type, description, amount, sort_order)
               VALUES (?, ?, ?, ?, 0)""",
            (order["id"], order["service_type"], order["description"], order["amount"]),
        )

    # إنشاء حساب المدير الافتراضي
    admin_exists = conn.execute("SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,)).fetchone()
    if not admin_exists:
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            (ADMIN_USERNAME, hash_password(ADMIN_PASSWORD), "المدير", "admin", now),
        )

    conn.commit()
    conn.close()
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(BACKUPS_DIR, exist_ok=True)


def generate_invoice_number():
    conn = get_db()
    year = datetime.now().year
    prefix = f"INV-{year}-"
    row = conn.execute(
        "SELECT invoice_number FROM orders WHERE invoice_number LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}%",),
    ).fetchone()
    conn.close()

    if row:
        last_num = int(row["invoice_number"].split("-")[-1])
        next_num = last_num + 1
    else:
        next_num = 1

    return f"{prefix}{next_num:04d}"


def get_order_items(conn, order_id):
    rows = conn.execute(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY sort_order, id",
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_order_files(conn, order_id):
    rows = conn.execute(
        "SELECT * FROM order_files WHERE order_id = ? ORDER BY created_at",
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_active_services(conn):
    rows = conn.execute(
        "SELECT id, name FROM services WHERE is_active = 1 ORDER BY sort_order, id"
    ).fetchall()
    return [dict(r) for r in rows]


def enrich_order(conn, row):
    order = dict(row)
    order["items"] = get_order_items(conn, order["id"])
    order["files"] = get_order_files(conn, order["id"])
    if order["items"]:
        order["service_type"] = "، ".join(i["service_type"] for i in order["items"])
    return order
