from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Symptom
from app.utils.decorators import require_permission

kb_bp = Blueprint("kb", __name__)

# -------- Symptoms --------

@kb_bp.get("/symptoms")
@jwt_required()
@require_permission("KB_VIEW")
def list_symptoms():
    rows = Symptom.query.order_by(Symptom.priority_order.asc(), Symptom.id.asc()).all()
    return {
        "items": [
            {
                "id": s.id,
                "code": s.code,
                "question_text": s.question_text,
                "category": s.category,
                "priority_order": s.priority_order,
                "is_active": bool(s.is_active),
            }
            for s in rows
        ]
    }


@kb_bp.post("/symptoms")
@jwt_required()
@require_permission("KB_CREATE")
def create_symptom():
    data = request.get_json() or {}

    code = (data.get("code") or "").strip()
    question_text = (data.get("question_text") or "").strip()
    category = (data.get("category") or "").strip() or None
    priority_order = int(data.get("priority_order") or 0)
    is_active = bool(data.get("is_active", True))

    if not code or not question_text:
        return {"message": "code and question_text are required"}, 400

    if Symptom.query.filter_by(code=code).first():
        return {"message": "symptom code already exists"}, 409

    s = Symptom(
        code=code,
        question_text=question_text,
        category=category,
        priority_order=priority_order,
        is_active=is_active,
    )
    db.session.add(s)
    db.session.commit()

    return {"message": "created", "id": s.id}, 201


@kb_bp.put("/symptoms/<int:symptom_id>")
@jwt_required()
@require_permission("KB_UPDATE")
def update_symptom(symptom_id: int):
    s = Symptom.query.get_or_404(symptom_id)
    data = request.get_json() or {}

    if "code" in data:
        new_code = (data.get("code") or "").strip()
        if not new_code:
            return {"message": "code cannot be empty"}, 400
        # ensure unique
        exists = Symptom.query.filter(Symptom.code == new_code, Symptom.id != s.id).first()
        if exists:
            return {"message": "code already used"}, 409
        s.code = new_code

    if "question_text" in data:
        qt = (data.get("question_text") or "").strip()
        if not qt:
            return {"message": "question_text cannot be empty"}, 400
        s.question_text = qt

    if "category" in data:
        s.category = (data.get("category") or "").strip() or None

    if "priority_order" in data:
        s.priority_order = int(data.get("priority_order") or 0)

    if "is_active" in data:
        s.is_active = bool(data.get("is_active"))

    db.session.commit()
    return {"message": "updated"}


@kb_bp.delete("/symptoms/<int:symptom_id>")
@jwt_required()
@require_permission("KB_DELETE")
def delete_symptom(symptom_id: int):
    s = Symptom.query.get_or_404(symptom_id)
    db.session.delete(s)
    db.session.commit()
    return {"message": "deleted"}
