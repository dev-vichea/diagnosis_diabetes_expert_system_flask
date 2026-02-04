from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Symptom
from app.utils.decorators import require_permission
from app.services.admin_symptom_service import (
    create_symptom_from_payload,
    list_symptoms_payloads,
    update_symptom_from_payload,
)

kb_bp = Blueprint("kb", __name__)

# -------- Symptoms --------

@kb_bp.get("/symptoms")
@jwt_required()
@require_permission("KB_VIEW")
def list_symptoms():
    return {"items": list_symptoms_payloads()}


@kb_bp.post("/symptoms")
@jwt_required()
@require_permission("KB_CREATE")
def create_symptom():
    data = request.get_json() or {}

    payload, error, status = create_symptom_from_payload(data)
    if error:
        return {"message": error}, status
    return {"message": "created", "symptom": payload}, status


@kb_bp.put("/symptoms/<int:symptom_id>")
@jwt_required()
@require_permission("KB_UPDATE")
def update_symptom(symptom_id: int):
    s = Symptom.query.get_or_404(symptom_id)
    data = request.get_json() or {}
    payload, error, status = update_symptom_from_payload(s, data)
    if error:
        return {"message": error}, status
    return {"message": "updated", "symptom": payload}, status


@kb_bp.delete("/symptoms/<int:symptom_id>")
@jwt_required()
@require_permission("KB_DELETE")
def delete_symptom(symptom_id: int):
    s = Symptom.query.get_or_404(symptom_id)
    db.session.delete(s)
    db.session.commit()
    return {"message": "deleted"}
