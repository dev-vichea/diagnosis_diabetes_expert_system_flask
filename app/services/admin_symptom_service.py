import json
from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from app.models import Symptom

VALID_INPUT_TYPES = {"BOOLEAN", "NUMBER", "TEXT", "SINGLE"}
VALID_SHOW_IF_OPERATORS = {"==", "!=", ">=", "<=", ">", "<", "PRESENT", "ABSENT"}


def symptom_payload(symptom: Symptom) -> Dict[str, Any]:
    return {
        "id": symptom.id,
        "code": symptom.code,
        "name": symptom.name or symptom.code,
        "question_text": symptom.question_text,
        "input_type": symptom.input_type,
        "unit": symptom.unit,
        "options_json": symptom.options_json,
        "is_active": bool(symptom.is_active),
        "category": symptom.category,
        "ui_section": symptom.ui_section,
        "parent_symptom_id": symptom.parent_symptom_id,
        "show_if_operator": symptom.show_if_operator,
        "show_if_value": symptom.show_if_value,
        "priority_order": symptom.priority_order,
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
        return "", "input_type must be BOOLEAN, NUMBER, TEXT, or SINGLE"
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
    ui_section = (data.get("ui_section") or "").strip() or None
    priority_order = int(data.get("priority_order") or 0)
    is_active = bool(data.get("is_active", True))
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
    if input_type == "SINGLE" and not options_json:
        return None, "options_json is required for SINGLE input_type", 400
    if input_type != "SINGLE":
        options_json = None

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
        ui_section=ui_section,
        parent_symptom_id=parent_symptom_id,
        show_if_operator=show_if_operator,
        show_if_value=show_if_value,
        priority_order=priority_order,
        is_active=is_active,
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

    if "ui_section" in data:
        symptom.ui_section = (data.get("ui_section") or "").strip() or None

    if "priority_order" in data:
        symptom.priority_order = int(data.get("priority_order") or 0)

    if "is_active" in data:
        symptom.is_active = bool(data.get("is_active"))

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

    if input_type == "SINGLE" or "options_json" in data:
        raw_options = data.get("options_json", symptom.options_json)
        options_json, error = _parse_options_json(raw_options)
        if error:
            return None, error, 400
        if input_type == "SINGLE" and not options_json:
            return None, "options_json is required for SINGLE input_type", 400
        symptom.options_json = options_json
    elif input_type != "SINGLE":
        symptom.options_json = None

    db.session.commit()
    return symptom_payload(symptom), None, 200
