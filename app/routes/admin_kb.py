from flask import Blueprint, jsonify

admin_kb_bp = Blueprint("admin_kb", __name__)


@admin_kb_bp.get("/ping")
def ping():
	return jsonify({"status": "admin_kb ok"})

