from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity
from app.services.rbac_service import get_user_permission_codes

def require_permission(permission_code: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            identity = get_jwt_identity()
            if not identity:
                return jsonify({"message": "Unauthorized"}), 401

            user_id = int(identity)
            perms = get_user_permission_codes(user_id)

            if permission_code not in perms:
                return jsonify({"message": "Forbidden", "missing_permission": permission_code}), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator
