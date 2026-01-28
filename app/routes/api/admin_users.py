from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.models import User
from app.utils.decorators import require_permission
from app.services.admin_user_service import (
    create_user_from_payload,
    list_users_payloads,
    update_user_from_payload,
)

admin_users_bp = Blueprint("admin_users", __name__)


@admin_users_bp.post("/users")
@jwt_required()
@require_permission("USER_CREATE")
def admin_create_user():
    """
    Admin creates a user with a specific role: USER / KB_DOCTOR / ADMIN
    """
    data = request.get_json() or {}

    payload, error, status = create_user_from_payload(data)
    if error:
        return {"message": error}, status

    return {
        "message": "user created",
        "user": payload,
    }, status


@admin_users_bp.get("/users")
@jwt_required()
@require_permission("USER_VIEW")
def admin_list_users():
    return {"items": list_users_payloads()}


@admin_users_bp.put("/users/<int:user_id>")
@jwt_required()
@require_permission("USER_UPDATE")
def admin_update_user(user_id: int):
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    payload, error, status = update_user_from_payload(user, data)
    if error:
        return {"message": error}, status
    return {"message": "updated", "user": payload}, status
