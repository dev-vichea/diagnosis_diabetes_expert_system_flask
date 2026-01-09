from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Rule, RuleCondition, Symptom
from app.utils.decorators import require_permission

kb_rules_bp = Blueprint("kb_rules", __name__)


# ---------- Rules list ----------
@kb_rules_bp.get("/rules")
@jwt_required()
@require_permission("KB_VIEW")
def list_rules():
    rules = Rule.query.order_by(Rule.priority.desc(), Rule.id.desc()).all()
    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "diagnosis_code": r.diagnosis_code,
                "risk_level": r.risk_level,
                "priority": r.priority,
                "is_active": bool(r.is_active),
                "explanation_text": getattr(r, "explanation_text", None),
                "conditions_count": len(r.conditions),
            }
            for r in rules
        ]
    }


# ---------- Get one rule (for edit screen) ----------
@kb_rules_bp.get("/rules/<int:rule_id>")
@jwt_required()
@require_permission("KB_VIEW")
def get_rule(rule_id: int):
    r = Rule.query.get_or_404(rule_id)

    # load symptoms for labels
    symptom_ids = [c.symptom_id for c in r.conditions]
    smap = {s.id: s for s in Symptom.query.filter(Symptom.id.in_(symptom_ids)).all()} if symptom_ids else {}

    return {
        "id": r.id,
        "name": r.name,
        "diagnosis_code": r.diagnosis_code,
        "risk_level": r.risk_level,
        "priority": r.priority,
        "is_active": bool(r.is_active),
        "explanation_text": getattr(r, "explanation_text", None),
        "conditions": [
            {
                "id": c.id,
                "symptom_id": c.symptom_id,
                "symptom_code": (smap.get(c.symptom_id).code if smap.get(c.symptom_id) else None),
                "expected_value": bool(c.expected_value),
                "reason_text": getattr(c, "reason_text", None),
            }
            for c in r.conditions
        ],
    }


# ---------- Create rule ----------
@kb_rules_bp.post("/rules")
@jwt_required()
@require_permission("KB_CREATE")
def create_rule():
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    diagnosis_code = (data.get("diagnosis_code") or "").strip().upper()
    risk_level = (data.get("risk_level") or "").strip().upper()
    priority = int(data.get("priority") or 0)
    is_active = bool(data.get("is_active", True))
    explanation_text = (data.get("explanation_text") or "").strip() or None

    if not name or not diagnosis_code or not risk_level:
        return {"message": "name, diagnosis_code, risk_level are required"}, 400

    r = Rule(
        name=name,
        diagnosis_code=diagnosis_code,
        risk_level=risk_level,
        priority=priority,
        is_active=is_active,
    )
    if hasattr(r, "explanation_text"):
        r.explanation_text = explanation_text

    db.session.add(r)
    db.session.commit()

    return {"message": "created", "rule_id": r.id}, 201


# ---------- Update rule ----------
@kb_rules_bp.put("/rules/<int:rule_id>")
@jwt_required()
@require_permission("KB_UPDATE")
def update_rule(rule_id: int):
    r = Rule.query.get_or_404(rule_id)
    data = request.get_json() or {}

    if "name" in data:
        r.name = (data.get("name") or "").strip()

    if "diagnosis_code" in data:
        r.diagnosis_code = (data.get("diagnosis_code") or "").strip().upper()

    if "risk_level" in data:
        r.risk_level = (data.get("risk_level") or "").strip().upper()

    if "priority" in data:
        r.priority = int(data.get("priority") or 0)

    if "is_active" in data:
        r.is_active = bool(data.get("is_active"))

    if "explanation_text" in data and hasattr(r, "explanation_text"):
        r.explanation_text = (data.get("explanation_text") or "").strip() or None

    db.session.commit()
    return {"message": "updated"}


# ---------- Delete rule ----------
@kb_rules_bp.delete("/rules/<int:rule_id>")
@jwt_required()
@require_permission("KB_DELETE")
def delete_rule(rule_id: int):
    r = Rule.query.get_or_404(rule_id)

    # delete conditions first (avoid FK errors)
    RuleCondition.query.filter_by(rule_id=r.id).delete()
    db.session.delete(r)
    db.session.commit()
    return {"message": "deleted"}


# ---------- Replace all conditions (perfect for UI builder Save Changes) ----------
@kb_rules_bp.put("/rules/<int:rule_id>/conditions")
@jwt_required()
@require_permission("KB_UPDATE")
def replace_conditions(rule_id: int):
    """
    Body:
    {
      "conditions": [
        {"symptom_id": 1, "expected_value": true, "reason_text": "optional"},
        {"symptom_id": 2, "expected_value": true}
      ]
    }
    """
    r = Rule.query.get_or_404(rule_id)
    data = request.get_json() or {}
    conditions = data.get("conditions") or []

    if not isinstance(conditions, list) or len(conditions) == 0:
        return {"message": "conditions must be a non-empty list"}, 400

    # validate symptom ids exist
    symptom_ids = [c.get("symptom_id") for c in conditions]
    if any(sid is None for sid in symptom_ids):
        return {"message": "each condition requires symptom_id"}, 400

    exists = Symptom.query.filter(Symptom.id.in_(symptom_ids), Symptom.is_active == True).all()
    if len(exists) != len(set(symptom_ids)):
        return {"message": "one or more symptom_id invalid/inactive"}, 400

    # delete old
    RuleCondition.query.filter_by(rule_id=r.id).delete()
    db.session.commit()

    # insert new
    for c in conditions:
        expected = c.get("expected_value", True)
        reason_text = (c.get("reason_text") or "").strip() or None

        rc = RuleCondition(
            rule_id=r.id,
            symptom_id=int(c["symptom_id"]),
            expected_value=bool(expected),
        )
        if hasattr(rc, "reason_text"):
            rc.reason_text = reason_text

        db.session.add(rc)

    db.session.commit()
    return {"message": "conditions replaced"}
