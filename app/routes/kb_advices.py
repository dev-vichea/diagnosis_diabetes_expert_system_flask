from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Advice
from app.utils.decorators import require_permission

kb_advices_bp = Blueprint("kb_advices", __name__)


@kb_advices_bp.get("/advices")
@jwt_required()
@require_permission("KB_VIEW")
def list_advices():
    rows = (
        Advice.query
        .order_by(Advice.diagnosis_code.asc(), Advice.risk_level.asc(), Advice.id.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": a.id,
                "diagnosis_code": a.diagnosis_code,
                "risk_level": a.risk_level,
                "title": a.title,
                "severity": a.severity,
                "is_active": bool(a.is_active),
            }
            for a in rows
        ]
    }


@kb_advices_bp.get("/advices/<int:advice_id>")
@jwt_required()
@require_permission("KB_VIEW")
def get_advice(advice_id: int):
    a = Advice.query.get_or_404(advice_id)
    return {
        "id": a.id,
        "diagnosis_code": a.diagnosis_code,
        "risk_level": a.risk_level,
        "title": a.title,
        "content": a.content,
        "severity": a.severity,
        "is_active": bool(a.is_active),
    }


@kb_advices_bp.post("/advices")
@jwt_required()
@require_permission("KB_CREATE")
def create_advice():
    """
    Body:
    {
      "diagnosis_code": "DIABETES_RISK",
      "risk_level": "HIGH",
      "title": "Urgent check-up recommended",
      "content": "....",
      "severity": "ALERT",
      "is_active": true
    }
    """
    data = request.get_json() or {}

    diagnosis_code = (data.get("diagnosis_code") or "").strip().upper()
    risk_level = (data.get("risk_level") or "").strip().upper()
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    severity = (data.get("severity") or "INFO").strip().upper()
    is_active = bool(data.get("is_active", True))

    if not diagnosis_code or not risk_level or not title or not content:
        return {"message": "diagnosis_code, risk_level, title, content are required"}, 400

    # enforce one active advice per (diagnosis_code, risk_level) (optional but recommended)
    exists = Advice.query.filter_by(
        diagnosis_code=diagnosis_code,
        risk_level=risk_level,
        is_active=True
    ).first()
    if exists:
        return {
            "message": "active advice already exists for this diagnosis_code + risk_level",
            "existing_advice_id": exists.id
        }, 409

    a = Advice(
        diagnosis_code=diagnosis_code,
        risk_level=risk_level,
        title=title,
        content=content,
        severity=severity,
        is_active=is_active,
    )
    db.session.add(a)
    db.session.commit()
    return {"message": "created", "advice_id": a.id}, 201


@kb_advices_bp.put("/advices/<int:advice_id>")
@jwt_required()
@require_permission("KB_UPDATE")
def update_advice(advice_id: int):
    a = Advice.query.get_or_404(advice_id)
    data = request.get_json() or {}

    if "diagnosis_code" in data:
        a.diagnosis_code = (data.get("diagnosis_code") or "").strip().upper()

    if "risk_level" in data:
        a.risk_level = (data.get("risk_level") or "").strip().upper()

    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            return {"message": "title cannot be empty"}, 400
        a.title = title

    if "content" in data:
        content = (data.get("content") or "").strip()
        if not content:
            return {"message": "content cannot be empty"}, 400
        a.content = content

    if "severity" in data:
        a.severity = (data.get("severity") or "INFO").strip().upper()

    if "is_active" in data:
        a.is_active = bool(data.get("is_active"))

    # optional: prevent two active advices per diagnosis+risk
    if a.is_active:
        dup = Advice.query.filter(
            Advice.id != a.id,
            Advice.diagnosis_code == a.diagnosis_code,
            Advice.risk_level == a.risk_level,
            Advice.is_active == True,
        ).first()
        if dup:
            return {
                "message": "another active advice already exists for this diagnosis_code + risk_level",
                "existing_advice_id": dup.id
            }, 409

    db.session.commit()
    return {"message": "updated"}


@kb_advices_bp.delete("/advices/<int:advice_id>")
@jwt_required()
@require_permission("KB_DELETE")
def delete_advice(advice_id: int):
    a = Advice.query.get_or_404(advice_id)
    db.session.delete(a)
    db.session.commit()
    return {"message": "deleted"}
