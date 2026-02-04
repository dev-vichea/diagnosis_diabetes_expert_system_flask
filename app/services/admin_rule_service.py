import json
from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from app.models import Rule, RuleCondition, RuleAction, Disease, Symptom

VALID_OPERATORS = {"PRESENT", "ABSENT", "==", "!=", ">=", "<=", ">", "<"}

DIAGNOSIS_MAP = {
    "Normal": ("LOW_RISK", "LOW"),
    "Prediabetes": ("MODERATE_RISK", "MEDIUM"),
    "Type 2 Diabetes Risk": ("HIGH_RISK_TYPE_2_DIABETES", "HIGH"),
    "High Risk Type 2": ("HIGH_RISK_TYPE_2_DIABETES", "HIGH"),
    "High Risk Type 2 Diabetes": ("HIGH_RISK_TYPE_2_DIABETES", "HIGH"),
    "Moderate Risk": ("MODERATE_RISK", "MEDIUM"),
    "Low Risk": ("LOW_RISK", "LOW"),
    "Monitor": ("MONITOR", "LOW"),
}


def _normalize_diagnosis_payload(data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    diagnosis = (data.get("diagnosis") or "").strip()
    diagnosis_code = (data.get("diagnosis_code") or "").strip().upper()
    risk_level = (data.get("risk_level") or "").strip().upper()

    if diagnosis_code and risk_level:
        return diagnosis or diagnosis_code, diagnosis_code, risk_level, None
    if diagnosis:
        mapped = DIAGNOSIS_MAP.get(diagnosis)
        if mapped:
            return diagnosis, mapped[0], mapped[1], None
        return diagnosis, diagnosis.upper().replace(" ", "_"), "LOW", None
    return None, None, None, None


def _parse_confidence(raw: Any) -> Tuple[Optional[float], Optional[str]]:
    if raw is None or raw == "":
        return None, None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, "confidence must be a number"
    if value < 0 or value > 100:
        return None, "confidence must be between 0 and 100"
    return value, None


def _severity_from_risk(risk_level: Optional[str]) -> str:
    level = (risk_level or "").upper()
    if level == "HIGH":
        return "DANGER"
    if level == "MEDIUM":
        return "WARN"
    return "INFO"


def _ensure_action(rule: Rule, diagnosis_code: Optional[str], risk_level: Optional[str], confidence: Optional[float], diagnosis_name: Optional[str] = None):
    if not diagnosis_code:
        return
    disease = Disease.query.filter_by(code=diagnosis_code).first()
    if not disease:
        disease = Disease(
            code=diagnosis_code,
            name=diagnosis_name or diagnosis_code,
            urgency=risk_level or "LOW",
            severity=_severity_from_risk(risk_level),
            is_active=True,
        )
        db.session.add(disease)
        db.session.commit()

    action = RuleAction.query.filter_by(rule_id=rule.id, disease_id=disease.id).first()
    conf = confidence / 100.0 if confidence is not None and confidence > 1 else confidence
    if action:
        action.confidence = conf if conf is not None else action.confidence
    else:
        db.session.add(RuleAction(
            rule_id=rule.id,
            disease_id=disease.id,
            confidence=conf if conf is not None else 0.5,
        ))
    db.session.commit()


def rule_payload(rule: Rule, include_conditions: bool = False) -> Dict[str, Any]:
    actions = []
    primary_action = None
    primary_disease = None
    best_confidence = None
    for action in rule.actions:
        disease = action.disease
        confidence_raw = float(action.confidence) if action.confidence is not None else None
        confidence_norm = None
        if confidence_raw is not None:
            confidence_norm = confidence_raw / 100.0 if confidence_raw > 1 else confidence_raw
        actions.append({
            "disease_code": disease.code if disease else None,
            "disease_name": disease.name if disease else None,
            "risk_level": disease.urgency if disease else None,
            "confidence": confidence_raw,
        })
        score = confidence_norm if confidence_norm is not None else -1
        if best_confidence is None or score > best_confidence:
            best_confidence = score
            primary_action = action
            primary_disease = disease

    payload = {
        "id": rule.id,
        "rule_code": rule.rule_code,
        "title": rule.title,
        "priority": rule.priority,
        "is_active": bool(rule.is_active),
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        "conditions_count": len(rule.conditions),
        "explanation_text": rule.explanation_text,
        "actions": actions,
    }

    if primary_action:
        raw_confidence = float(primary_action.confidence) if primary_action.confidence is not None else None
        confidence_pct = None
        if raw_confidence is not None:
            normalized = raw_confidence / 100.0 if raw_confidence > 1 else raw_confidence
            confidence_pct = round(normalized * 100.0, 2)
        payload.update({
            "diagnosis": primary_disease.name if primary_disease and primary_disease.name else (primary_disease.code if primary_disease else None),
            "diagnosis_code": primary_disease.code if primary_disease else None,
            "risk_level": primary_disease.urgency if primary_disease else None,
            "confidence": confidence_pct,
        })

    if include_conditions:
        symptom_ids = [c.symptom_id for c in rule.conditions]
        smap = {s.id: s for s in Symptom.query.filter(Symptom.id.in_(symptom_ids)).all()} if symptom_ids else {}
        payload["conditions"] = [
            {
                "id": c.id,
                "symptom_id": c.symptom_id,
                "symptom_code": (smap.get(c.symptom_id).code if smap.get(c.symptom_id) else None),
                "symptom_name": (smap.get(c.symptom_id).name if smap.get(c.symptom_id) else None),
                "symptom_input_type": (smap.get(c.symptom_id).input_type if smap.get(c.symptom_id) else None),
                "operator": c.operator or "==",
                "value": c.value,
                "is_required": bool(c.is_required),
                "weight": float(c.weight or 0),
            }
            for c in rule.conditions
        ]

    return payload


def list_rules_payloads() -> List[Dict[str, Any]]:
    rules = Rule.query.order_by(Rule.priority.desc(), Rule.id.desc()).all()
    return [rule_payload(rule) for rule in rules]


def get_rule_payload(rule: Rule) -> Dict[str, Any]:
    return rule_payload(rule, include_conditions=True)


def create_rule_from_payload(
    data: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    rule_code = (data.get("rule_code") or "").strip()
    title = (data.get("title") or "").strip()

    if not rule_code:
        return None, "rule_code is required", 400
    if Rule.query.filter_by(rule_code=rule_code).first():
        return None, "rule_code already exists", 409
    if not title:
        title = rule_code

    confidence, error = _parse_confidence(data.get("confidence"))
    if error:
        return None, error, 400

    priority = int(data.get("priority") or 0)
    is_active = bool(data.get("is_active", True))
    explanation_text = data.get("explanation_text")
    if isinstance(explanation_text, str):
        explanation_text = explanation_text.strip() or None

    rule = Rule(
        rule_code=rule_code,
        title=title,
        priority=priority,
        is_active=is_active,
        explanation_text=explanation_text,
    )
    db.session.add(rule)
    db.session.commit()

    diagnosis, diagnosis_code, risk_level, _ = _normalize_diagnosis_payload(data)
    _ensure_action(rule, diagnosis_code, risk_level, confidence, diagnosis_name=diagnosis)

    return rule_payload(rule, include_conditions=True), None, 201


def update_rule_from_payload(
    rule: Rule,
    data: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    if "rule_code" in data:
        rule_code = (data.get("rule_code") or "").strip()
        if not rule_code:
            return None, "rule_code cannot be empty", 400
        if Rule.query.filter(Rule.rule_code == rule_code, Rule.id != rule.id).first():
            return None, "rule_code already exists", 409
        rule.rule_code = rule_code

    if "title" in data:
        title = (data.get("title") or "").strip()
        if title:
            rule.title = title

    if "priority" in data:
        rule.priority = int(data.get("priority") or 0)

    if "is_active" in data:
        rule.is_active = bool(data.get("is_active"))

    if "explanation_text" in data:
        explanation_text = data.get("explanation_text")
        if isinstance(explanation_text, str):
            explanation_text = explanation_text.strip() or None
        rule.explanation_text = explanation_text

    db.session.commit()

    confidence, _ = _parse_confidence(data.get("confidence"))
    diagnosis, diagnosis_code, risk_level, _ = _normalize_diagnosis_payload(data)
    _ensure_action(rule, diagnosis_code, risk_level, confidence, diagnosis_name=diagnosis)

    return rule_payload(rule, include_conditions=True), None, 200


def add_condition(rule: Rule, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    symptom_id = payload.get("symptom_id")
    operator = (payload.get("operator") or "==").upper()
    value = payload.get("value")
    is_required = bool(payload.get("is_required", True))
    weight = float(payload.get("weight") or 1.0)

    if operator not in VALID_OPERATORS:
        return None, "invalid operator", 400
    if symptom_id is None:
        return None, "symptom_id is required", 400

    try:
        symptom_id = int(symptom_id)
    except (TypeError, ValueError):
        return None, "symptom_id must be integer", 400
    if not Symptom.query.get(symptom_id):
        return None, "symptom_id not found", 404

    exists = RuleCondition.query.filter_by(rule_id=rule.id, symptom_id=symptom_id).first()
    if exists:
        return None, "condition already exists", 409

    rc = RuleCondition(
        rule_id=rule.id,
        symptom_id=symptom_id,
        operator=operator,
        value=str(value) if value is not None and operator not in {"PRESENT", "ABSENT"} else None,
        is_required=is_required,
        weight=weight,
    )
    db.session.add(rc)
    db.session.commit()
    return rule_payload(rule, include_conditions=True), None, 201


def delete_condition(rule: Rule, condition_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    cond = RuleCondition.query.filter_by(id=condition_id, rule_id=rule.id).first()
    if not cond:
        return None, "condition not found", 404
    db.session.delete(cond)
    db.session.commit()
    return rule_payload(rule, include_conditions=True), None, 200


def replace_rule_conditions(rule: Rule, conditions: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    RuleCondition.query.filter_by(rule_id=rule.id).delete()
    for payload in conditions:
        symptom_id = payload.get("symptom_id")
        operator = (payload.get("operator") or "==").upper()
        value = payload.get("value")
        is_required = bool(payload.get("is_required", True))
        weight = float(payload.get("weight") or 1.0)

        if operator not in VALID_OPERATORS:
            return None, "invalid operator", 400
        try:
            symptom_id = int(symptom_id)
        except (TypeError, ValueError):
            return None, "symptom_id must be integer", 400
        if not Symptom.query.get(symptom_id):
            return None, "symptom_id not found", 404

        db.session.add(RuleCondition(
            rule_id=rule.id,
            symptom_id=symptom_id,
            operator=operator,
            value=str(value) if value is not None and operator not in {"PRESENT", "ABSENT"} else None,
            is_required=is_required,
            weight=weight,
        ))
    db.session.commit()
    return rule_payload(rule, include_conditions=True), None, 200
