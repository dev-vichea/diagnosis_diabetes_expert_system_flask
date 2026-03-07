from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from app.models import Rule, RuleCondition, RuleAction, Disease, Symptom

VALID_OPERATORS = {"PRESENT", "ABSENT", "==", "!=", ">=", "<=", ">", "<", "EQ", "GTE", "BETWEEN", "IN"}
VALID_RULE_TYPES = {"screening", "diagnostic", "exclusion", "red_flag"}
VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}

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


def _normalize_diagnosis_payload(
    data: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[int], Optional[str]]:
    diagnosis = (data.get("diagnosis") or "").strip()
    diagnosis_code = (data.get("diagnosis_code") or "").strip().upper()
    risk_level = (data.get("risk_level") or "").strip().upper()
    raw_disease_id = data.get("disease_id")
    disease_id: Optional[int] = None

    if raw_disease_id not in (None, ""):
        try:
            disease_id = int(raw_disease_id)
        except (TypeError, ValueError):
            return None, None, None, None, "disease_id must be an integer"
        if disease_id <= 0:
            return None, None, None, None, "disease_id must be a positive integer"

    if risk_level and risk_level not in VALID_RISK_LEVELS:
        return None, None, None, None, "risk_level must be one of: LOW, MEDIUM, HIGH"

    if diagnosis and not diagnosis_code and disease_id is None:
        return None, None, None, None, "Provide disease_id or diagnosis_code when diagnosis name is set."
    if risk_level and not diagnosis_code and disease_id is None:
        return None, None, None, None, "risk_level requires disease_id or diagnosis_code."

    if diagnosis_code and risk_level:
        return diagnosis or diagnosis_code, diagnosis_code, risk_level, disease_id, None
    if diagnosis_code:
        return diagnosis or diagnosis_code, diagnosis_code, "LOW", disease_id, None
    if diagnosis and disease_id is not None:
        return diagnosis, None, risk_level or None, disease_id, None
    if diagnosis:
        mapped = DIAGNOSIS_MAP.get(diagnosis)
        if mapped:
            return diagnosis, mapped[0], mapped[1], disease_id, None
        return diagnosis, diagnosis.upper().replace(" ", "_"), "LOW", disease_id, None
    return None, None, risk_level or None, disease_id, None


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


def _parse_fraction_field(raw: Any, field_name: str) -> Tuple[Optional[float], Optional[str]]:
    if raw is None or raw == "":
        return None, None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, f"{field_name} must be a number"
    if value < 0 or value > 100:
        return None, f"{field_name} must be between 0 and 100 (or 0.0 to 1.0)"
    normalized = value / 100.0 if value > 1.0 else value
    return max(0.0, min(1.0, normalized)), None


def _parse_non_negative_int(raw: Any, field_name: str) -> Tuple[Optional[int], Optional[str]]:
    if raw is None or raw == "":
        return None, None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, f"{field_name} must be an integer"
    if value < 0:
        return None, f"{field_name} must be >= 0"
    return value, None


def _coerce_bool(raw: Any, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in {"1", "true", "yes", "y", "on"}:
            return True
        if value in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _confidence_to_fraction(confidence: Optional[float]) -> Optional[float]:
    if confidence is None:
        return None
    conf = float(confidence)
    if conf > 1:
        conf = conf / 100.0
    return max(0.0, min(1.0, conf))


def _normalize_rule_type(raw: Any, fallback: str = "screening") -> Tuple[Optional[str], Optional[str]]:
    if raw is None:
        return fallback, None
    text = str(raw).strip().lower()
    if not text:
        return fallback, None
    if text not in VALID_RULE_TYPES:
        return None, "rule_type must be one of: screening, diagnostic, exclusion, red_flag"
    return text, None


def _enforce_screening_labs_optional(
    rule_type: str,
    symptom: Optional[Symptom],
    is_required: bool,
) -> bool:
    if (
        (rule_type or "screening").strip().lower() == "screening"
        and symptom
        and (symptom.code or "").strip().lower() == "has_labs"
    ):
        return False
    return is_required


def _normalize_screening_rule_conditions(rule: Rule) -> None:
    if (rule.rule_type or "screening").strip().lower() != "screening":
        return
    lab_symptom = Symptom.query.filter_by(code="has_labs").first()
    if not lab_symptom:
        return
    RuleCondition.query.filter_by(
        rule_id=rule.id,
        symptom_id=lab_symptom.id,
        is_required=True,
    ).update({"is_required": False})


def _generate_rule_code(rule_type: str) -> str:
    normalized_type = (rule_type or "screening").strip().lower()
    if normalized_type == "diagnostic":
        prefix = "R_DGN"
    elif normalized_type == "exclusion":
        prefix = "R_EXC"
    elif normalized_type == "red_flag":
        prefix = "R_RED"
    else:
        prefix = "R_SCR"

    max_suffix = 0
    rows = (
        Rule.query
        .with_entities(Rule.rule_code)
        .filter(Rule.rule_code.like(f"{prefix}_%"))
        .all()
    )
    for (code,) in rows:
        if not code:
            continue
        text = str(code).strip().upper()
        if not text.startswith(f"{prefix}_"):
            continue
        suffix = text.rsplit("_", 1)[-1]
        if suffix.isdigit():
            max_suffix = max(max_suffix, int(suffix))

    next_suffix = max_suffix + 1
    for _ in range(10000):
        candidate = f"{prefix}_{next_suffix:03d}"
        if not Rule.query.filter_by(rule_code=candidate).first():
            return candidate
        next_suffix += 1

    return f"{prefix}_{next_suffix}"


def _risk_from_disease(disease: Optional[Disease]) -> str:
    if not disease:
        return "LOW"
    severity_level = (disease.severity_level or "LOW").upper()
    if severity_level == "HIGH":
        return "HIGH"
    if severity_level == "MEDIUM":
        return "MEDIUM"
    return "LOW"


def _severity_level_from_risk(risk_level: Optional[str]) -> str:
    level = (risk_level or "").upper()
    if level == "HIGH":
        return "high"
    if level == "MEDIUM":
        return "medium"
    return "low"


def _resolve_target_disease(
    *,
    disease_id: Optional[int],
    diagnosis_code: Optional[str],
    diagnosis_name: Optional[str],
    risk_level: Optional[str],
) -> Tuple[Optional[Disease], Optional[str], int]:
    disease: Optional[Disease] = None
    if disease_id is not None:
        disease = Disease.query.get(disease_id)
        if not disease:
            return None, "disease_id not found", 404
        if diagnosis_code and (disease.code or "").upper() != diagnosis_code:
            return None, "disease_id and diagnosis_code do not match", 400
        return disease, None, 200

    if not diagnosis_code:
        return None, None, 200

    disease = Disease.query.filter_by(code=diagnosis_code).first()
    if disease:
        return disease, None, 200

    disease = Disease(
        code=diagnosis_code,
        name=diagnosis_name or diagnosis_code,
        severity_level=_severity_level_from_risk(risk_level),
        active=True,
    )
    db.session.add(disease)
    db.session.flush()
    return disease, None, 200


def _legacy_primary_action(rule: Rule) -> Optional[RuleAction]:
    best = None
    best_conf = -1.0
    for action in rule.actions:
        raw = float(action.confidence) if action.confidence is not None else 0.0
        normalized = raw / 100.0 if raw > 1 else raw
        if normalized > best_conf:
            best = action
            best_conf = normalized
    return best


def _sync_legacy_action(rule: Rule, disease: Optional[Disease], base_confidence: Optional[float]) -> None:
    existing_actions = RuleAction.query.filter_by(rule_id=rule.id).all()
    if not disease:
        for item in existing_actions:
            db.session.delete(item)
        return

    confidence = base_confidence if base_confidence is not None else 0.5
    action = next((item for item in existing_actions if item.disease_id == disease.id), None)
    if action:
        action.confidence = confidence
    else:
        action = RuleAction(
            rule_id=rule.id,
            disease_id=disease.id,
            confidence=confidence,
        )
        db.session.add(action)
        db.session.flush()

    for item in existing_actions:
        if item.id != action.id:
            db.session.delete(item)


def rule_payload(rule: Rule, include_conditions: bool = False) -> Dict[str, Any]:
    disease = rule.disease
    risk_level = (rule.risk_level or "").upper() or None
    base_confidence = float(rule.base_confidence) if rule.base_confidence is not None else None

    legacy = _legacy_primary_action(rule)
    if not disease and legacy and legacy.disease:
        disease = legacy.disease
    if base_confidence is None and legacy and legacy.confidence is not None:
        base_confidence = _confidence_to_fraction(float(legacy.confidence))
    if not risk_level:
        risk_level = _risk_from_disease(disease)

    payload = {
        "id": rule.id,
        "rule_code": rule.rule_code,
        "title": rule.title,
        "rule_type": (rule.rule_type or "screening").lower(),
        "version": int(rule.version or 1),
        "rule_set_id": rule.rule_set_id,
        "disease_id": disease.id if disease else None,
        "base_confidence": round(base_confidence, 4) if base_confidence is not None else None,
        "max_conf_without_labs": (
            float(rule.confidence_cap_if_unconfirmed)
            if rule.confidence_cap_if_unconfirmed is not None
            else None
        ),
        "confidence_cap_if_unconfirmed": (
            float(rule.confidence_cap_if_unconfirmed)
            if rule.confidence_cap_if_unconfirmed is not None
            else None
        ),
        "confidence_bonus_max": (
            float(rule.confidence_bonus_max)
            if rule.confidence_bonus_max is not None
            else None
        ),
        "min_required_matches": (
            int(rule.min_required_matches)
            if rule.min_required_matches is not None
            else None
        ),
        "stop_engine_on_match": bool(rule.stop_on_match),
        "stop_on_match": bool(rule.stop_on_match),
        "risk_level": risk_level,
        "priority": rule.priority,
        "active": bool(rule.is_active),
        "is_active": bool(rule.is_active),
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        "conditions_count": len(rule.conditions),
        "patient_summary_template": rule.patient_summary_template,
        "doctor_response_template": rule.doctor_response_template or rule.explanation_text,
        "advice_template": rule.advice_template,
        "explanation_text": rule.explanation_text,
        "actions": [
            {
                "disease_id": disease.id if disease else None,
                "disease_code": disease.code if disease else None,
                "disease_name": disease.name if disease else None,
                "risk_level": risk_level,
                "confidence": base_confidence,
            }
        ] if (disease or base_confidence is not None) else [],
    }

    confidence_pct = round(base_confidence * 100.0, 2) if base_confidence is not None else None
    payload.update({
        "diagnosis": disease.name if disease and disease.name else (disease.code if disease else None),
        "diagnosis_code": disease.code if disease else None,
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
    rule_code = (data.get("rule_code") or "").strip().upper()
    title = (data.get("title") or "").strip()

    confidence, error = _parse_confidence(data.get("confidence", data.get("base_confidence")))
    if error:
        return None, error, 400
    base_confidence = _confidence_to_fraction(confidence)
    if base_confidence is None:
        base_confidence = 0.5

    confidence_cap_if_unconfirmed, error = _parse_fraction_field(
        data.get("max_conf_without_labs", data.get("confidence_cap_if_unconfirmed")),
        "confidence_cap_if_unconfirmed",
    )
    if error:
        return None, error, 400

    confidence_bonus_max, error = _parse_fraction_field(
        data.get("confidence_bonus_max"),
        "confidence_bonus_max",
    )
    if error:
        return None, error, 400

    min_required_matches, error = _parse_non_negative_int(
        data.get("min_required_matches"),
        "min_required_matches",
    )
    if error:
        return None, error, 400

    rule_type, type_error = _normalize_rule_type(data.get("rule_type"), fallback="screening")
    if type_error:
        return None, type_error, 400

    if not rule_code:
        rule_code = _generate_rule_code(rule_type or "screening")
    elif Rule.query.filter_by(rule_code=rule_code).first():
        return None, "rule_code already exists", 409

    if not title:
        title = rule_code

    diagnosis, diagnosis_code, risk_level, disease_id, diagnosis_error = _normalize_diagnosis_payload(data)
    if diagnosis_error:
        return None, diagnosis_error, 400
    disease, disease_error, disease_status = _resolve_target_disease(
        disease_id=disease_id,
        diagnosis_code=diagnosis_code,
        diagnosis_name=diagnosis,
        risk_level=risk_level,
    )
    if disease_error:
        return None, disease_error, disease_status

    priority = int(data.get("priority") or 0)
    is_active = _coerce_bool(data.get("active"), _coerce_bool(data.get("is_active"), True))
    stop_on_match = _coerce_bool(data.get("stop_engine_on_match"), _coerce_bool(data.get("stop_on_match"), False))
    rule_set_id_raw = data.get("rule_set_id")
    rule_set_id = None
    if rule_set_id_raw not in (None, ""):
        try:
            rule_set_id = int(rule_set_id_raw)
        except (TypeError, ValueError):
            return None, "rule_set_id must be an integer", 400
    version, error = _parse_non_negative_int(data.get("version"), "version")
    if error:
        return None, error, 400
    if version is None:
        version = 1
    explanation_text = data.get("explanation_text")
    if isinstance(explanation_text, str):
        explanation_text = explanation_text.strip() or None
    doctor_response_template = data.get("doctor_response_template")
    if isinstance(doctor_response_template, str):
        doctor_response_template = doctor_response_template.strip() or None
    if doctor_response_template is None:
        doctor_response_template = explanation_text

    patient_summary_template = data.get("patient_summary_template")
    if isinstance(patient_summary_template, str):
        patient_summary_template = patient_summary_template.strip() or None

    advice_template = data.get("advice_template")
    if isinstance(advice_template, str):
        advice_template = advice_template.strip() or None

    rule = Rule(
        rule_code=rule_code,
        title=title,
        rule_type=rule_type or "screening",
        version=version,
        rule_set_id=rule_set_id,
        disease_id=(disease.id if disease else None),
        base_confidence=base_confidence,
        confidence_cap_if_unconfirmed=confidence_cap_if_unconfirmed,
        confidence_bonus_max=confidence_bonus_max,
        min_required_matches=min_required_matches,
        stop_on_match=stop_on_match,
        risk_level=((risk_level or _risk_from_disease(disease) or "LOW").upper()),
        priority=priority,
        is_active=is_active,
        patient_summary_template=patient_summary_template,
        doctor_response_template=doctor_response_template,
        advice_template=advice_template,
        explanation_text=doctor_response_template,
    )
    db.session.add(rule)
    db.session.flush()
    _sync_legacy_action(rule, disease, base_confidence)
    db.session.commit()

    return rule_payload(rule, include_conditions=True), None, 201


def update_rule_from_payload(
    rule: Rule,
    data: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    disease = rule.disease

    if "rule_code" in data:
        rule_code = (data.get("rule_code") or "").strip().upper()
        if not rule_code:
            return None, "rule_code cannot be empty", 400
        if Rule.query.filter(Rule.rule_code == rule_code, Rule.id != rule.id).first():
            return None, "rule_code already exists", 409
        rule.rule_code = rule_code

    if "title" in data:
        title = (data.get("title") or "").strip()
        if title:
            rule.title = title

    if "rule_type" in data:
        rule_type, type_error = _normalize_rule_type(data.get("rule_type"), fallback=(rule.rule_type or "screening"))
        if type_error:
            return None, type_error, 400
        rule.rule_type = rule_type or "screening"

    if "version" in data:
        version, error = _parse_non_negative_int(data.get("version"), "version")
        if error:
            return None, error, 400
        if version is None:
            return None, "version cannot be empty", 400
        rule.version = version

    if "priority" in data:
        rule.priority = int(data.get("priority") or 0)

    if "active" in data or "is_active" in data:
        rule.is_active = _coerce_bool(
            data.get("active"),
            _coerce_bool(data.get("is_active"), bool(rule.is_active)),
        )

    if "stop_engine_on_match" in data or "stop_on_match" in data:
        rule.stop_on_match = _coerce_bool(
            data.get("stop_engine_on_match"),
            _coerce_bool(data.get("stop_on_match"), bool(rule.stop_on_match)),
        )

    if "rule_set_id" in data:
        raw = data.get("rule_set_id")
        if raw in (None, ""):
            rule.rule_set_id = None
        else:
            try:
                rule.rule_set_id = int(raw)
            except (TypeError, ValueError):
                return None, "rule_set_id must be an integer", 400

    if "explanation_text" in data:
        explanation_text = data.get("explanation_text")
        if isinstance(explanation_text, str):
            explanation_text = explanation_text.strip() or None
        rule.explanation_text = explanation_text
        if "doctor_response_template" not in data:
            rule.doctor_response_template = explanation_text

    if "doctor_response_template" in data:
        doctor_response_template = data.get("doctor_response_template")
        if isinstance(doctor_response_template, str):
            doctor_response_template = doctor_response_template.strip() or None
        rule.doctor_response_template = doctor_response_template
        rule.explanation_text = doctor_response_template

    if "patient_summary_template" in data:
        patient_summary_template = data.get("patient_summary_template")
        if isinstance(patient_summary_template, str):
            patient_summary_template = patient_summary_template.strip() or None
        rule.patient_summary_template = patient_summary_template

    if "advice_template" in data:
        advice_template = data.get("advice_template")
        if isinstance(advice_template, str):
            advice_template = advice_template.strip() or None
        rule.advice_template = advice_template

    if "confidence" in data or "base_confidence" in data:
        confidence, confidence_error = _parse_confidence(data.get("confidence", data.get("base_confidence")))
        if confidence_error:
            return None, confidence_error, 400
        normalized = _confidence_to_fraction(confidence)
        if normalized is not None:
            rule.base_confidence = normalized

    if "confidence_cap_if_unconfirmed" in data or "max_conf_without_labs" in data:
        confidence_cap_if_unconfirmed, error = _parse_fraction_field(
            data.get("max_conf_without_labs", data.get("confidence_cap_if_unconfirmed")),
            "confidence_cap_if_unconfirmed",
        )
        if error:
            return None, error, 400
        rule.confidence_cap_if_unconfirmed = confidence_cap_if_unconfirmed

    if "confidence_bonus_max" in data:
        confidence_bonus_max, error = _parse_fraction_field(
            data.get("confidence_bonus_max"),
            "confidence_bonus_max",
        )
        if error:
            return None, error, 400
        rule.confidence_bonus_max = confidence_bonus_max

    if "min_required_matches" in data:
        min_required_matches, error = _parse_non_negative_int(
            data.get("min_required_matches"),
            "min_required_matches",
        )
        if error:
            return None, error, 400
        rule.min_required_matches = min_required_matches

    target_keys = {"diagnosis", "diagnosis_code", "risk_level", "disease_id"}
    if any(key in data for key in target_keys):
        diagnosis, diagnosis_code, risk_level, disease_id, diagnosis_error = _normalize_diagnosis_payload(data)
        if diagnosis_error:
            return None, diagnosis_error, 400
        resolved_disease, disease_error, disease_status = _resolve_target_disease(
            disease_id=disease_id,
            diagnosis_code=diagnosis_code,
            diagnosis_name=diagnosis,
            risk_level=risk_level,
        )
        if disease_error:
            return None, disease_error, disease_status

        explicit_clear = (
            ("disease_id" in data and data.get("disease_id") in (None, ""))
            or ("diagnosis_code" in data and not str(data.get("diagnosis_code") or "").strip())
        )

        if resolved_disease is not None:
            disease = resolved_disease
            rule.disease_id = resolved_disease.id
        elif explicit_clear:
            disease = None
            rule.disease_id = None

        if risk_level:
            rule.risk_level = risk_level
        elif disease is not None:
            rule.risk_level = _risk_from_disease(disease)

    _normalize_screening_rule_conditions(rule)
    db.session.flush()
    _sync_legacy_action(rule, disease, _confidence_to_fraction(float(rule.base_confidence) if rule.base_confidence is not None else None))
    db.session.commit()

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
    symptom = Symptom.query.get(symptom_id)
    if not symptom:
        return None, "symptom_id not found", 404
    is_required = _enforce_screening_labs_optional(rule.rule_type or "screening", symptom, is_required)

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
        symptom = Symptom.query.get(symptom_id)
        if not symptom:
            return None, "symptom_id not found", 404
        is_required = _enforce_screening_labs_optional(rule.rule_type or "screening", symptom, is_required)

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
