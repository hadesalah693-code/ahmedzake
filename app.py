import os
import uuid
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
from datetime import datetime, date
from werkzeug.utils import secure_filename
from flask_login import login_required, login_user, logout_user, current_user

from config import SECRET_KEY, PORT, ADMIN_USERNAME
from database import (
    get_db, init_db, generate_invoice_number, enrich_order,
    get_active_services, UPLOADS_DIR, ALLOWED_EXTENSIONS,
)
from backup import create_backup, auto_backup_if_needed, list_backups
from network import get_local_ips, get_access_urls
from auth import (
    init_auth, User, permission_required, role_required,
    verify_password, hash_password, ROLES,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
init_db()
init_auth(app, get_db)
auto_backup_if_needed()

EXPENSE_CATEGORIES = [
    "إيجار",
    "رواتب",
    "قرطاسية",
    "صيانة",
    "كهرباء وماء",
    "إنترنت",
    "مواد طباعة",
    "أخرى",
]

PAYMENT_METHODS = {
    "cash": "كاش",
    "card": "ماكينة",
    "transfer": "تحويل بنكي",
}


def row_to_dict(row):
    return dict(row) if row else None


def allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def save_order_items(conn, order_id, items):
    conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
    for i, item in enumerate(items):
        conn.execute(
            """INSERT INTO order_items (order_id, service_type, description, amount, sort_order)
               VALUES (?, ?, ?, ?, ?)""",
            (order_id, item["service_type"], item.get("description", ""), float(item["amount"]), i),
        )


def items_summary(items):
    if not items:
        return "", ""
    service_type = "، ".join(i["service_type"] for i in items)
    description = " | ".join(i.get("description", "") for i in items if i.get("description"))
    return service_type, description


def total_from_items(items):
    return sum(float(i["amount"]) for i in items)


# ── Auth ──

@app.route("/login")
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "اسم المستخدم وكلمة المرور مطلوبان"}), 400

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
    ).fetchone()
    conn.close()

    if not row or not verify_password(row["password_hash"], password):
        return jsonify({"error": "اسم المستخدم أو كلمة المرور غير صحيحة"}), 401

    user = User(row["id"], row["username"], row["role"], row["full_name"])
    login_user(user, remember=True)
    return jsonify({"ok": True, "user": user.to_dict()})


@app.route("/api/auth/logout", methods=["POST"])
@login_required
def api_logout():
    logout_user()
    return jsonify({"ok": True})


@app.route("/api/auth/me", methods=["GET"])
def api_me():
    if not current_user.is_authenticated:
        return jsonify({"authenticated": False}), 401
    return jsonify({"authenticated": True, "user": current_user.to_dict()})


# ── Users (admin only) ──

@app.route("/api/users", methods=["GET"])
@login_required
@role_required("admin")
def list_users():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, full_name, role, is_active, created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return jsonify([{**row_to_dict(r), "role_label": ROLES.get(r["role"], r["role"])} for r in rows])


@app.route("/api/users", methods=["POST"])
@login_required
@role_required("admin")
def create_user():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = data.get("role", "employee")
    full_name = (data.get("full_name") or "").strip()

    if not username or not password:
        return jsonify({"error": "اسم المستخدم وكلمة المرور مطلوبان"}), 400
    if role not in ROLES:
        return jsonify({"error": "دور غير صالح"}), 400

    conn = get_db()
    exists = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if exists:
        conn.close()
        return jsonify({"error": "اسم المستخدم موجود مسبقاً"}), 400

    now = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, full_name, role, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
        (username, hash_password(password), full_name, role, now),
    )
    conn.commit()
    row = conn.execute("SELECT id, username, full_name, role, is_active, created_at FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify({**row_to_dict(row), "role_label": ROLES.get(row["role"])}), 201


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
@login_required
@role_required("admin")
def delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({"error": "لا يمكن حذف حسابك"}), 400
    conn = get_db()
    conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/users/<int:user_id>/password", methods=["PUT"])
@login_required
@role_required("admin")
def change_user_password(user_id):
    data = request.json or {}
    password = data.get("password") or ""
    if len(password) < 4:
        return jsonify({"error": "كلمة المرور قصيرة جداً"}), 400
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── Pages ──

@app.route("/")
@login_required
def index():
    conn = get_db()
    service_types = [s["name"] for s in get_active_services(conn)]
    conn.close()
    return render_template(
        "index.html",
        service_types=service_types,
        expense_categories=EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS,
    )


# ── Settings ──

@app.route("/api/settings", methods=["GET"])
@login_required
def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return jsonify({r["key"]: r["value"] for r in rows})


@app.route("/api/settings", methods=["PUT"])
@login_required
@permission_required("settings")
def update_settings():
    data = request.json
    conn = get_db()
    for key, value in data.items():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    conn.commit()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return jsonify({r["key"]: r["value"] for r in rows})


# ── Services (dynamic) ──

@app.route("/api/services", methods=["GET"])
@login_required
def list_services():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, sort_order FROM services WHERE is_active = 1 ORDER BY sort_order, id"
    ).fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/services", methods=["POST"])
@login_required
@permission_required("services")
def add_service():
    data = request.json
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "اسم الخدمة مطلوب"}), 400

    conn = get_db()
    exists = conn.execute("SELECT id FROM services WHERE name = ?", (name,)).fetchone()
    if exists:
        conn.execute("UPDATE services SET is_active = 1 WHERE id = ?", (exists["id"],))
        conn.commit()
        row = conn.execute("SELECT id, name, sort_order FROM services WHERE id = ?", (exists["id"],)).fetchone()
        conn.close()
        return jsonify(row_to_dict(row))

    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) as m FROM services").fetchone()["m"]
    now = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO services (name, sort_order, is_active, created_at) VALUES (?, ?, 1, ?)",
        (name, max_order + 1, now),
    )
    conn.commit()
    row = conn.execute("SELECT id, name, sort_order FROM services WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/services/<int:service_id>", methods=["DELETE"])
@login_required
@permission_required("services")
def delete_service(service_id):
    conn = get_db()
    conn.execute("UPDATE services SET is_active = 0 WHERE id = ?", (service_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── Orders ──

@app.route("/api/orders", methods=["GET"])
@login_required
@permission_required("archive")
def list_orders():
    month = request.args.get("month")
    search = request.args.get("search", "").strip()
    service = request.args.get("service", "")

    query = "SELECT DISTINCT o.* FROM orders o"
    params = []
    joins = []

    if service:
        joins.append("JOIN order_items oi ON oi.order_id = o.id")
        query += " " + " ".join(joins)

    query += " WHERE o.status != 'cancelled'"

    if month:
        query += " AND strftime('%Y-%m', o.created_at) = ?"
        params.append(month)

    if search:
        query += " AND (o.customer_name LIKE ? OR o.customer_phone LIKE ? OR o.invoice_number LIKE ? OR o.description LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like, like])

    if service:
        query += " AND oi.service_type = ?"
        params.append(service)

    query += " ORDER BY o.created_at DESC"

    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    orders = [enrich_order(conn, r) for r in rows]
    conn.close()
    return jsonify(orders)


@app.route("/api/orders/<int:order_id>", methods=["GET"])
@login_required
@permission_required("archive")
def get_order(order_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "غير موجود"}), 404
    order = enrich_order(conn, row)
    conn.close()
    return jsonify(order)


@app.route("/api/orders", methods=["POST"])
@login_required
@permission_required("orders")
def create_order():
    data = request.json
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "يجب إضافة خدمة واحدة على الأقل"}), 400

    now = datetime.now().isoformat()
    invoice = generate_invoice_number()
    total = total_from_items(items)
    service_type, description = items_summary(items)

    conn = get_db()
    cur = conn.execute(
        """INSERT INTO orders (invoice_number, customer_name, customer_phone, service_type,
           description, amount, payment_method, status, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            invoice,
            data["customer_name"],
            data.get("customer_phone", ""),
            service_type,
            description,
            total,
            data["payment_method"],
            data.get("status", "completed"),
            data.get("notes", ""),
            now,
            now,
        ),
    )
    order_id = cur.lastrowid
    save_order_items(conn, order_id, items)
    conn.commit()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    order = enrich_order(conn, row)
    conn.close()
    return jsonify(order), 201


@app.route("/api/orders/<int:order_id>", methods=["PUT"])
@login_required
@permission_required("orders")
def update_order(order_id):
    data = request.json
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "يجب إضافة خدمة واحدة على الأقل"}), 400

    now = datetime.now().isoformat()
    total = total_from_items(items)
    service_type, description = items_summary(items)

    conn = get_db()
    conn.execute(
        """UPDATE orders SET customer_name=?, customer_phone=?, service_type=?,
           description=?, amount=?, payment_method=?, status=?, notes=?, updated_at=?
           WHERE id=?""",
        (
            data["customer_name"],
            data.get("customer_phone", ""),
            service_type,
            description,
            total,
            data["payment_method"],
            data.get("status", "completed"),
            data.get("notes", ""),
            now,
            order_id,
        ),
    )
    save_order_items(conn, order_id, items)
    conn.commit()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    order = enrich_order(conn, row)
    conn.close()
    return jsonify(order)


@app.route("/api/orders/<int:order_id>", methods=["DELETE"])
@login_required
@permission_required("orders")
def delete_order(order_id):
    conn = get_db()
    conn.execute("UPDATE orders SET status='cancelled', updated_at=? WHERE id=?", (datetime.now().isoformat(), order_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── Files ──

@app.route("/api/orders/<int:order_id>/files", methods=["POST"])
@login_required
@permission_required("archive")
def upload_files(order_id):
    conn = get_db()
    order = conn.execute("SELECT id FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"error": "الطلب غير موجود"}), 404

    files = request.files.getlist("files")
    if not files:
        conn.close()
        return jsonify({"error": "لم يتم اختيار ملفات"}), 400

    order_dir = os.path.join(UPLOADS_DIR, str(order_id))
    os.makedirs(order_dir, exist_ok=True)

    saved = []
    now = datetime.now().isoformat()

    for f in files:
        if not f.filename or not allowed_file(f.filename):
            continue

        original = f.filename
        safe = secure_filename(original)
        ext = os.path.splitext(safe)[1]
        stored = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(order_dir, stored)
        f.save(path)
        size = os.path.getsize(path)

        cur = conn.execute(
            """INSERT INTO order_files (order_id, filename, original_name, file_type, file_size, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (order_id, stored, original, ext, size, now),
        )
        saved.append({
            "id": cur.lastrowid,
            "filename": stored,
            "original_name": original,
            "file_type": ext,
            "file_size": size,
            "created_at": now,
        })

    conn.commit()
    conn.close()
    return jsonify(saved), 201


@app.route("/api/files/<int:file_id>", methods=["DELETE"])
@login_required
@permission_required("archive")
def delete_file(file_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM order_files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "غير موجود"}), 404

    path = os.path.join(UPLOADS_DIR, str(row["order_id"]), row["filename"])
    if os.path.exists(path):
        os.remove(path)

    conn.execute("DELETE FROM order_files WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/uploads/<int:order_id>/<filename>")
@login_required
@permission_required("archive")
def serve_file(order_id, filename):
    return send_from_directory(os.path.join(UPLOADS_DIR, str(order_id)), filename)


# ── Expenses ──

@app.route("/api/expenses", methods=["GET"])
@login_required
@permission_required("expenses")
def list_expenses():
    month = request.args.get("month")
    query = "SELECT * FROM expenses WHERE 1=1"
    params = []
    if month:
        query += " AND strftime('%Y-%m', expense_date) = ?"
        params.append(month)
    query += " ORDER BY expense_date DESC"

    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/expenses", methods=["POST"])
@login_required
@permission_required("expenses")
def create_expense():
    data = request.json
    now = datetime.now().isoformat()
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO expenses (title, category, amount, payment_method, notes, expense_date, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            data["title"],
            data["category"],
            float(data["amount"]),
            data["payment_method"],
            data.get("notes", ""),
            data.get("expense_date", date.today().isoformat()),
            now,
        ),
    )
    conn.commit()
    expense_id = cur.lastrowid
    row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
@login_required
@permission_required("expenses")
def delete_expense(expense_id):
    conn = get_db()
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── Reports ──

def _monthly_data(conn, month):
    revenue = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count, payment_method
           FROM orders WHERE status='completed' AND strftime('%Y-%m', created_at)=?
           GROUP BY payment_method""",
        (month,),
    ).fetchall()

    total_revenue = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM orders WHERE status='completed' AND strftime('%Y-%m', created_at)=?",
        (month,),
    ).fetchone()

    expenses = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count, category
           FROM expenses WHERE strftime('%Y-%m', expense_date)=?
           GROUP BY category""",
        (month,),
    ).fetchall()

    total_expenses = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE strftime('%Y-%m', expense_date)=?",
        (month,),
    ).fetchone()

    services = conn.execute(
        """SELECT oi.service_type, COALESCE(SUM(oi.amount), 0) as total, COUNT(*) as count
           FROM order_items oi
           JOIN orders o ON o.id = oi.order_id
           WHERE o.status='completed' AND strftime('%Y-%m', o.created_at)=?
           GROUP BY oi.service_type ORDER BY total DESC""",
        (month,),
    ).fetchall()

    rev_total = total_revenue["total"]
    exp_total = total_expenses["total"]

    return {
        "period": month,
        "revenue": {
            "total": rev_total,
            "count": total_revenue["count"],
            "by_payment": [row_to_dict(r) for r in revenue],
        },
        "expenses": {
            "total": exp_total,
            "count": total_expenses["count"],
            "by_category": [row_to_dict(r) for r in expenses],
        },
        "profit": rev_total - exp_total,
        "is_profit": rev_total >= exp_total,
        "services": [row_to_dict(r) for r in services],
    }


@app.route("/api/reports/monthly", methods=["GET"])
@login_required
@permission_required("reports")
def monthly_report():
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    conn = get_db()
    data = _monthly_data(conn, month)

    daily = conn.execute(
        """SELECT DATE(created_at) as day, COALESCE(SUM(amount), 0) as revenue
           FROM orders WHERE status='completed' AND strftime('%Y-%m', created_at)=?
           GROUP BY DATE(created_at) ORDER BY day""",
        (month,),
    ).fetchall()
    conn.close()

    data["daily_revenue"] = [row_to_dict(r) for r in daily]
    return jsonify(data)


@app.route("/api/reports/yearly", methods=["GET"])
@login_required
@permission_required("reports")
def yearly_report():
    year = request.args.get("year", str(date.today().year))
    conn = get_db()

    months_data = []
    for m in range(1, 13):
        month = f"{year}-{m:02d}"
        months_data.append(_monthly_data(conn, month))

    total_revenue = sum(m["revenue"]["total"] for m in months_data)
    total_expenses = sum(m["expenses"]["total"] for m in months_data)
    total_orders = sum(m["revenue"]["count"] for m in months_data)

    # Aggregate services for the year
    services = conn.execute(
        """SELECT oi.service_type, COALESCE(SUM(oi.amount), 0) as total, COUNT(*) as count
           FROM order_items oi
           JOIN orders o ON o.id = oi.order_id
           WHERE o.status='completed' AND strftime('%Y', o.created_at)=?
           GROUP BY oi.service_type ORDER BY total DESC""",
        (year,),
    ).fetchall()

    # Aggregate payment methods for the year
    payments = conn.execute(
        """SELECT payment_method, COALESCE(SUM(amount), 0) as total, COUNT(*) as count
           FROM orders WHERE status='completed' AND strftime('%Y', created_at)=?
           GROUP BY payment_method""",
        (year,),
    ).fetchall()

    conn.close()

    profit = total_revenue - total_expenses

    return jsonify({
        "year": year,
        "revenue": {"total": total_revenue, "count": total_orders},
        "expenses": {"total": total_expenses, "count": sum(m["expenses"]["count"] for m in months_data)},
        "profit": profit,
        "is_profit": profit >= 0,
        "months": months_data,
        "services": [row_to_dict(r) for r in services],
        "by_payment": [row_to_dict(r) for r in payments],
    })


@app.route("/api/reports/today", methods=["GET"])
@login_required
@permission_required("dashboard")
def today_summary():
    day = request.args.get("date", date.today().isoformat())
    return jsonify(_daily_data(get_db(), day))


def _daily_data(conn, day):
    revenue = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count, payment_method
           FROM orders WHERE status='completed' AND DATE(created_at)=?
           GROUP BY payment_method""",
        (day,),
    ).fetchall()

    total_revenue = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM orders WHERE status='completed' AND DATE(created_at)=?",
        (day,),
    ).fetchone()

    expenses = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count, category
           FROM expenses WHERE expense_date=?
           GROUP BY category""",
        (day,),
    ).fetchall()

    total_expenses = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE expense_date=?",
        (day,),
    ).fetchone()

    services = conn.execute(
        """SELECT oi.service_type, COALESCE(SUM(oi.amount), 0) as total, COUNT(*) as count
           FROM order_items oi
           JOIN orders o ON o.id = oi.order_id
           WHERE o.status='completed' AND DATE(o.created_at)=?
           GROUP BY oi.service_type ORDER BY total DESC""",
        (day,),
    ).fetchall()

    orders = conn.execute(
        "SELECT * FROM orders WHERE status='completed' AND DATE(created_at)=? ORDER BY created_at DESC",
        (day,),
    ).fetchall()
    orders = [enrich_order(conn, r) for r in orders]

    expense_list = conn.execute(
        "SELECT * FROM expenses WHERE expense_date=? ORDER BY created_at DESC",
        (day,),
    ).fetchall()

    rev_total = total_revenue["total"]
    exp_total = total_expenses["total"]

    result = {
        "date": day,
        "revenue": {
            "total": rev_total,
            "count": total_revenue["count"],
            "by_payment": [row_to_dict(r) for r in revenue],
        },
        "expenses": {
            "total": exp_total,
            "count": total_expenses["count"],
            "by_category": [row_to_dict(r) for r in expenses],
        },
        "profit": rev_total - exp_total,
        "is_profit": rev_total >= exp_total,
        "services": [row_to_dict(r) for r in services],
        "orders": orders,
        "expense_list": [row_to_dict(r) for r in expense_list],
        "net": rev_total - exp_total,
    }
    conn.close()
    return result


@app.route("/api/reports/daily", methods=["GET"])
@login_required
@permission_required("reports")
def daily_report():
    day = request.args.get("date", date.today().isoformat())
    conn = get_db()
    return jsonify(_daily_data(conn, day))


@app.route("/api/network", methods=["GET"])
@login_required
@permission_required("network")
def network_info():
    ips = get_local_ips()
    urls = get_access_urls()
    return jsonify({
        "port": PORT,
        "ips": ips,
        "urls": urls,
        "phone_url": urls[1] if len(urls) > 1 else urls[0],
    })


# ── Backup ──

@app.route("/api/backup", methods=["POST"])
@login_required
@permission_required("backup")
def manual_backup():
    try:
        result = create_backup()
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/backup", methods=["GET"])
@login_required
@permission_required("backup")
def get_backups():
    conn = get_db()
    last = conn.execute("SELECT value FROM settings WHERE key = 'last_backup'").fetchone()
    conn.close()
    return jsonify({
        "last_backup": last["value"] if last else "",
        "backups": list_backups(),
    })


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    urls = get_access_urls()
    print("\n" + "=" * 50)
    print("  Al-Wisam University Services")
    print("  Local:   http://127.0.0.1:" + str(PORT))
    for ip in get_local_ips():
        print(f"  Network: http://{ip}:{PORT}")
    print("  Open the Network link on your phone (same WiFi)")
    print("=" * 50 + "\n")
    app.run(host="0.0.0.0", debug=False, port=PORT)
