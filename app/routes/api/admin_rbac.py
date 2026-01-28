from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Role, Permission, RolePermission, UserRole
from app.utils.decorators import require_permission

admin_rbac_bp = Blueprint("admin_rbac", __name__)


def _perm_payload(perm: Permission):
    return {"id": perm.id, "code": perm.code, "description": perm.description}


def _role_payload(role: Role):
    return {
        "id": role.id,
        "name": role.name,
        "description": getattr(role, "description", None),
        "permissions": [_perm_payload(p) for p in role.permissions],
    }


@admin_rbac_bp.get("/rbac/roles")
@jwt_required()
@require_permission("RBAC_VIEW")
def list_roles():
    roles = Role.query.order_by(Role.name.asc()).all()
    return {"items": [_role_payload(r) for r in roles]}


@admin_rbac_bp.get("/rbac/roles/<int:role_id>")
@jwt_required()
@require_permission("RBAC_VIEW")
def get_role(role_id: int):
    role = Role.query.get_or_404(role_id)
    return {"role": _role_payload(role)}


@admin_rbac_bp.get("/rbac/permissions")
@jwt_required()
@require_permission("RBAC_VIEW")
def list_permissions():
    perms = Permission.query.order_by(Permission.code.asc()).all()
    return {"items": [_perm_payload(p) for p in perms]}


@admin_rbac_bp.post("/rbac/roles")
@jwt_required()
@require_permission("RBAC_UPDATE")
def create_role():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip().upper()
    if not name:
        return {"message": "name is required"}, 400

    if Role.query.filter_by(name=name).first():
        return {"message": "role already exists"}, 409

    role = Role(
        name=name,
        description=(data.get("description") or "").strip() or None,
    )
    db.session.add(role)
    db.session.commit()

    perms = _resolve_permissions(data)
    if perms:
        role.permissions = perms
        db.session.commit()

    return {"message": "created", "role": _role_payload(role)}, 201


@admin_rbac_bp.put("/rbac/roles/<int:role_id>")
@jwt_required()
@require_permission("RBAC_UPDATE")
def update_role(role_id: int):
    role = Role.query.get_or_404(role_id)
    data = request.get_json() or {}

    if "name" in data:
        name = (data.get("name") or "").strip().upper()
        if not name:
            return {"message": "name cannot be empty"}, 400
        if Role.query.filter(Role.name == name, Role.id != role.id).first():
            return {"message": "role name already exists"}, 409
        role.name = name

    if "description" in data:
        role.description = (data.get("description") or "").strip() or None

    db.session.commit()
    return {"message": "updated", "role": _role_payload(role)}


@admin_rbac_bp.put("/rbac/roles/<int:role_id>/permissions")
@jwt_required()
@require_permission("RBAC_UPDATE")
def replace_role_permissions(role_id: int):
    role = Role.query.get_or_404(role_id)
    data = request.get_json() or {}
    perms = _resolve_permissions(data)
    if perms is None:
        return {"message": "permission_ids or permission_codes must be provided"}, 400

    role.permissions = perms
    db.session.commit()
    return {"message": "updated", "role": _role_payload(role)}


@admin_rbac_bp.delete("/rbac/roles/<int:role_id>")
@jwt_required()
@require_permission("RBAC_UPDATE")
def delete_role(role_id: int):
    role = Role.query.get_or_404(role_id)

    UserRole.query.filter_by(role_id=role.id).delete()
    RolePermission.query.filter_by(role_id=role.id).delete()

    db.session.delete(role)
    db.session.commit()
    return {"message": "deleted"}


def _resolve_permissions(data):
    perm_ids = data.get("permission_ids")
    perm_codes = data.get("permission_codes")

    if perm_ids is None and perm_codes is None:
        return None

    if perm_ids:
        return Permission.query.filter(Permission.id.in_(perm_ids)).all()

    codes = [str(c).strip().upper() for c in (perm_codes or []) if str(c).strip()]
    return Permission.query.filter(Permission.code.in_(codes)).all()
