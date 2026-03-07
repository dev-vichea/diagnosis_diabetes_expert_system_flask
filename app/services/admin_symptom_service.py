import json
from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from sqlalchemy.exc import IntegrityError

from app.models import CaseFact, Rule, RuleCondition, Symptom

VALID_INPUT_TYPES = {"BOOLEAN", "NUMBER", "TEXT", "SINGLE", "MULTI"}
VALID_SHOW_IF_OPERATORS = {"==", "!=", ">=", "<=", ">", "<", "PRESENT", "ABSENT"}


def _symptom_style(symptom: Symptom) -> str:
    category = (symptom.category or "").strip().lower().replace("-", "_")
    code = (symptom.code or "").strip().lower().replace("-", "_")
    if category in {"lab", "labs", "laboratory", "has_lab", "hab_lab", "gate"}:
        return "LAB"
    if code in {"has_labs", "has_lab"}:
        return "LAB"
    if symptom.parent_symptom_id:
        return "DETAIL"
    if category == "classic":
        return "CHECKLIST"
    return "CHECKLIST"


def symptom_payload(symptom: Symptom) -> Dict[str, Any]:
    return {
        "id": symptom.id,
        "code": symptom.code,
        "name": symptom.name or symptom.code,
        "question_text": symptom.question_text,
        "input_type": symptom.input_type,
        "unit": symptom.unit,
        "options_json": symptom.options_json,
        "min": float(symptom.min_value) if symptom.min_value is not None else None,
        "max": float(symptom.max_value) if symptom.max_value is not None else None,
        "allow_unknown": bool(symptom.allow_unknown),
        "importance_weight": float(symptom.importance_weight) if symptom.importance_weight is not None else 1.0,
        "reference_ranges_json": symptom.reference_ranges_json,
        "active": bool(symptom.active),
        "is_active": bool(symptom.is_active),
        "category": symptom.category,
        "parent_symptom_id": symptom.parent_symptom_id,
        "show_if_operator": symptom.show_if_operator,
        "show_if_value": symptom.show_if_value,
        "priority_order": symptom.priority_order,
        "question_style": _symptom_style(symptom),
        "created_at": symptom.created_at.isoformat() if symptom.created_at else None,
        "updated_at": symptom.updated_at.isoformat() if symptom.updated_at else None,
    }


def list_symptoms_payloads() -> List[Dict[str, Any]]:
    rows = Symptom.query.order_by(Symptom.priority_order.asc(), Symptom.id.asc()).all()
    return [symptom_payload(symptom) for symptom in rows]


def _parse_options_json(raw: Any) -> Tuple[Optional[Any], Optional[str]]:
    if raw is None or raw == "":
        return None, None
    if isinstance(raw, (list, dict)):
        return raw, None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None, "options_json must be valid JSON"
        if not isinstance(parsed, (list, dict)):
            return None, "options_json must be an array or object"
        return parsed, None
    return None, "options_json must be a JSON array or object"


def _normalize_input_type(raw: Any) -> Tuple[str, Optional[str]]:
    value = (raw or "BOOLEAN")
    if isinstance(value, str):
        value = value.strip().upper()
    if value not in VALID_INPUT_TYPES:
        return "", "input_type must be BOOLEAN, NUMBER, TEXT, SINGLE, or MULTI"
    return value, None


def create_symptom_from_payload(
    data: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    question_text = (data.get("question_text") or "").strip()
    input_type, error = _normalize_input_type(data.get("input_type"))
    if error:
        return None, error, 400

    unit = (data.get("unit") or "").strip() or None
    category = (data.get("category") or "").strip() or None
    min_value = data.get("min", data.get("min_value"))
    max_value = data.get("max", data.get("max_value"))
    allow_unknown = bool(data.get("allow_unknown", False))
    importance_weight = float(data.get("importance_weight") or 1.0)
    reference_ranges_json, ref_error = _parse_options_json(data.get("reference_ranges_json"))
    if ref_error:
        return None, "reference_ranges_json must be valid JSON", 400
    priority_order = int(data.get("priority_order") or 0)
    is_active = bool(data.get("active", data.get("is_active", True)))
    parent_symptom_id = data.get("parent_symptom_id")
    show_if_operator = (data.get("show_if_operator") or "").strip().upper() or None
    show_if_value = data.get("show_if_value")

    if not code or not question_text:
        return None, "code and question_text are required", 400

    if not name:
        name = question_text or code

    options_json, error = _parse_options_json(data.get("options_json"))
    if error:
        return None, error, 400
    if input_type in {"SINGLE", "MULTI"} and not options_json:
        return None, "options_json is required for SINGLE or MULTI input_type", 400
    if input_type not in {"SINGLE", "MULTI"}:
        options_json = None

    try:
        min_value = float(min_value) if min_value not in (None, "") else None
    except (TypeError, ValueError):
        return None, "min must be numeric", 400
    try:
        max_value = float(max_value) if max_value not in (None, "") else None
    except (TypeError, ValueError):
        return None, "max must be numeric", 400

    if Symptom.query.filter_by(code=code).first():
        return None, "symptom code already exists", 409

    if parent_symptom_id is not None:
        try:
            parent_symptom_id = int(parent_symptom_id)
        except (TypeError, ValueError):
            return None, "parent_symptom_id must be an integer", 400
        parent = Symptom.query.get(parent_symptom_id)
        if not parent:
            return None, "parent_symptom_id not found", 400
    if show_if_operator and show_if_operator not in VALID_SHOW_IF_OPERATORS:
        return None, f"invalid show_if_operator: {show_if_operator}", 400
    if show_if_value is not None and not isinstance(show_if_value, str):
        show_if_value = str(show_if_value)

    symptom = Symptom(
        code=code,
        name=name,
        question_text=question_text,
        input_type=input_type,
        unit=unit,
        options_json=options_json,
        category=category,
        min_value=min_value,
        max_value=max_value,
        allow_unknown=allow_unknown,
        importance_weight=importance_weight,
        reference_ranges_json=reference_ranges_json,
        parent_symptom_id=parent_symptom_id,
        show_if_operator=show_if_operator,
        show_if_value=show_if_value,
        priority_order=priority_order,
        active=is_active,
    )
    db.session.add(symptom)
    db.session.commit()

    return symptom_payload(symptom), None, 201


def update_symptom_from_payload(
    symptom: Symptom,
    data: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    if "code" in data:
        code = (data.get("code") or "").strip()
        if not code:
            return None, "code cannot be empty", 400
        if Symptom.query.filter(Symptom.code == code, Symptom.id != symptom.id).first():
            return None, "code already used", 409
        symptom.code = code

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return None, "name cannot be empty", 400
        symptom.name = name

    if "question_text" in data:
        question_text = (data.get("question_text") or "").strip()
        if not question_text:
            return None, "question_text cannot be empty", 400
        symptom.question_text = question_text

    input_type = symptom.input_type
    if "input_type" in data:
        input_type, error = _normalize_input_type(data.get("input_type"))
        if error:
            return None, error, 400
        symptom.input_type = input_type
    else:
        input_type = symptom.input_type

    if "unit" in data:
        symptom.unit = (data.get("unit") or "").strip() or None

    if "category" in data:
        symptom.category = (data.get("category") or "").strip() or None

    if "min" in data or "min_value" in data:
        raw = data.get("min", data.get("min_value"))
        try:
            symptom.min_value = float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            return None, "min must be numeric", 400

    if "max" in data or "max_value" in data:
        raw = data.get("max", data.get("max_value"))
        try:
            symptom.max_value = float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            return None, "max must be numeric", 400

    if "allow_unknown" in data:
        symptom.allow_unknown = bool(data.get("allow_unknown"))

    if "importance_weight" in data:
        try:
            symptom.importance_weight = float(data.get("importance_weight") or 1.0)
        except (TypeError, ValueError):
            return None, "importance_weight must be numeric", 400

    if "reference_ranges_json" in data:
        parsed_ref, error = _parse_options_json(data.get("reference_ranges_json"))
        if error:
            return None, "reference_ranges_json must be valid JSON", 400
        symptom.reference_ranges_json = parsed_ref

    if "priority_order" in data:
        symptom.priority_order = int(data.get("priority_order") or 0)

    if "active" in data or "is_active" in data:
        symptom.active = bool(data.get("active", data.get("is_active")))

    if "parent_symptom_id" in data:
        parent_symptom_id = data.get("parent_symptom_id")
        if parent_symptom_id in (None, ""):
            symptom.parent_symptom_id = None
        else:
            try:
                parent_symptom_id = int(parent_symptom_id)
            except (TypeError, ValueError):
                return None, "parent_symptom_id must be an integer", 400
            if parent_symptom_id == symptom.id:
                return None, "parent_symptom_id cannot be self", 400
            parent = Symptom.query.get(parent_symptom_id)
            if not parent:
                return None, "parent_symptom_id not found", 400
            symptom.parent_symptom_id = parent_symptom_id

    if "show_if_operator" in data:
        show_if_operator = (data.get("show_if_operator") or "").strip().upper() or None
        if show_if_operator and show_if_operator not in VALID_SHOW_IF_OPERATORS:
            return None, f"invalid show_if_operator: {show_if_operator}", 400
        symptom.show_if_operator = show_if_operator

    if "show_if_value" in data:
        show_if_value = data.get("show_if_value")
        if show_if_value in (None, ""):
            symptom.show_if_value = None
        else:
            symptom.show_if_value = str(show_if_value)

    if input_type in {"SINGLE", "MULTI"} or "options_json" in data:
        raw_options = data.get("options_json", symptom.options_json)
        options_json, error = _parse_options_json(raw_options)
        if error:
            return None, error, 400
        if input_type in {"SINGLE", "MULTI"} and not options_json:
            return None, "options_json is required for SINGLE or MULTI input_type", 400
        symptom.options_json = options_json
    elif input_type not in {"SINGLE", "MULTI"}:
        symptom.options_json = None

    db.session.commit()
    return symptom_payload(symptom), None, 200


def delete_symptom(symptom: Symptom) -> Tuple[bool, Optional[str], int]:
    rule_count = db.session.query(RuleCondition.id).filter(RuleCondition.symptom_id == symptom.id).count()
    fact_count = db.session.query(CaseFact.id).filter(CaseFact.symptom_id == symptom.id).count()

    try:
        if rule_count > 0:
            RuleCondition.query.filter_by(symptom_id=symptom.id).delete(synchronize_session=False)
        if fact_count > 0:
            CaseFact.query.filter_by(symptom_id=symptom.id).delete(synchronize_session=False)
        db.session.delete(symptom)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        sample_rules = (
            db.session.query(Rule.rule_code)
            .join(RuleCondition, RuleCondition.rule_id == Rule.id)
            .filter(RuleCondition.symptom_id == symptom.id)
            .order_by(Rule.rule_code.asc())
            .limit(3)
            .all()
        )
        sample_codes = [str(row[0]) for row in sample_rules if row and row[0]]
        sample_suffix = f" (e.g. {', '.join(sample_codes)})" if sample_codes else ""
        return (
            False,
            (
                "Cannot delete symptom because it is still referenced by related data"
                f"{sample_suffix}."
            ),
            409,
        )

    return True, None, 200
