from typing import Dict, Any, Optional

from app.models import CaseFact, Symptom


def _match_trigger(operator: str, expected: Optional[str], actual: Any) -> bool:
    operator = (operator or "==").upper()
    if actual is None:
        return operator == "ABSENT"

    if isinstance(expected, str) and expected.lower() in {"true", "false"}:
        expected = "1" if expected.lower() == "true" else "0"
    if isinstance(expected, str) and expected.strip() in {"1", "0"}:
        expected_val = expected.strip() == "1"
    else:
        expected_val = expected

    if operator == "PRESENT":
        if isinstance(actual, bool):
            return actual is True
        return True
    if operator == "ABSENT":
        if isinstance(actual, bool):
            return actual is False
        return False
    if operator == "==":
        return actual == expected_val
    if operator == "!=":
        return actual != expected_val

    try:
        actual_num = float(actual)
        expected_num = float(expected_val)
    except (TypeError, ValueError):
        return False

    if operator == ">":
        return actual_num > expected_num
    if operator == ">=":
        return actual_num >= expected_num
    if operator == "<":
        return actual_num < expected_num
    if operator == "<=":
        return actual_num <= expected_num
    return False


def _is_symptom_active(symptom: Symptom, facts: Dict[str, Any], symptom_map: Dict[int, Symptom], seen: set) -> bool:
    if symptom.id in seen:
        return True
    seen.add(symptom.id)
    if not symptom.parent_symptom_id:
        return True
    parent = symptom_map.get(symptom.parent_symptom_id)
    if not parent:
        return False
    if not _is_symptom_active(parent, facts, symptom_map, seen):
        return False
    actual = facts.get(parent.code)
    return _match_trigger(symptom.show_if_operator or "==", symptom.show_if_value, actual)


def _typed_value(fact: CaseFact, symptom: Optional[Symptom]) -> Any:
    input_type = (symptom.input_type if symptom else "BOOLEAN") if symptom else "BOOLEAN"
    input_type = (input_type or "BOOLEAN").upper()
    if input_type == "BOOLEAN":
        return None if fact.value_bool is None else bool(fact.value_bool)
    if input_type == "NUMBER":
        return fact.value_number
    if input_type in {"TEXT", "SINGLE"}:
        return fact.value_text
    if fact.value_bool is not None:
        return bool(fact.value_bool)
    if fact.value_number is not None:
        return fact.value_number
    if fact.value_text is not None:
        return fact.value_text
    return None


def _set_fact_value(facts: Dict[str, Any], code: str, value: Any):
    if code not in facts:
        facts[code] = value
        return
    if isinstance(value, bool):
        if value and facts.get(code) is False:
            facts[code] = True
        return
    facts[code] = value


def facts_for_assessment(assessment_id: int) -> Dict[str, Any]:
    rows = CaseFact.query.filter_by(assessment_id=assessment_id).all()
    symptom_ids = [r.symptom_id for r in rows if r.symptom_id]

    symptom_map = {s.id: s for s in Symptom.query.filter(Symptom.id.in_(symptom_ids)).all()} if symptom_ids else {}

    raw_facts: Dict[str, Any] = {}
    for row in rows:
        symptom = symptom_map.get(row.symptom_id)
        if not symptom:
            continue
        value = _typed_value(row, symptom)
        if value is None and (symptom.input_type or "").upper() == "NUMBER":
            _set_fact_value(
                raw_facts,
                symptom.code,
                {
                    "value": None,
                    "state": getattr(row, "state", None),
                    "is_provided": bool(getattr(row, "is_provided", False)),
                    "value_number": None,
                },
            )
            continue
        if value is None:
            continue
        _set_fact_value(raw_facts, symptom.code, value)

    facts: Dict[str, Any] = {}
    for row in rows:
        symptom = symptom_map.get(row.symptom_id)
        if not symptom:
            continue
        value = _typed_value(row, symptom)
        if value is None and (symptom.input_type or "").upper() == "NUMBER":
            if not _is_symptom_active(symptom, raw_facts, symptom_map, set()):
                continue
            _set_fact_value(
                facts,
                symptom.code,
                {
                    "value": None,
                    "state": getattr(row, "state", None),
                    "is_provided": bool(getattr(row, "is_provided", False)),
                    "value_number": None,
                },
            )
            continue
        if value is None:
            continue
        if not _is_symptom_active(symptom, raw_facts, symptom_map, set()):
            continue
        _set_fact_value(facts, symptom.code, value)

    return facts
