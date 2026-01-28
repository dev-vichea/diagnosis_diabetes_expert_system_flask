from flask import jsonify, render_template, request
from app.models import User

from app.routes.web import web_bp
from app.routes.web.utils import require_login, require_permissions, wants_json
from app.services.admin_user_service import (
    create_user_from_payload,
    list_users_payloads,
    update_user_from_payload,
)


@web_bp.get("/admin/users")
def admin_users():
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("USER_VIEW")
    if guard:
        return guard
    return render_template("admin/users.html", users=list_users_payloads())


@web_bp.get("/admin/users/data")
def admin_users_data():
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("USER_VIEW")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "USER_VIEW"}), 403
        return guard
    return jsonify({"items": list_users_payloads()})


@web_bp.post("/admin/users")
def admin_users_create_submit():
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("USER_CREATE")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "USER_CREATE"}), 403
        return guard

    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()

    payload, error, status = create_user_from_payload(data)
    if error:
        return jsonify({"message": error}), status
    return jsonify({"message": "user created", "user": payload}), status


@web_bp.put("/admin/users/<int:user_id>")
def admin_users_update_submit(user_id: int):
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("USER_UPDATE")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "USER_UPDATE"}), 403
        return guard

    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}

    payload, error, status = update_user_from_payload(user, data)
    if error:
        return jsonify({"message": error}), status
    return jsonify({"message": "updated", "user": payload}), status


@web_bp.get("/admin/users/create")
def admin_users_create():
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("USER_CREATE")
    if guard:
        return guard
    return render_template("admin/users_create.html")
