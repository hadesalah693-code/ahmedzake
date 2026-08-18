from functools import wraps
from flask import jsonify, redirect, url_for, request
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash

login_manager = LoginManager()

ROLES = {
    "admin": "مدير",
    "employee": "موظف",
    "accountant": "محاسب",
}

# صلاحيات كل دور
PERMISSIONS = {
    "admin": {
        "dashboard", "orders", "archive", "expenses", "reports",
        "settings", "services", "users", "backup", "network",
    },
    "employee": {"dashboard", "orders", "archive", "reports"},
    "accountant": {"dashboard", "expenses", "reports"},
}


class User(UserMixin):
    def __init__(self, id, username, role, full_name="", is_active=True):
        self.id = id
        self.username = username
        self.role = role
        self.full_name = full_name
        self._is_active = is_active

    @property
    def is_active(self):
        return self._is_active

    def has_permission(self, perm):
        return perm in PERMISSIONS.get(self.role, set())

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "role_label": ROLES.get(self.role, self.role),
            "full_name": self.full_name,
            "permissions": list(PERMISSIONS.get(self.role, set())),
        }


def init_auth(app, get_db):
    login_manager.init_app(app)
    login_manager.login_view = "login_page"
    login_manager.session_protection = "strong"

    @login_manager.user_loader
    def load_user(user_id):
        conn = get_db()
        row = conn.execute(
            "SELECT id, username, role, full_name, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        conn.close()
        if not row or not row["is_active"]:
            return None
        return User(row["id"], row["username"], row["role"], row["full_name"], bool(row["is_active"]))

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify({"error": "يجب تسجيل الدخول"}), 401
        return redirect(url_for("login_page"))


def permission_required(perm):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "يجب تسجيل الدخول"}), 401
            if not current_user.has_permission(perm):
                return jsonify({"error": "ليس لديك صلاحية"}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "يجب تسجيل الدخول"}), 401
            if current_user.role not in roles:
                return jsonify({"error": "ليس لديك صلاحية"}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def hash_password(password):
    return generate_password_hash(password)


def verify_password(stored_hash, password):
    return check_password_hash(stored_hash, password)
