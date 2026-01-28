from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from app.models import Role, User, UserRole
from app.utils.security import hash_password

VALID_ROLES = {"USER", "KB_DOCTOR", "ADMIN"}


def user_payload(user: User) -> Dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "status": user.status,
        "roles": sorted([r.name for r in user.roles]),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def list_users_payloads(limit: int = 100) -> List[Dict[str, Any]]:
    rows = User.query.order_by(User.id.desc()).limit(limit).all()
    return [user_payload(u) for u in rows]


def _normalize_role_names(data: Dict[str, Any], default_role: Optional[str]) -> List[str]:
    role_names = data.get("roles")
    if isinstance(role_names, list) and role_names:
        role_names = [
            str(role).strip().upper()
            for role in role_names
            if str(role).strip()
        ]
    else:
        role_value = (data.get("role") or "").strip().upper()
        if role_value:
            role_names = [role_value]
        elif default_role:
            role_names = [default_role]
        else:
            role_names = []
    return role_names


def _ensure_roles_exist(role_names: List[str]) -> Tuple[Optional[List[Role]], Optional[str], int]:
    if not role_names:
        return None, "roles cannot be empty", 400
    if not all(role in VALID_ROLES for role in role_names):
        return None, "roles must be USER, KB_DOCTOR, or ADMIN", 400
    roles = Role.query.filter(Role.name.in_(role_names)).all()
    if len(roles) != len(set(role_names)):
        missing = sorted(set(role_names) - {role.name for role in roles})
        return None, f"role(s) not found: {', '.join(missing)}", 400
    return roles, None, 200


def create_user_from_payload(
    data: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role_names = _normalize_role_names(data, default_role="USER")

    if not name or not email or not password:
        return None, "name, email, password are required", 400

    roles, error, status = _ensure_roles_exist(role_names)
    if error:
        return None, error, status

    if User.query.filter_by(email=email).first():
        return None, "email already exists", 409

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        status="ACTIVE",
    )
    db.session.add(user)
    db.session.commit()

    for role in roles or []:
        db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.commit()

    return user_payload(user), None, 201


def update_user_from_payload(
    user: User,
    data: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return None, "name cannot be empty", 400
        user.name = name

    if "email" in data:
        email = (data.get("email") or "").strip().lower()
        if not email:
            return None, "email cannot be empty", 400
        if User.query.filter(User.email == email, User.id != user.id).first():
            return None, "email already exists", 409
        user.email = email

    if "status" in data:
        status = (data.get("status") or "").strip().upper()
        if status not in ("ACTIVE", "DISABLED"):
            return None, "status must be ACTIVE or DISABLED", 400
        user.status = status

    if "roles" in data or "role" in data:
        role_names = _normalize_role_names(data, default_role=None)
        roles, error, status = _ensure_roles_exist(role_names)
        if error:
            return None, error, status
        user.roles = roles or []

    db.session.commit()
    return user_payload(user), None, 200
