from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import AuditLog, Role, User, UserRole
from app.services.audit_service import record_audit_event
from app.utils.security import hash_password

VALID_ROLES = {"USER", "KB_DOCTOR", "ADMIN"}
ACTIVITY_ACTIONS = {"LOGIN", "LOGOUT", "REGISTER", "USER_CREATED", "USER_UPDATED"}


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
    actor_user_id: Optional[int] = None,
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

    record_audit_event(
        action="USER_CREATED",
        entity="USER",
        actor_user_id=actor_user_id,
        entity_id=user.id,
        meta={
            "target_user_name": user.name,
            "target_user_email": user.email,
            "roles": sorted([role.name for role in user.roles]),
        },
    )

    return user_payload(user), None, 201


def update_user_from_payload(
    user: User,
    data: Dict[str, Any],
    actor_user_id: Optional[int] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    changes: List[str] = []

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return None, "name cannot be empty", 400
        if user.name != name:
            changes.append("name")
        user.name = name

    if "email" in data:
        email = (data.get("email") or "").strip().lower()
        if not email:
            return None, "email cannot be empty", 400
        if User.query.filter(User.email == email, User.id != user.id).first():
            return None, "email already exists", 409
        if user.email != email:
            changes.append("email")
        user.email = email

    if "status" in data:
        status = (data.get("status") or "").strip().upper()
        if status not in ("ACTIVE", "DISABLED"):
            return None, "status must be ACTIVE or DISABLED", 400
        if user.status != status:
            changes.append("status")
        user.status = status

    if "roles" in data or "role" in data:
        role_names = _normalize_role_names(data, default_role=None)
        roles, error, status = _ensure_roles_exist(role_names)
        if error:
            return None, error, status
        current_roles = sorted([role.name for role in user.roles])
        next_roles = sorted([role.name for role in (roles or [])])
        if current_roles != next_roles:
            changes.append("roles")
        user.roles = roles or []

    db.session.commit()

    if changes:
        record_audit_event(
            action="USER_UPDATED",
            entity="USER",
            actor_user_id=actor_user_id,
            entity_id=user.id,
            meta={
                "target_user_name": user.name,
                "target_user_email": user.email,
                "changes": sorted(set(changes)),
            },
        )
    return user_payload(user), None, 200


def _activity_display(log: AuditLog, actor_name: str, actor_email: str) -> Dict[str, Any]:
    meta = log.meta_json if isinstance(log.meta_json, dict) else {}
    action = (log.action or "").upper()
    subject_name = meta.get("target_user_name") or actor_name or actor_email or "Unknown user"

    if action == "LOGIN":
        details = meta.get("details") or "User signed in to the system."
        return {
            "user": actor_name or actor_email or "Unknown user",
            "action": "logged in",
            "type": "login",
            "icon": "box-arrow-in-right",
            "details": details,
        }

    if action == "LOGOUT":
        details = meta.get("details") or "User signed out from the system."
        return {
            "user": actor_name or actor_email or "Unknown user",
            "action": "logged out",
            "type": "logout",
            "icon": "box-arrow-right",
            "details": details,
        }

    if action in {"REGISTER", "USER_CREATED"}:
        actor_text = actor_name or actor_email
        details = "New user account created."
        if actor_text and subject_name and actor_text != subject_name:
            details = f"Created by {actor_text}."
        return {
            "user": subject_name,
            "action": "created account",
            "type": "create",
            "icon": "person-plus",
            "details": details,
        }

    changed_fields = meta.get("changes") if isinstance(meta.get("changes"), list) else []
    detail_parts = [str(item).replace("_", " ") for item in changed_fields if str(item).strip()]
    details = (
        f"Updated {', '.join(detail_parts)}."
        if detail_parts
        else (meta.get("details") or "User profile updated.")
    )
    return {
        "user": subject_name,
        "action": "updated profile",
        "type": "update",
        "icon": "person-gear",
        "details": details,
    }


def list_recent_user_activities(limit: int = 20) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 20), 100))
    items: List[Dict[str, Any]] = []

    try:
        rows = (
            db.session.query(AuditLog, User.name, User.email)
            .outerjoin(User, User.id == AuditLog.actor_user_id)
            .filter(AuditLog.action.in_(ACTIVITY_ACTIONS))
            .order_by(AuditLog.created_at.desc())
            .limit(safe_limit)
            .all()
        )
    except SQLAlchemyError:
        rows = []
        db.session.rollback()

    for log, actor_name, actor_email in rows:
        rendered = _activity_display(log, actor_name or "", actor_email or "")
        items.append(
            {
                "id": log.id,
                "user": rendered["user"],
                "action": rendered["action"],
                "type": rendered["type"],
                "icon": rendered["icon"],
                "details": rendered["details"],
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
        )

    if items:
        return items

    try:
        fallback_users = User.query.order_by(User.created_at.desc()).limit(min(safe_limit, 10)).all()
    except SQLAlchemyError:
        db.session.rollback()
        return []

    for user in fallback_users:
        items.append(
            {
                "id": f"user-{user.id}",
                "user": user.name or user.email or f"User #{user.id}",
                "action": "created account",
                "type": "create",
                "icon": "person-plus",
                "details": "Existing account in the system.",
                "created_at": user.created_at.isoformat() if user.created_at else None,
            }
        )

    return items
