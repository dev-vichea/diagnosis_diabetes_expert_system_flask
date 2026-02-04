from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.models import Rule
from app.utils.decorators import require_permission
from app.services.admin_rule_service import (
    create_rule_from_payload,
    get_rule_payload,
    list_rules_payloads,
    replace_rule_conditions,
    update_rule_from_payload,
)

kb_rules_bp = Blueprint("kb_rules", __name__)


# ---------- Rules list ----------
@kb_rules_bp.get("/rules")
@jwt_required()
@require_permission("KB_VIEW")
def list_rules():
    return {"items": list_rules_payloads()}


# ---------- Get one rule (for edit screen) ----------
@kb_rules_bp.get("/rules/<int:rule_id>")
@jwt_required()
@require_permission("KB_VIEW")
def get_rule(rule_id: int):
    r = Rule.query.get_or_404(rule_id)
    return get_rule_payload(r)


# ---------- Create rule ----------
@kb_rules_bp.post("/rules")
@jwt_required()
@require_permission("KB_CREATE")
def create_rule():
    data = request.get_json() or {}
    payload, error, status = create_rule_from_payload(data)
    if error:
        return {"message": error}, status
    return {"message": "created", "rule": payload}, status


# ---------- Update rule ----------
@kb_rules_bp.put("/rules/<int:rule_id>")
@jwt_required()
@require_permission("KB_UPDATE")
def update_rule(rule_id: int):
    r = Rule.query.get_or_404(rule_id)
    data = request.get_json() or {}
    payload, error, status = update_rule_from_payload(r, data)
    if error:
        return {"message": error}, status
    return {"message": "updated", "rule": payload}, status


# ---------- Delete rule ----------
@kb_rules_bp.delete("/rules/<int:rule_id>")
@jwt_required()
@require_permission("KB_DELETE")
def delete_rule(rule_id: int):
    r = Rule.query.get_or_404(rule_id)

    from app.extensions import db
    from app.models import RuleCondition
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
        {"symptom_id": 1, "operator": "==", "value": true},
        {"symptom_id": 2, "operator": ">=", "value": 140, "logic_group": "A"}
      ]
    }
    """
    r = Rule.query.get_or_404(rule_id)
    data = request.get_json() or {}
    conditions = data.get("conditions") or []

    _, error, status = replace_rule_conditions(r, conditions)
    if error:
        return {"message": error}, status
    return {"message": "conditions replaced"}
