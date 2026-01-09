from functools import wraps
from flask_jwt_extended import get_jwt_identity
from flask import jsonify

from app.models import User


def require_permission(permission_code: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user_id = get_jwt_identity()
            if not user_id:
                return jsonify({"message": "Unauthorized"}), 401

            user = User.query.get(int(user_id))
            if not user:
                return jsonify({"message": "User not found"}), 401

            # Collect permissions from roles
            permissions = {
                perm.code
                for role in user.roles
                for perm in role.permissions
            }

            if permission_code not in permissions:
                return jsonify({"message": "Forbidden"}), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator
