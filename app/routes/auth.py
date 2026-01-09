from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token

from app.models import User
from app.utils.security import hash_password, verify_password

from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.rbac_service import get_user_permission_codes

from app.extensions import db
from app.models import Role, UserRole


auth_bp = Blueprint("auth", __name__)

@auth_bp.get("/me")
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    perms = sorted(list(get_user_permission_codes(user_id)))
    return {"user_id": user_id, "permissions": perms}


@auth_bp.get("/ping")
def ping():
	return jsonify({"status": "auth ok"})


@auth_bp.post("/login")
def login():
	data = request.get_json() or {}
	email = (data.get("email") or "").strip().lower()
	password = data.get("password") or ""

	if not email or not password:
		return {"message": "email and password are required"}, 400

	user = User.query.filter_by(email=email).first()
	if not user or user.status != "ACTIVE":
		return {"message": "Invalid credentials"}, 401
	if not verify_password(password, user.password_hash):
		return {"message": "Invalid credentials"}, 401

	access_token = create_access_token(identity=str(user.id))
	return jsonify(
		{
			"access_token": access_token,
			"user_id": user.id,
			"email": user.email,
		}
	)

@auth_bp.post("/register")
def register():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name or not email or not password:
        return {"message": "name, email, password are required"}, 400

    if User.query.filter_by(email=email).first():
        return {"message": "email already exists"}, 409

    user = User(name=name, email=email, password_hash=hash_password(password), status="ACTIVE")
    db.session.add(user)
    db.session.commit()

    # ✅ always USER
    user_role = Role.query.filter_by(name="USER").first()
    if user_role:
        db.session.add(UserRole(user_id=user.id, role_id=user_role.id))
        db.session.commit()

    token = create_access_token(identity=str(user.id))
    return {"access_token": token, "user": {"id": user.id, "name": user.name, "email": user.email}}, 201

