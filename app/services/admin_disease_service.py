from typing import Any, Dict, List, Optional, Set, Tuple

from app.extensions import db
from app.models import Disease, Rule, RuleAction, RuleCondition, Symptom

VALID_SEVERITY_LEVEL = {"low", "medium", "high"}
VALID_CATEGORY = {"type1", "type2", "prediabetes", "gestational", "other"}


def disease_payload(disease: Disease) -> Dict[str, Any]:
    recommendation = disease.default_recommendation
    active = bool(disease.active)
    screening_label = f"Possible {disease.name} (screening)" if disease.name else None
    return {
        "id": disease.id,
        "code": disease.code,
        "name": disease.name,
        "description": disease.description,
        "category": disease.category,
        "severity_level": disease.severity_level,
        "default_recommendation": recommendation,
        "active": active,
        # Compatibility keys for current frontend payload consumers.
        "patient_label_screening": screening_label,
        "patient_label_confirmed": disease.name,
        "default_next_steps": recommendation,
        "red_flag_message": None,
        "is_active": active,
        "created_at": disease.created_at.isoformat() if disease.created_at else None,
    }


def list_diseases_payloads() -> List[Dict[str, Any]]:
    rows = Disease.query.order_by(Disease.code.asc(), Disease.id.asc()).all()
    return [disease_payload(disease) for disease in rows]


def _coerce_bool(raw: Any, default: bool = True) -> bool:
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


def _normalize_enum(raw: Any, allowed: set, default: str, field_name: str) -> Tuple[str, Optional[str]]:
    value = (raw or default)
    if isinstance(value, str):
        value = value.strip().lower()
    if value not in allowed:
        return "", f"{field_name} must be one of: {', '.join(sorted(allowed))}"
    return value, None


def _normalize_severity(raw: Any, default: str = "low") -> Tuple[str, Optional[str]]:
    value = raw
    if isinstance(value, str) and value.strip().lower() == "urgent":
        value = "high"
    return _normalize_enum(value, VALID_SEVERITY_LEVEL, default, "severity_level")


def _normalize_category(raw: Any, default: str = "other") -> Tuple[str, Optional[str]]:
    value = raw
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"diabetes", "type2dm", "t2dm"}:
            value = "type2"
        elif lowered in {"type1dm", "t1dm"}:
            value = "type1"
        elif lowered in {"pregnancy", "gdm"}:
            value = "gestational"
        elif lowered in {"predm", "pre-diabetes"}:
            value = "prediabetes"
    return _normalize_enum(value, VALID_CATEGORY, default, "category")


def create_disease_from_payload(
    data: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()

    description = (data.get("description") or "").strip() or None
    raw_category = (data.get("category") or "other")
    default_recommendation = (
        (data.get("default_recommendation") or data.get("default_next_steps") or "").strip() or None
    )
    active = _coerce_bool(data.get("active"), _coerce_bool(data.get("is_active"), True))

    severity_level, error = _normalize_severity(data.get("severity_level"), "low")
    if error:
        return None, error, 400

    category, error = _normalize_category(raw_category, "other")
    if error:
        return None, error, 400

    if not code or not name:
        return None, "code and name are required", 400
    if Disease.query.filter_by(code=code).first():
        return None, "disease code already exists", 409

    disease = Disease(
        code=code,
        name=name,
        description=description,
        category=category,
        severity_level=severity_level,
        default_recommendation=default_recommendation,
        active=active,
    )
    db.session.add(disease)
    db.session.commit()
    return disease_payload(disease), None, 201


def update_disease_from_payload(
    disease: Disease,
    data: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    if "code" in data:
        code = (data.get("code") or "").strip().upper()
        if not code:
            return None, "code cannot be empty", 400
        if Disease.query.filter(Disease.code == code, Disease.id != disease.id).first():
            return None, "code already used", 409
        disease.code = code

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return None, "name cannot be empty", 400
        disease.name = name

    if "description" in data:
        disease.description = (data.get("description") or "").strip() or None

    if "category" in data:
        category, error = _normalize_category(
            data.get("category"),
            disease.category or "other",
        )
        if error:
            return None, error, 400
        disease.category = category

    if "severity_level" in data:
        severity_level, error = _normalize_severity(
            data.get("severity_level"),
            disease.severity_level or "low",
        )
        if error:
            return None, error, 400
        disease.severity_level = severity_level

    if "default_recommendation" in data or "default_next_steps" in data:
        raw = data.get("default_recommendation")
        if raw is None and "default_next_steps" in data:
            raw = data.get("default_next_steps")
        disease.default_recommendation = (raw or "").strip() or None

    if "active" in data or "is_active" in data:
        raw_active = data.get("active")
        if raw_active is None and "is_active" in data:
            raw_active = data.get("is_active")
        disease.active = _coerce_bool(raw_active, bool(disease.active))

    db.session.commit()
    return disease_payload(disease), None, 200


def disease_related_symptoms_payload(disease_id: int) -> Dict[str, Any]:
    rule_ids: Set[int] = set()

    for row in db.session.query(Rule.id).filter(Rule.disease_id == disease_id).all():
        if row[0]:
            rule_ids.add(int(row[0]))

    for row in db.session.query(RuleAction.rule_id).filter(RuleAction.disease_id == disease_id).all():
        if row[0]:
            rule_ids.add(int(row[0]))

    if not rule_ids:
        return {
            "rule_count": 0,
            "symptom_count": 0,
            "items": [],
        }

    rows = (
        db.session.query(
            RuleCondition.symptom_id,
            Symptom.code,
            Symptom.name,
            Symptom.category,
            Symptom.input_type,
            Rule.rule_code,
        )
        .join(Rule, Rule.id == RuleCondition.rule_id)
        .join(Symptom, Symptom.id == RuleCondition.symptom_id)
        .filter(RuleCondition.rule_id.in_(list(rule_ids)))
        .order_by(Symptom.name.asc(), Symptom.code.asc(), Rule.rule_code.asc())
        .all()
    )

    grouped: Dict[int, Dict[str, Any]] = {}
    for symptom_id, code, name, category, input_type, rule_code in rows:
        sid = int(symptom_id)
        entry = grouped.setdefault(
            sid,
            {
                "id": sid,
                "code": code,
                "name": name,
                "category": category,
                "input_type": input_type,
                "rule_codes": set(),
            },
        )
        if rule_code:
            entry["rule_codes"].add(str(rule_code))

    items: List[Dict[str, Any]] = []
    for value in grouped.values():
        items.append(
            {
                "id": value["id"],
                "code": value["code"],
                "name": value["name"],
                "category": value["category"],
                "input_type": value["input_type"],
                "rule_codes": sorted(list(value["rule_codes"])),
            }
        )

    items.sort(key=lambda row: ((row.get("name") or "").lower(), (row.get("code") or "").lower()))
    return {
        "rule_count": len(rule_ids),
        "symptom_count": len(items),
        "items": items,
    }
