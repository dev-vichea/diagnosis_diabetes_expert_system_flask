from flask import jsonify, render_template, request

from app.routes.web import web_bp
from app.routes.web.utils import require_login, require_permissions, wants_json
from app.models import Rule
from app.services.admin_rule_service import (
    create_rule_from_payload,
    get_rule_payload,
    list_rules_payloads,
    replace_rule_conditions,
    update_rule_from_payload,
)
from app.services.admin_symptom_service import list_symptoms_payloads


@web_bp.get("/knowledge/rules")
def kb_rules():
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("KB_VIEW")
    if guard:
        return guard
    return render_template(
        "knowledge/rules.html",
        rules=list_rules_payloads(),
        symptoms=list_symptoms_payloads(),
    )


@web_bp.get("/knowledge/rules/create")
def kb_rules_create():
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("KB_CREATE")
    if guard:
        return guard
    return render_template(
        "knowledge/rules_create.html",
        symptoms=list_symptoms_payloads(),
    )


@web_bp.get("/knowledge/rules/data")
def kb_rules_data():
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("KB_VIEW")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "KB_VIEW"}), 403
        return guard
    return jsonify({"items": list_rules_payloads()})


@web_bp.get("/knowledge/rules/<int:rule_id>")
def kb_rules_detail(rule_id: int):
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("KB_VIEW")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "KB_VIEW"}), 403
        return guard
    rule = Rule.query.get_or_404(rule_id)
    return jsonify(get_rule_payload(rule))


@web_bp.post("/knowledge/rules")
def kb_rules_create_submit():
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("KB_CREATE")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "KB_CREATE"}), 403
        return guard

    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()

    payload, error, status = create_rule_from_payload(data)
    if error:
        return jsonify({"message": error}), status
    return jsonify({"message": "created", "rule": payload}), status


@web_bp.put("/knowledge/rules/<int:rule_id>")
def kb_rules_update_submit(rule_id: int):
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("KB_UPDATE")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "KB_UPDATE"}), 403
        return guard

    rule = Rule.query.get_or_404(rule_id)
    data = request.get_json(silent=True) or {}
    payload, error, status = update_rule_from_payload(rule, data)
    if error:
        return jsonify({"message": error}), status
    return jsonify({"message": "updated", "rule": payload}), status


@web_bp.put("/knowledge/rules/<int:rule_id>/conditions")
def kb_rules_replace_conditions(rule_id: int):
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("KB_UPDATE")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "KB_UPDATE"}), 403
        return guard

    rule = Rule.query.get_or_404(rule_id)
    data = request.get_json(silent=True) or {}
    conditions = data.get("conditions") or []

    _, error, status = replace_rule_conditions(rule, conditions)
    if error:
        return jsonify({"message": error}), status
    return jsonify({"message": "conditions replaced"})


@web_bp.delete("/knowledge/rules/<int:rule_id>")
def kb_rules_delete_submit(rule_id: int):
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("KB_DELETE")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "KB_DELETE"}), 403
        return guard

    rule = Rule.query.get_or_404(rule_id)
    from app.extensions import db
    from app.models import RuleCondition
    RuleCondition.query.filter_by(rule_id=rule.id).delete()
    db.session.delete(rule)
    db.session.commit()
    return jsonify({"message": "deleted"})
