import json
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


def _parse_numeric(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _parse_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def _parse_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (int, float, bool)):
        return [value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
            if parsed is None:
                return []
            return [parsed]
        except json.JSONDecodeError:
            parts = [p.strip() for p in value.split(",") if p.strip()]
            return parts or [value]
    return [value]


def _in_list(actual: Any, candidates: List[Any]) -> bool:
    if not candidates:
        return False

    if isinstance(actual, bool):
        if actual in candidates:
            return True

    if isinstance(actual, (int, float)) and not isinstance(actual, bool):
        num_candidates = [c for c in (_parse_numeric(v) for v in candidates) if c is not None]
        if num_candidates and _parse_numeric(actual) in num_candidates:
            return True

    actual_str = str(actual).strip().lower()
    candidate_strs = {str(v).strip().lower() for v in candidates}
    return actual_str in candidate_strs


def _condition_detail(cond, expected: Any = None, actual: Any = None) -> Dict[str, Any]:
    return {
        "symptom_id": getattr(cond, "symptom_id", None),
        "symptom_code": getattr(cond, "symptom_code", None),
        "parent_symptom_id": getattr(cond, "parent_symptom_id", None),
        "parent_symptom_code": getattr(cond, "parent_symptom_code", None),
        "parent_show_if_operator": getattr(cond, "parent_show_if_operator", None),
        "parent_show_if_value": getattr(cond, "parent_show_if_value", None),
        "parent_parent_symptom_code": getattr(cond, "parent_parent_symptom_code", None),
        "operator": (cond.operator or "==").upper(),
        "value": cond.value,
        "expected": expected,
        "actual": actual,
        "logic_group": (cond.logic_group or "").strip() or None,
        "is_required": bool(getattr(cond, "is_required", True)),
        "weight": float(getattr(cond, "weight", 1.0) or 0),
        "show_if_operator": getattr(cond, "show_if_operator", None),
        "show_if_value": getattr(cond, "show_if_value", None),
        "is_derived": bool(getattr(cond, "is_derived", False)),
    }


def _fact_value(cond, facts: Dict[Any, Any]) -> Tuple[bool, Any]:
    code = getattr(cond, "symptom_code", None)
    if code is not None and code in facts:
        return True, facts[code]
    sid = getattr(cond, "symptom_id", None)
    if sid is not None and sid in facts:
        return True, facts[sid]
    return False, None


def evaluate_condition(cond, facts: Dict[Any, Any]) -> Tuple[str, Dict[str, Any]]:
    found, actual = _fact_value(cond, facts)
    operator = (cond.operator or "==").upper()

    if operator == "PRESENT":
        if not found:
            return "MISSING", _condition_detail(cond, expected=True, actual=None)
        matched = actual is not None
        if isinstance(actual, bool):
            matched = actual is True
        return ("MATCHED" if matched else "CONTRADICTION"), _condition_detail(cond, expected=True, actual=actual)

    if operator == "ABSENT":
        if not found:
            return "MATCHED", _condition_detail(cond, expected=False, actual=None)
        matched = actual is None
        if isinstance(actual, bool):
            matched = actual is False
        return ("MATCHED" if matched else "CONTRADICTION"), _condition_detail(cond, expected=False, actual=actual)

    if not found:
        expected = cond.value
        if operator == "==":
            expected_bool = _parse_bool(cond.value)
            if expected_bool is not None:
                expected = expected_bool
        return "MISSING", _condition_detail(cond, expected=expected, actual=None)

    if operator == "==":
        if isinstance(actual, bool):
            expected = _parse_bool(cond.value)
            if expected is None:
                expected = True
        else:
            expected = _parse_numeric(cond.value)
            if expected is None:
                expected = cond.value
        matched = actual == expected
        return ("MATCHED" if matched else "CONTRADICTION"), _condition_detail(cond, expected, actual)

    if operator == "!=":
        if isinstance(actual, bool):
            expected = _parse_bool(cond.value)
            if expected is None:
                expected = True
        else:
            expected = _parse_numeric(cond.value)
            if expected is None:
                expected = cond.value
        matched = actual != expected
        return ("MATCHED" if matched else "CONTRADICTION"), _condition_detail(cond, expected, actual)

    if operator in {">", ">=", "<", "<="}:
        actual_num = _parse_numeric(actual)
        expected_num = _parse_numeric(cond.value)
        if actual_num is None or expected_num is None:
            return "CONTRADICTION", _condition_detail(cond, expected_num, actual)
        if operator == ">":
            matched = actual_num > expected_num
        elif operator == ">=":
            matched = actual_num >= expected_num
        elif operator == "<":
            matched = actual_num < expected_num
        else:
            matched = actual_num <= expected_num
        return ("MATCHED" if matched else "CONTRADICTION"), _condition_detail(cond, expected_num, actual_num)

    if operator == "IN":
        candidates = _parse_list(cond.value)
        matched = _in_list(actual, candidates)
        return ("MATCHED" if matched else "CONTRADICTION"), _condition_detail(cond, candidates, actual)

    return "CONTRADICTION", _condition_detail(cond, cond.value, actual)


def evaluate_rule_status(rule, facts: Dict[Any, Any]) -> Dict[str, Any]:
    if not rule.conditions:
        return {
            "status": "MATCHED",
            "matched": [],
            "missing": [],
            "contradictions": [],
            "matched_count": 0,
            "missing_count": 0,
            "contradiction_count": 0,
            "total_count": 0,
            "required_total_weight": 0.0,
            "required_matched_weight": 0.0,
            "optional_total_weight": 0.0,
            "optional_matched_weight": 0.0,
            "groups": [],
        }

    groups: Dict[str, List[Any]] = {}
    for cond in rule.conditions:
        group_key = (cond.logic_group or "").strip() or "DEFAULT"
        groups.setdefault(group_key, []).append(cond)

    group_results = []
    for group_key, conds in groups.items():
        matched, missing, contradictions = [], [], []
        matched_required, missing_required, contradictions_required = [], [], []
        matched_optional, missing_optional, contradictions_optional = [], [], []
        required_total_weight = 0.0
        required_matched_weight = 0.0
        optional_total_weight = 0.0
        optional_matched_weight = 0.0

        for cond in conds:
            status, detail = evaluate_condition(cond, facts)
            is_required = bool(detail.get("is_required", True))
            weight = float(detail.get("weight", 0) or 0)
            if is_required:
                required_total_weight += weight
            else:
                optional_total_weight += weight

            if status == "MATCHED":
                matched.append(detail)
                if is_required:
                    matched_required.append(detail)
                    required_matched_weight += weight
                else:
                    matched_optional.append(detail)
                    optional_matched_weight += weight
            elif status == "MISSING":
                missing.append(detail)
                if is_required:
                    missing_required.append(detail)
                else:
                    missing_optional.append(detail)
            else:
                contradictions.append(detail)
                if is_required:
                    contradictions_required.append(detail)
                else:
                    contradictions_optional.append(detail)

        if contradictions_required:
            status = "IMPOSSIBLE"
        elif missing_required:
            status = "POSSIBLE"
        else:
            if required_total_weight == 0 and not matched_optional and missing_optional:
                status = "POSSIBLE"
            else:
                status = "MATCHED"

        group_results.append({
            "group": None if group_key == "DEFAULT" else group_key,
            "status": status,
            "matched": matched,
            "missing": missing,
            "contradictions": contradictions,
            "matched_required": matched_required,
            "missing_required": missing_required,
            "contradictions_required": contradictions_required,
            "matched_optional": matched_optional,
            "missing_optional": missing_optional,
            "contradictions_optional": contradictions_optional,
            "matched_count": len(matched),
            "missing_count": len(missing),
            "contradiction_count": len(contradictions),
            "total_count": len(conds),
            "required_total_weight": required_total_weight,
            "required_matched_weight": required_matched_weight,
            "optional_total_weight": optional_total_weight,
            "optional_matched_weight": optional_matched_weight,
        })

    if any(gr["status"] == "MATCHED" for gr in group_results):
        overall_status = "MATCHED"
        candidates = [gr for gr in group_results if gr["status"] == "MATCHED"]
    elif any(gr["status"] == "POSSIBLE" for gr in group_results):
        overall_status = "POSSIBLE"
        candidates = [gr for gr in group_results if gr["status"] == "POSSIBLE"]
    else:
        overall_status = "IMPOSSIBLE"
        candidates = group_results

    def rank_key(gr):
        total = gr["total_count"] or 1
        progress = gr["matched_count"] / total
        return (progress, gr["matched_count"], -gr["missing_count"], -gr["contradiction_count"], gr["total_count"])

    best_group = max(candidates, key=rank_key) if candidates else {
        "matched": [],
        "missing": [],
        "contradictions": [],
        "matched_count": 0,
        "missing_count": 0,
        "contradiction_count": 0,
        "total_count": 0,
        "required_total_weight": 0.0,
        "required_matched_weight": 0.0,
        "optional_total_weight": 0.0,
        "optional_matched_weight": 0.0,
    }

    return {
        "status": overall_status,
        "matched": best_group["matched"],
        "missing": best_group["missing"],
        "contradictions": best_group["contradictions"],
        "matched_count": best_group["matched_count"],
        "missing_count": best_group["missing_count"],
        "contradiction_count": best_group["contradiction_count"],
        "total_count": best_group["total_count"],
        "required_total_weight": best_group.get("required_total_weight", 0.0),
        "required_matched_weight": best_group.get("required_matched_weight", 0.0),
        "optional_total_weight": best_group.get("optional_total_weight", 0.0),
        "optional_matched_weight": best_group.get("optional_matched_weight", 0.0),
        "groups": group_results,
    }


def is_urgent_rule(rule) -> bool:
    risk_level = (getattr(rule, "risk_level", "") or "").upper()
    diagnosis_code = (getattr(rule, "diagnosis_code", "") or "").upper()
    return risk_level in {"VERY_HIGH", "CRITICAL", "DANGER"} or "CRITICAL" in diagnosis_code or "DANGER" in diagnosis_code


def score_rule(rule, matched_count: int, total_count: int, urgency_flag: bool = False) -> float:
    confidence = getattr(rule, "confidence", None)
    confidence = float(confidence) if confidence is not None else 0.0
    total = total_count or 1
    coverage = matched_count / total

    score = (confidence * 1.0) + (coverage * 20.0) + (getattr(rule, "priority", 0) * 0.01)
    if urgency_flag:
        score += 10.0
    return round(score, 4)
