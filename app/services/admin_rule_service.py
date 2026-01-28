import json
from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from app.models import Rule, RuleCondition, Symptom

VALID_OPERATORS = {"==", ">=", "<=", "IN"}

DIAGNOSIS_MAP = {
    "Normal": ("LOW_RISK", "LOW"),
    "Prediabetes": ("MODERATE_RISK", "MODERATE"),
    "Type 2 Diabetes Risk": ("HIGH_RISK_TYPE_2_DIABETES", "HIGH"),
    "High Risk Type 2": ("HIGH_RISK_TYPE_2_DIABETES", "HIGH"),
    "High Risk Type 2 Diabetes": ("HIGH_RISK_TYPE_2_DIABETES", "HIGH"),
    "Very High Type 2 Diabetes Risk": ("HIGH_RISK_TYPE_2_DIABETES", "VERY_HIGH"),
    "Moderate Risk": ("MODERATE_RISK", "MODERATE"),
    "Low Risk": ("LOW_RISK", "LOW"),
    "Monitor": ("MONITOR", "LOW"),
}


def _normalize_diagnosis_payload(data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    diagnosis = (data.get("diagnosis") or "").strip()
    if not diagnosis:
        return None, None, None, "diagnosis is required"

    if "diagnosis_code" in data or "risk_level" in data:
        diagnosis_code = (data.get("diagnosis_code") or "").strip().upper()
        risk_level = (data.get("risk_level") or "").strip().upper()
        if not diagnosis_code or not risk_level:
            return None, None, None, "diagnosis_code and risk_level are required when provided"
        return diagnosis, diagnosis_code, risk_level, None

    mapped = DIAGNOSIS_MAP.get(diagnosis)
    if mapped:
        return diagnosis, mapped[0], mapped[1], None

    diagnosis_code = diagnosis.upper().replace(" ", "_")
    return diagnosis, diagnosis_code, "LOW", None


def _parse_confidence(raw: Any) -> Tuple[Optional[int], Optional[str]]:
    if raw is None or raw == "":
        return None, None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, "confidence must be an integer"
    if value < 0 or value > 100:
        return None, "confidence must be between 0 and 100"
    return value, None


def rule_payload(rule: Rule, include_conditions: bool = False) -> Dict[str, Any]:
    payload = {
        "id": rule.id,
        "rule_code": rule.rule_code,
        "title": rule.title or rule.name,
        "diagnosis": rule.diagnosis or rule.diagnosis_code,
        "priority": rule.priority,
        "confidence": rule.confidence,
        "is_active": bool(rule.is_active),
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        "diagnosis_code": rule.diagnosis_code,
        "risk_level": rule.risk_level,
        "conditions_count": len(rule.conditions),
        "explanation_text": rule.explanation_text,
    }

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
                "logic_group": c.logic_group,
                "expected_value": bool(c.expected_value),
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
    name = (data.get("name") or "").strip()

    diagnosis, diagnosis_code, risk_level, error = _normalize_diagnosis_payload(data)
    if error:
        return None, error, 400

    if not rule_code:
        return None, "rule_code is required", 400

    if Rule.query.filter_by(rule_code=rule_code).first():
        return None, "rule_code already exists", 409

    if not title:
        title = name or rule_code
    if not name:
        name = title

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
        name=name,
        diagnosis=diagnosis,
        diagnosis_code=diagnosis_code,
        risk_level=risk_level,
        priority=priority,
        confidence=confidence,
        is_active=is_active,
        explanation_text=explanation_text,
    )
    db.session.add(rule)
    db.session.commit()

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

    if "title" in data or "name" in data:
        title = (data.get("title") or "").strip()
        name = (data.get("name") or "").strip()
        if title:
            rule.title = title
        if name:
            rule.name = name
        if title and not name:
            rule.name = title

    if "diagnosis" in data or "diagnosis_code" in data or "risk_level" in data:
        diagnosis, diagnosis_code, risk_level, error = _normalize_diagnosis_payload({
            "diagnosis": data.get("diagnosis") or rule.diagnosis,
            "diagnosis_code": data.get("diagnosis_code"),
            "risk_level": data.get("risk_level"),
        })
        if error:
            return None, error, 400
        rule.diagnosis = diagnosis
        rule.diagnosis_code = diagnosis_code
        rule.risk_level = risk_level

    if "priority" in data:
        rule.priority = int(data.get("priority") or 0)

    if "confidence" in data:
        confidence, error = _parse_confidence(data.get("confidence"))
        if error:
            return None, error, 400
        rule.confidence = confidence

    if "is_active" in data:
        rule.is_active = bool(data.get("is_active"))

    if "explanation_text" in data:
        explanation_text = data.get("explanation_text")
        if isinstance(explanation_text, str):
            explanation_text = explanation_text.strip() or None
        rule.explanation_text = explanation_text

    db.session.commit()
    return rule_payload(rule, include_conditions=True), None, 200


def replace_rule_conditions(
    rule: Rule,
    conditions: List[Dict[str, Any]],
) -> Tuple[Optional[List[RuleCondition]], Optional[str], int]:
    if not isinstance(conditions, list) or len(conditions) == 0:
        return None, "conditions must be a non-empty list", 400

    symptom_ids = [c.get("symptom_id") for c in conditions]
    if any(sid is None for sid in symptom_ids):
        return None, "each condition requires symptom_id", 400

    exists = Symptom.query.filter(Symptom.id.in_(symptom_ids), Symptom.is_active == True).all()
    if len(exists) != len(set(symptom_ids)):
        return None, "one or more symptom_id invalid/inactive", 400

    for raw in conditions:
        operator = (raw.get("operator") or "==").strip().upper()
        if operator not in VALID_OPERATORS:
            return None, f"invalid operator: {operator}", 400

    RuleCondition.query.filter_by(rule_id=rule.id).delete()
    db.session.commit()

    created: List[RuleCondition] = []
    for raw in conditions:
        operator = (raw.get("operator") or "==").strip().upper()
        value = raw.get("value")
        if isinstance(value, (list, dict)):
            value = json.dumps(value)
        elif value is not None:
            value = str(value)

        logic_group = (raw.get("logic_group") or "").strip() or None

        expected_value = True
        if operator == "==":
            if isinstance(raw.get("value"), bool):
                expected_value = bool(raw.get("value"))
            elif isinstance(value, str) and value.lower() in ("true", "false"):
                expected_value = value.lower() == "true"

        rc = RuleCondition(
            rule_id=rule.id,
            symptom_id=int(raw["symptom_id"]),
            expected_value=expected_value,
            operator=operator,
            value=value,
            logic_group=logic_group,
        )
        created.append(rc)
        db.session.add(rc)

    db.session.commit()
    return created, None, 200
