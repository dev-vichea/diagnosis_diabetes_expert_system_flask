from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from app.models import Permission, Role


def role_payload(role: Role) -> Dict[str, Any]:
    return {
        "id": role.id,
        "name": role.name,
        "permissions": sorted([perm.code for perm in role.permissions]),
    }


def list_roles_payloads() -> List[Dict[str, Any]]:
    roles = Role.query.order_by(Role.name.asc()).all()
    return [role_payload(role) for role in roles]


def list_permissions_payloads() -> List[Dict[str, Any]]:
    perms = Permission.query.order_by(Permission.code.asc()).all()
    return [
        {"id": perm.id, "code": perm.code, "description": perm.description}
        for perm in perms
    ]


def update_role_permissions(
    role: Role, permission_codes: Optional[List[Any]]
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    if permission_codes is None:
        return None, "permission_codes are required", 400

    codes = [
        str(code).strip().upper()
        for code in permission_codes
        if str(code).strip()
    ]
    if not codes:
        role.permissions = []
        db.session.commit()
        return role_payload(role), None, 200

    perms = Permission.query.filter(Permission.code.in_(codes)).all()
    if len(perms) != len(set(codes)):
        missing = sorted(set(codes) - {perm.code for perm in perms})
        return None, f"permission(s) not found: {', '.join(missing)}", 400

    role.permissions = perms
    db.session.commit()
    return role_payload(role), None, 200
