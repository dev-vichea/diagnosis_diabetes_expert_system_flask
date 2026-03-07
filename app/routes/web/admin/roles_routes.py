from flask import jsonify, render_template, request

from app.extensions import db
from app.routes.web import web_bp
from app.routes.web.utils import (
    current_permissions,
    current_roles,
    require_login,
    require_permissions,
    wants_json,
)
from app.services.admin_rbac_service import (
    list_permissions_payloads,
    list_roles_payloads,
    update_role_permissions,
)
from app.models import Role, RolePermission, UserRole


PROTECTED_ROLE_NAMES = {"ADMIN", "USER", "KB_DOCTOR"}


@web_bp.get("/admin/roles")
def admin_roles():
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("RBAC_VIEW")
    if guard:
        return guard
    return render_template("admin/roles.html")


@web_bp.get("/admin/role-permissions")
def admin_role_permissions():
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("RBAC_VIEW")
    if guard:
        return guard
    perms = current_permissions()
    roles = current_roles()
    can_update = "RBAC_UPDATE" in perms or "ADMIN" in roles
    return render_template(
        "admin/role_permissions.html",
        roles=list_roles_payloads(),
        permissions=list_permissions_payloads(),
        can_update=can_update,
    )


@web_bp.get("/admin/role-permissions/data")
def admin_role_permissions_data():
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("RBAC_VIEW")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "RBAC_VIEW"}), 403
        return guard
    return jsonify(
        {
            "roles": list_roles_payloads(),
            "permissions": list_permissions_payloads(),
        }
    )


@web_bp.put("/admin/role-permissions/<int:role_id>")
def admin_role_permissions_update(role_id: int):
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("RBAC_UPDATE")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "RBAC_UPDATE"}), 403
        return guard

    role = Role.query.get_or_404(role_id)
    data = request.get_json(silent=True) or {}
    permission_codes = data.get("permission_codes")

    payload, error, status = update_role_permissions(role, permission_codes)
    if error:
        return jsonify({"message": error}), status
    return jsonify({"message": "updated", "role": payload}), status


@web_bp.post("/admin/role-permissions/roles")
def admin_role_permissions_create():
    guard = require_login()
    if guard:
        return jsonify({"message": "Unauthorized"}), 401
    guard = require_permissions("RBAC_UPDATE")
    if guard:
        return jsonify({"message": "Forbidden", "missing_permission": "RBAC_UPDATE"}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip().upper()
    if not name:
        return jsonify({"message": "name is required"}), 400

    if Role.query.filter_by(name=name).first():
        return jsonify({"message": "role already exists"}), 409

    role = Role(name=name)
    db.session.add(role)
    db.session.commit()

    permission_codes = data.get("permission_codes") or []
    payload, error, status = update_role_permissions(role, permission_codes)
    if error:
        return jsonify({"message": error}), status
    return jsonify({"message": "created", "role": payload}), 201


@web_bp.put("/admin/role-permissions/roles/<int:role_id>")
def admin_role_permissions_role_update(role_id: int):
    guard = require_login()
    if guard:
        return jsonify({"message": "Unauthorized"}), 401
    guard = require_permissions("RBAC_UPDATE")
    if guard:
        return jsonify({"message": "Forbidden", "missing_permission": "RBAC_UPDATE"}), 403

    role = Role.query.get_or_404(role_id)
    data = request.get_json(silent=True) or {}
    raw_name = data.get("name")
    if raw_name is None:
        name = (role.name or "").strip().upper()
    else:
        name = str(raw_name).strip().upper()
        if not name:
            return jsonify({"message": "name is required"}), 400

    if role.name in PROTECTED_ROLE_NAMES and name != role.name:
        return jsonify({"message": f"{role.name} is a protected role and cannot be renamed"}), 403

    if Role.query.filter(Role.name == name, Role.id != role.id).first():
        return jsonify({"message": "role name already exists"}), 409

    role.name = name
    permission_codes = data.get("permission_codes")
    if permission_codes is not None:
        payload, error, status = update_role_permissions(role, permission_codes)
        if error:
            return jsonify({"message": error}), status
        return jsonify({"message": "updated", "role": payload}), 200

    db.session.commit()
    return jsonify(
        {
            "message": "updated",
            "role": {
                "id": role.id,
                "name": role.name,
                "permissions": sorted([perm.code for perm in role.permissions]),
            },
        }
    ), 200


@web_bp.delete("/admin/role-permissions/roles/<int:role_id>")
def admin_role_permissions_role_delete(role_id: int):
    guard = require_login()
    if guard:
        return jsonify({"message": "Unauthorized"}), 401
    guard = require_permissions("RBAC_UPDATE")
    if guard:
        return jsonify({"message": "Forbidden", "missing_permission": "RBAC_UPDATE"}), 403

    role = Role.query.get_or_404(role_id)
    role_name = (role.name or "").upper()
    if role_name in PROTECTED_ROLE_NAMES:
        return jsonify({"message": f"{role_name} is a protected role and cannot be deleted"}), 403

    if role_name in current_roles():
        return jsonify({"message": "Cannot delete a role currently assigned to your active account session"}), 409

    UserRole.query.filter_by(role_id=role.id).delete()
    RolePermission.query.filter_by(role_id=role.id).delete()
    db.session.delete(role)
    db.session.commit()
    return jsonify({"message": "deleted", "role_id": role_id}), 200
