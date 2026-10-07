import os
import shutil
import zipfile
from datetime import datetime, timedelta

from database import DB_PATH, UPLOADS_DIR, BACKUPS_DIR, DATA_DIR, get_db
from database import using_postgres, _PG_SCHEMA, _SQLITE_SCHEMA

MAX_BACKUPS = 30
BACKUP_INTERVAL_HOURS = 24

_DUMP_TABLES = [
    ("settings", "key, value", "key"),
    ("services", "id, name, sort_order, is_active, created_at", "id"),
    ("users", "id, username, password_hash, full_name, role, is_active, created_at", "id"),
    ("orders", "id, invoice_number, customer_name, customer_phone, service_type, description, amount, payment_method, status, notes, created_at, updated_at", "id"),
    ("order_items", "id, order_id, service_type, description, amount, sort_order", "id"),
    ("order_files", "id, order_id, filename, original_name, file_type, file_size, created_at", "id"),
    ("expenses", "id, title, category, amount, payment_method, notes, expense_date, created_at", "id"),
]


def _sql_literal(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def _dump_sql_database(conn):
    lines = ["-- Al-Wisam database dump", "-- Generated: " + datetime.now().isoformat(), ""]
    schema = "\n\n".join(_PG_SCHEMA) if using_postgres() else _SQLITE_SCHEMA
    lines.append(schema)
    lines.append("")
    for table, cols, order_col in _DUMP_TABLES:
        rows = conn.execute(f"SELECT {cols} FROM {table} ORDER BY {order_col}").fetchall()
        if not rows:
            continue
        lines.append(f"-- {table}")
        for r in rows:
            vals = ", ".join(_sql_literal(v) for v in dict(r).values())
            lines.append(f"INSERT INTO {table} ({cols}) VALUES ({vals});")
        lines.append("")
    return "\n".join(lines)


def create_backup():
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_name = f"backup_{timestamp}.zip"
    backup_path = os.path.join(BACKUPS_DIR, backup_name)

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if using_postgres():
            conn = get_db()
            zf.writestr("database.sql", _dump_sql_database(conn))
            conn.close()
        elif os.path.exists(DB_PATH):
            zf.write(DB_PATH, "wisam.db")

        if os.path.isdir(UPLOADS_DIR):
            for root, _, files in os.walk(UPLOADS_DIR):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, DATA_DIR)
                    zf.write(full_path, arcname)

    _cleanup_old_backups()

    now = datetime.now().isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('last_backup', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (now,),
    )
    conn.commit()
    conn.close()

    return {
        "filename": backup_name,
        "path": backup_path,
        "size": os.path.getsize(backup_path),
        "created_at": now,
    }


def _cleanup_old_backups():
    backups = sorted(
        [f for f in os.listdir(BACKUPS_DIR) if f.startswith("backup_") and f.endswith(".zip")],
        reverse=True,
    )
    for old in backups[MAX_BACKUPS:]:
        try:
            os.remove(os.path.join(BACKUPS_DIR, old))
        except OSError:
            pass


def should_auto_backup():
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = 'last_backup'").fetchone()
    conn.close()

    if not row or not row["value"]:
        return True

    try:
        last = datetime.fromisoformat(row["value"])
        return datetime.now() - last > timedelta(hours=BACKUP_INTERVAL_HOURS)
    except ValueError:
        return True


def auto_backup_if_needed():
    if should_auto_backup():
        try:
            result = create_backup()
            return {"auto": True, **result}
        except Exception as e:
            return {"auto": True, "error": str(e)}
    return {"auto": False}


def list_backups():
    if not os.path.isdir(BACKUPS_DIR):
        return []

    backups = []
    for name in sorted(os.listdir(BACKUPS_DIR), reverse=True):
        if name.startswith("backup_") and name.endswith(".zip"):
            path = os.path.join(BACKUPS_DIR, name)
            backups.append({
                "filename": name,
                "size": os.path.getsize(path),
                "created_at": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
            })
    return backups
