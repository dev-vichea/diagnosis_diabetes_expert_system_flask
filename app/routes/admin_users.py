from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import User, Role, UserRole
from app.utils.decorators import require_permission
from app.utils.security import hash_password

admin_users_bp = Blueprint("admin_users", __name__)


@admin_users_bp.post("/users")
@jwt_required()
@require_permission("USER_CREATE")
def admin_create_user():
    """
    Admin creates a user with a specific role: USER / KB_DOCTOR / ADMIN
    """
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role_name = (data.get("role") or "USER").strip().upper()

    if not name or not email or not password:
        return {"message": "name, email, password are required"}, 400

    if role_name not in ("USER", "KB_DOCTOR", "ADMIN"):
        return {"message": "role must be USER, KB_DOCTOR, or ADMIN"}, 400

    if User.query.filter_by(email=email).first():
        return {"message": "email already exists"}, 409

    role = Role.query.filter_by(name=role_name).first()
    if not role:
        return {"message": f"role '{role_name}' not found in database"}, 400

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        status="ACTIVE",
    )
    db.session.add(user)
    db.session.commit()

    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.commit()

    return {
        "message": "user created",
        "user": {"id": user.id, "name": user.name, "email": user.email, "role": role.name},
    }, 201


@admin_users_bp.get("/users")
@jwt_required()
@require_permission("USER_VIEW")
def admin_list_users():
    rows = User.query.order_by(User.id.desc()).limit(100).all()
    return {
        "items": [
            {"id": u.id, "name": u.name, "email": u.email, "status": u.status}
            for u in rows
        ]
    }
