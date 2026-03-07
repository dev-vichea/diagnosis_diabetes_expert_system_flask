from typing import Any, Dict, List, Tuple

from flask import jsonify, render_template, request

from app.routes.web import web_bp
from app.routes.web.utils import require_login, require_permissions, wants_json
from app.models import Rule, Symptom
from app.inference.engine_core import Condition, RulePayload, run_inference
from app.inference.rule_eval import evaluate_rule_status
from app.services.admin_rule_service import (
    create_rule_from_payload,
    get_rule_payload,
    list_rules_payloads,
    replace_rule_conditions,
    update_rule_from_payload,
)
from app.services.admin_disease_service import list_diseases_payloads
from app.services.admin_symptom_service import list_symptoms_payloads


def _format_expected_value(detail: Dict[str, Any]) -> str:
    expected = detail.get("expected", detail.get("value"))
    operator = (detail.get("operator") or "==").upper()
    if operator in {"PRESENT", "ABSENT"}:
        return operator.title()
    if isinstance(expected, bool):
        return "Yes" if expected else "No"
    if expected is None:
        return "-"
    return str(expected)


def _format_actual_value(detail: Dict[str, Any]) -> str:
    actual = detail.get("actual")
    if actual is None:
        return "Not provided"
    if isinstance(actual, bool):
        return "Yes" if actual else "No"
    return str(actual)


def _condition_label(detail: Dict[str, Any], symptom_map: Dict[int, Symptom]) -> str:
    sid = detail.get("symptom_id")
    symptom = symptom_map.get(sid)
    if symptom:
        return symptom.name or symptom.question_text or symptom.code
    return detail.get("symptom_code") or f"Symptom {sid}"


def _build_preview_payload(rule: Rule) -> Tuple[RulePayload, Dict[int, Symptom]]:
    symptom_ids = [condition.symptom_id for condition in rule.conditions]
    symptom_map = {
        symptom.id: symptom
        for symptom in Symptom.query.filter(Symptom.id.in_(symptom_ids)).all()
    } if symptom_ids else {}

    disease = rule.disease
    confidence = float(rule.base_confidence) if rule.base_confidence is not None else None
    if not disease or confidence is None:
        best_action = None
        best_score = -1.0
        for action in rule.actions:
            raw = float(action.confidence) if action.confidence is not None else 0.0
            score = raw / 100.0 if raw > 1 else raw
            if score > best_score:
                best_score = score
                best_action = action
        if not disease and best_action and best_action.disease:
            disease = best_action.disease
        if confidence is None and best_action and best_action.confidence is not None:
            raw = float(best_action.confidence)
            confidence = raw / 100.0 if raw > 1 else raw
    conditions: List[Condition] = []
    for condition in rule.conditions:
        symptom = symptom_map.get(condition.symptom_id)
        conditions.append(
            Condition(
                symptom_id=condition.symptom_id,
                symptom_code=(symptom.code if symptom else None),
                finding_code=(condition.finding_code or (symptom.code if symptom else None)),
                operator=condition.operator or "==",
                value=condition.value,
                values=(condition.values_json if condition.values_json is not None else condition.value),
                is_required=bool(condition.is_required),
                weight=float(condition.weight or 0),
                score_points=int(condition.score_points or 0),
                negate=bool(condition.negate),
                input_type=(symptom.input_type if symptom else None),
            )
        )

    disease_risk = "LOW"
    if disease:
        severity_level = (disease.severity_level or "LOW").upper()
        if severity_level == "HIGH":
            disease_risk = "HIGH"
        elif severity_level == "MEDIUM":
            disease_risk = "MEDIUM"

    payload = RulePayload(
        id=rule.id,
        name=rule.title,
        diagnosis_code=(disease.code if disease else rule.rule_code),
        risk_level=((rule.risk_level or disease_risk or "UNKNOWN")),
        rule_type=(rule.rule_type or "screening"),
        stop_on_match=bool(rule.stop_on_match),
        confidence_cap_if_unconfirmed=(
            float(rule.confidence_cap_if_unconfirmed)
            if rule.confidence_cap_if_unconfirmed is not None
            else None
        ),
        confidence_bonus_max=(
            float(rule.confidence_bonus_max)
            if rule.confidence_bonus_max is not None
            else None
        ),
        min_required_matches=(
            int(rule.min_required_matches)
            if rule.min_required_matches is not None
            else None
        ),
        priority=rule.priority or 0,
        confidence=confidence,
        conditions=conditions,
    )
    return payload, symptom_map


def _coerce_preview_fact(symptom: Symptom, raw: Any) -> Tuple[bool, Any]:
    input_type = (symptom.input_type or "BOOLEAN").upper()
    if raw is None:
        return False, None
    text = str(raw).strip()
    if text == "":
        return False, None

    if input_type == "BOOLEAN":
        lowered = text.lower()
        if lowered in {"unknown", "dont_know", "don't_know", "not_sure"}:
            return False, None
        if lowered in {"1", "true", "yes", "y"}:
            return True, True
        if lowered in {"0", "false", "no", "n"}:
            return True, False
        return False, None

    if input_type == "NUMBER":
        try:
            return True, float(text)
        except (TypeError, ValueError):
            return False, None

    if input_type in {"TEXT", "SINGLE"}:
        return True, text

    return False, None


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
        diseases=list_diseases_payloads(),
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
        diseases=list_diseases_payloads(),
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


@web_bp.route("/knowledge/rules/<int:rule_id>/preview", methods=["GET", "POST"])
def kb_rules_preview(rule_id: int):
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("KB_VIEW")
    if guard:
        return guard

    rule = Rule.query.get_or_404(rule_id)
    payload = get_rule_payload(rule)
    preview_payload, symptom_map = _build_preview_payload(rule)

    submitted_values: Dict[int, str] = {}
    preview_result = None
    errors: List[str] = []

    # Build fields from this rule's conditions only (temporary evaluation).
    preview_inputs = []
    for condition in payload.get("conditions") or []:
        symptom_id = condition.get("symptom_id")
        symptom = symptom_map.get(symptom_id)
        if not symptom:
            continue
        preview_inputs.append(
            {
                "symptom": symptom,
                "condition": condition,
            }
        )

    preview_inputs.sort(
        key=lambda item: (
            0 if item["condition"].get("is_required", True) else 1,
            item["symptom"].priority_order or 0,
            item["symptom"].id,
        )
    )

    if request.method == "POST":
        facts: Dict[str, Any] = {}
        for item in preview_inputs:
            symptom = item["symptom"]
            field_key = f"symptom_{symptom.id}"
            raw_value = request.form.get(field_key)
            submitted_values[symptom.id] = raw_value or ""

            parsed_ok, parsed_value = _coerce_preview_fact(symptom, raw_value)
            if not parsed_ok and str(raw_value or "").strip() != "":
                errors.append(f"Invalid value for {symptom.name or symptom.code}.")
                continue
            if parsed_ok and symptom.code:
                facts[symptom.code] = parsed_value

        if not errors:
            inference = run_inference(facts, [preview_payload])
            evaluated_rows = inference.get("evaluated") or []
            row = evaluated_rows[0] if evaluated_rows else {}
            eval_result = evaluate_rule_status(preview_payload, facts)

            matched_items = row.get("matched_conditions") or eval_result.get("matched") or []
            missing_items = row.get("missing_conditions") or eval_result.get("missing") or []
            contradiction_items = eval_result.get("contradictions") or []

            required_total = float(row.get("required_total_weight") or 0)
            required_matched = float(row.get("required_matched_weight") or 0)
            if required_total > 0:
                required_coverage = required_matched / required_total
            else:
                total_count = float(row.get("total_conditions") or 0)
                required_coverage = (float(row.get("matched_count") or 0) / total_count) if total_count else 0.0

            base_conf = float(row.get("confidence") or 0.5)
            contextual_conf = max(0.0, min(1.0, (base_conf * 0.4) + (required_coverage * 0.6)))

            def _detail_rows(items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
                out = []
                for detail in items:
                    out.append(
                        {
                            "label": _condition_label(detail, symptom_map),
                            "operator": (detail.get("operator") or "==").upper(),
                            "expected": _format_expected_value(detail),
                            "actual": _format_actual_value(detail),
                        }
                    )
                return out

            missing_labs = []
            for detail in missing_items:
                sid = detail.get("symptom_id")
                symptom = symptom_map.get(sid)
                if not symptom:
                    continue
                category = (symptom.category or "").strip().lower().replace("-", "_")
                if category in {"labs", "lab", "laboratory", "has_lab", "hab_lab", "gate"}:
                    missing_labs.append(symptom.question_text or symptom.name or symptom.code)
            rule_type = (payload.get("rule_type") or "screening").lower()

            preview_result = {
                "status": row.get("status") or "IMPOSSIBLE",
                "diagnosis_code": row.get("diagnosis_code") or payload.get("diagnosis_code") or payload.get("rule_code"),
                "diagnosis_name": payload.get("diagnosis") or payload.get("title"),
                "rule_type": rule_type,
                "risk_level": row.get("risk_level") or payload.get("risk_level"),
                "matched_count": int(row.get("matched_count") or 0),
                "total_conditions": int(row.get("total_conditions") or 0),
                "score": float(row.get("score") or 0.0),
                "required_coverage_pct": round(required_coverage * 100.0, 1),
                "confidence_pct": round(contextual_conf * 100.0, 1),
                "matched": _detail_rows(matched_items),
                "missing": _detail_rows(missing_items),
                "contradictions": _detail_rows(contradiction_items),
                "recommended_tests": missing_labs if rule_type == "screening" else [],
            }

    return render_template(
        "knowledge/rule_preview.html",
        rule=payload,
        preview_inputs=preview_inputs,
        submitted_values=submitted_values,
        preview_result=preview_result,
        errors=errors,
    )


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
