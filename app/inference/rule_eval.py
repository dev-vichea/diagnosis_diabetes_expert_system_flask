import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

COND_MATCH = "MATCH"
COND_NO_MATCH = "NO_MATCH"
COND_UNKNOWN = "UNKNOWN"

RULE_MATCH = "match"
RULE_NO_MATCH = "no_match"
RULE_UNKNOWN = "unknown"

_OPERATOR_ALIASES = {
    "EQ": "EQ",
    "==": "EQ",
    "NEQ": "NEQ",
    "!=": "NEQ",
    "GT": "GT",
    ">": "GT",
    "GTE": "GTE",
    ">=": "GTE",
    "LT": "LT",
    "<": "LT",
    "LTE": "LTE",
    "<=": "LTE",
    "BETWEEN": "BETWEEN",
    "IN": "IN",
    "PRESENT": "PRESENT",
    "ABSENT": "ABSENT",
}


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


@dataclass
class ConditionEval:
    state: str
    detail: Dict[str, Any]


@dataclass
class RuleEval:
    matched_state: str
    score_added: int
    missing_findings: List[str]
    matched_required_count: int
    total_required_count: int
    matched_conditions: List[Dict[str, Any]]
    explain_text: str
    unknown_conditions: List[Dict[str, Any]] = field(default_factory=list)
    no_match_conditions: List[Dict[str, Any]] = field(default_factory=list)
    matched_total_count: int = 0
    total_conditions: int = 0
    required_total_weight: float = 0.0
    required_matched_weight: float = 0.0
    optional_total_weight: float = 0.0
    optional_matched_weight: float = 0.0
    confidence_added: float = 0.0


def _normalize_operator(raw: Optional[str]) -> str:
    key = str(raw or "EQ").strip().upper()
    return _OPERATOR_ALIASES.get(key, key)


def _condition_expected_value(cond) -> Any:
    if hasattr(cond, "values") and getattr(cond, "values") is not None:
        return getattr(cond, "values")
    return getattr(cond, "value", None)


def _coerce_score_points(cond) -> int:
    raw = getattr(cond, "score_points", 0)
    try:
        return int(raw or 0)
    except Exception:
        return 0


def _coerce_weight(cond) -> float:
    raw = getattr(cond, "weight", 1.0)
    try:
        return float(raw if raw is not None else 1.0)
    except Exception:
        return 1.0


def _is_unknown_bool(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"unknown", "unk", "none", ""}
    return False


def _extract_fact_meta(raw: Any) -> Tuple[Any, Optional[str], Optional[bool]]:
    if not isinstance(raw, dict):
        return raw, None, None

    state = raw.get("state")
    state = str(state).strip().lower() if state is not None else None

    value = raw.get("value")
    if value is None:
        for key in ("value_bool", "value_number", "value_text", "value_json"):
            if key in raw and raw.get(key) is not None:
                value = raw.get(key)
                break

    is_provided = raw.get("is_provided")
    if isinstance(is_provided, str):
        lowered = is_provided.strip().lower()
        if lowered in {"true", "1", "yes"}:
            is_provided = True
        elif lowered in {"false", "0", "no"}:
            is_provided = False
        else:
            is_provided = None
    elif not isinstance(is_provided, bool):
        is_provided = None

    return value, state, is_provided


def _condition_detail(cond, expected: Any = None, actual: Any = None) -> Dict[str, Any]:
    finding_code = getattr(cond, "finding_code", None) or getattr(cond, "symptom_code", None)
    return {
        "symptom_id": getattr(cond, "symptom_id", None),
        "symptom_code": getattr(cond, "symptom_code", None),
        "finding_code": finding_code,
        "parent_symptom_id": getattr(cond, "parent_symptom_id", None),
        "parent_symptom_code": getattr(cond, "parent_symptom_code", None),
        "parent_show_if_operator": getattr(cond, "parent_show_if_operator", None),
        "parent_show_if_value": getattr(cond, "parent_show_if_value", None),
        "parent_parent_symptom_code": getattr(cond, "parent_parent_symptom_code", None),
        "operator": _normalize_operator(getattr(cond, "operator", "==")),
        "value": _condition_expected_value(cond),
        "expected": expected,
        "actual": actual,
        "logic_group": (cond.logic_group or "").strip() or None,
        "is_required": bool(getattr(cond, "is_required", True)),
        "weight": _coerce_weight(cond),
        "score_points": _coerce_score_points(cond),
        "negate": bool(getattr(cond, "negate", False)),
        "input_type": (getattr(cond, "input_type", None) or "").upper() or None,
        "show_if_operator": getattr(cond, "show_if_operator", None),
        "show_if_value": getattr(cond, "show_if_value", None),
        "is_derived": bool(getattr(cond, "is_derived", False)),
    }


def _fact_value(cond, facts: Dict[Any, Any]) -> Tuple[bool, Any]:
    code = getattr(cond, "finding_code", None)
    if code is not None and code in facts:
        return True, facts[code]
    code = getattr(cond, "symptom_code", None)
    if code is not None and code in facts:
        return True, facts[code]
    sid = getattr(cond, "symptom_id", None)
    if sid is not None and sid in facts:
        return True, facts[sid]
    return False, None


def eval_condition(cond, facts: Dict[Any, Any]) -> ConditionEval:
    found, actual = _fact_value(cond, facts)
    operator = _normalize_operator(getattr(cond, "operator", "EQ"))
    expected_raw = _condition_expected_value(cond)
    if isinstance(expected_raw, list) and operator not in {"BETWEEN", "IN"}:
        expected_raw = expected_raw[0] if expected_raw else None
    detail = _condition_detail(cond, expected=expected_raw, actual=None)

    if not found:
        detail["actual"] = None
        return ConditionEval(COND_UNKNOWN, detail)

    raw_value, state, is_provided = _extract_fact_meta(actual)
    input_type = str(getattr(cond, "input_type", "") or "").strip().upper()
    unknown = False

    if state == "unknown":
        unknown = True
    elif input_type == "BOOLEAN":
        unknown = _is_unknown_bool(raw_value) or _parse_bool(raw_value) is None
    elif input_type == "NUMBER":
        unknown = (is_provided is False) or (raw_value is None) or (_parse_numeric(raw_value) is None)
    else:
        unknown = (is_provided is False) or (raw_value is None)

    if operator == "PRESENT":
        if unknown:
            return ConditionEval(COND_UNKNOWN, _condition_detail(cond, expected=True, actual=None))
        result_state = COND_MATCH
        if bool(getattr(cond, "negate", False)):
            result_state = COND_NO_MATCH
        return ConditionEval(result_state, _condition_detail(cond, expected=True, actual=raw_value))

    if operator == "ABSENT":
        if unknown:
            return ConditionEval(COND_UNKNOWN, _condition_detail(cond, expected=False, actual=None))
        if isinstance(raw_value, bool):
            matched = raw_value is False
        else:
            matched = raw_value in {"", [], {}}
        if bool(getattr(cond, "negate", False)):
            matched = not matched
        return ConditionEval(
            COND_MATCH if matched else COND_NO_MATCH,
            _condition_detail(cond, expected=False, actual=raw_value),
        )

    if unknown:
        return ConditionEval(COND_UNKNOWN, _condition_detail(cond, expected=expected_raw, actual=None))

    actual_value: Any = raw_value
    matched = False

    if operator == "EQ":
        if isinstance(raw_value, bool):
            expected = _parse_bool(expected_raw)
            if expected is None:
                expected = raw_value
            actual_value = bool(raw_value)
            matched = actual_value == expected
            detail = _condition_detail(cond, expected=expected, actual=actual_value)
        else:
            actual_num = _parse_numeric(raw_value)
            expected_num = _parse_numeric(expected_raw)
            if actual_num is not None and expected_num is not None:
                matched = actual_num == expected_num
                detail = _condition_detail(cond, expected=expected_num, actual=actual_num)
            else:
                matched = str(raw_value).strip().lower() == str(expected_raw).strip().lower()
                detail = _condition_detail(cond, expected=expected_raw, actual=raw_value)
    elif operator == "NEQ":
        if isinstance(raw_value, bool):
            expected = _parse_bool(expected_raw)
            if expected is None:
                expected = raw_value
            actual_value = bool(raw_value)
            matched = actual_value != expected
            detail = _condition_detail(cond, expected=expected, actual=actual_value)
        else:
            actual_num = _parse_numeric(raw_value)
            expected_num = _parse_numeric(expected_raw)
            if actual_num is not None and expected_num is not None:
                matched = actual_num != expected_num
                detail = _condition_detail(cond, expected=expected_num, actual=actual_num)
            else:
                matched = str(raw_value).strip().lower() != str(expected_raw).strip().lower()
                detail = _condition_detail(cond, expected=expected_raw, actual=raw_value)
    elif operator in {"GT", "GTE", "LT", "LTE"}:
        actual_num = _parse_numeric(raw_value)
        expected_num = _parse_numeric(expected_raw)
        if actual_num is None or expected_num is None:
            return ConditionEval(COND_NO_MATCH, _condition_detail(cond, expected=expected_raw, actual=raw_value))
        if operator == "GT":
            matched = actual_num > expected_num
        elif operator == "GTE":
            matched = actual_num >= expected_num
        elif operator == "LT":
            matched = actual_num < expected_num
        else:
            matched = actual_num <= expected_num
        detail = _condition_detail(cond, expected=expected_num, actual=actual_num)
    elif operator == "BETWEEN":
        bounds = _parse_list(expected_raw)
        if len(bounds) < 2:
            return ConditionEval(COND_NO_MATCH, _condition_detail(cond, expected=bounds, actual=raw_value))
        low = _parse_numeric(bounds[0])
        high = _parse_numeric(bounds[1])
        actual_num = _parse_numeric(raw_value)
        if low is None or high is None or actual_num is None:
            return ConditionEval(COND_NO_MATCH, _condition_detail(cond, expected=bounds[:2], actual=raw_value))
        matched = low <= actual_num <= high
        detail = _condition_detail(cond, expected=[low, high], actual=actual_num)
    elif operator == "IN":
        candidates = _parse_list(expected_raw)
        matched = _in_list(raw_value, candidates)
        detail = _condition_detail(cond, expected=candidates, actual=raw_value)
    else:
        return ConditionEval(COND_NO_MATCH, _condition_detail(cond, expected=expected_raw, actual=raw_value))

    if bool(getattr(cond, "negate", False)):
        matched = not matched

    return ConditionEval(COND_MATCH if matched else COND_NO_MATCH, detail)


def evaluate_condition(cond, facts: Dict[Any, Any]) -> Tuple[str, Dict[str, Any]]:
    evaluated = eval_condition(cond, facts)
    if evaluated.state == COND_MATCH:
        return "MATCHED", evaluated.detail
    if evaluated.state == COND_UNKNOWN:
        return "MISSING", evaluated.detail
    return "CONTRADICTION", evaluated.detail


def _safe_min_required(rule, total_conditions: int, default: int) -> int:
    raw = getattr(rule, "min_required_matches", None)
    if raw is None:
        return max(0, min(default, total_conditions))
    try:
        parsed = int(raw)
    except Exception:
        parsed = default
    if parsed < 0:
        parsed = 0
    return min(parsed, total_conditions)


def _rule_type(rule) -> str:
    return str(getattr(rule, "rule_type", "screening") or "screening").strip().lower()


def _legacy_status_from_rule_state(matched_state: str) -> str:
    if matched_state == RULE_MATCH:
        return "MATCHED"
    if matched_state == RULE_UNKNOWN:
        return "POSSIBLE"
    return "IMPOSSIBLE"


def build_explanation(rule, result: RuleEval) -> str:
    rule_label = getattr(rule, "name", None) or getattr(rule, "title", None) or f"rule:{getattr(rule, 'id', 'unknown')}"
    required_text = f"{result.matched_required_count}/{result.total_required_count} required"
    condition_text = f"{result.matched_total_count}/{result.total_conditions} conditions"
    if result.matched_state == RULE_MATCH:
        reason = "matched"
    elif result.matched_state == RULE_UNKNOWN:
        reason = "insufficient evidence"
    else:
        reason = "did not match"

    missing_text = ""
    if result.missing_findings:
        missing_text = f"; missing={','.join(result.missing_findings)}"
    return f"{rule_label} [{_rule_type(rule)}] {reason} ({required_text}, {condition_text}){missing_text}"


def eval_rule(rule, facts: Dict[Any, Any]) -> RuleEval:
    conditions = list(getattr(rule, "conditions", []) or [])
    if not conditions:
        result = RuleEval(
            matched_state=RULE_MATCH,
            score_added=0,
            missing_findings=[],
            matched_required_count=0,
            total_required_count=0,
            matched_conditions=[],
            explain_text="Rule has no conditions.",
            matched_total_count=0,
            total_conditions=0,
        )
        return result

    matched_conditions: List[Dict[str, Any]] = []
    unknown_conditions: List[Dict[str, Any]] = []
    no_match_conditions: List[Dict[str, Any]] = []

    required_total = 0
    matched_required = 0
    required_unknown = 0
    required_no_match = 0

    required_total_weight = 0.0
    required_matched_weight = 0.0
    optional_total_weight = 0.0
    optional_matched_weight = 0.0

    matched_score_sum = 0
    missing_findings: List[str] = []

    for cond in conditions:
        evaluation = eval_condition(cond, facts)
        detail = dict(evaluation.detail)
        is_required = bool(detail.get("is_required", True))
        weight = float(detail.get("weight") or 0.0)

        if is_required:
            required_total += 1
            required_total_weight += weight
        else:
            optional_total_weight += weight

        if evaluation.state == COND_MATCH:
            matched_conditions.append(detail)
            matched_score_sum += int(detail.get("score_points") or 0)
            if is_required:
                matched_required += 1
                required_matched_weight += weight
            else:
                optional_matched_weight += weight
        elif evaluation.state == COND_UNKNOWN:
            unknown_conditions.append(detail)
            code = detail.get("finding_code") or detail.get("symptom_code")
            if code:
                missing_findings.append(str(code))
            if is_required:
                required_unknown += 1
        else:
            no_match_conditions.append(detail)
            if is_required:
                required_no_match += 1

    matched_total = len(matched_conditions)
    total_conditions = len(conditions)
    unknown_count = len(unknown_conditions)
    optional_total_count = max(0, total_conditions - required_total)
    matched_optional_count = max(0, matched_total - matched_required)
    rule_type = _rule_type(rule)

    default_k = required_total if required_total > 0 else total_conditions
    k_threshold = _safe_min_required(rule, total_conditions, default_k)
    if k_threshold == 0 and total_conditions > 0:
        k_threshold = 1

    if rule_type == "screening":
        if required_no_match > 0:
            matched_state = RULE_NO_MATCH
        elif matched_total >= k_threshold:
            matched_state = RULE_MATCH
        elif unknown_count > 0:
            matched_state = RULE_UNKNOWN
        else:
            matched_state = RULE_NO_MATCH
        score_added = matched_score_sum
    elif rule_type == "diagnostic":
        if required_no_match > 0:
            matched_state = RULE_NO_MATCH
        elif required_unknown > 0:
            matched_state = RULE_UNKNOWN
        else:
            all_required_matched = (matched_required == required_total) if required_total > 0 else True
            if not all_required_matched:
                matched_state = RULE_NO_MATCH
            else:
                if optional_total_count > 0:
                    optional_k = _safe_min_required(rule, optional_total_count, default=0)
                    if matched_optional_count >= optional_k:
                        matched_state = RULE_MATCH
                    else:
                        matched_state = RULE_NO_MATCH
                elif matched_total >= k_threshold:
                    matched_state = RULE_MATCH
                else:
                    matched_state = RULE_NO_MATCH
        score_added = matched_score_sum if matched_state == RULE_MATCH else 0
    elif rule_type == "exclusion":
        if required_no_match > 0:
            matched_state = RULE_NO_MATCH
        elif required_unknown > 0:
            matched_state = RULE_UNKNOWN
        else:
            all_required_matched = (matched_required == required_total) if required_total > 0 else matched_total > 0
            if all_required_matched and matched_total >= max(1, min(k_threshold, total_conditions)):
                matched_state = RULE_MATCH
            elif unknown_count > 0:
                matched_state = RULE_UNKNOWN
            else:
                matched_state = RULE_NO_MATCH

        penalty = abs(matched_score_sum) if matched_score_sum != 0 else 0
        score_added = (-penalty) if matched_state == RULE_MATCH else 0
    else:
        if required_no_match > 0:
            matched_state = RULE_NO_MATCH
        elif matched_total >= k_threshold:
            matched_state = RULE_MATCH
        elif unknown_count > 0:
            matched_state = RULE_UNKNOWN
        else:
            matched_state = RULE_NO_MATCH
        score_added = matched_score_sum

    result = RuleEval(
        matched_state=matched_state,
        score_added=score_added,
        missing_findings=sorted(set(missing_findings)),
        matched_required_count=matched_required,
        total_required_count=required_total,
        matched_conditions=matched_conditions,
        unknown_conditions=unknown_conditions,
        no_match_conditions=no_match_conditions,
        explain_text="",
        matched_total_count=matched_total,
        total_conditions=total_conditions,
        required_total_weight=required_total_weight,
        required_matched_weight=required_matched_weight,
        optional_total_weight=optional_total_weight,
        optional_matched_weight=optional_matched_weight,
        confidence_added=0.0,
    )
    result.explain_text = build_explanation(rule, result)
    return result


def apply_rule_to_disease(disease_state: Dict[str, Any], rule, result: RuleEval) -> Dict[str, Any]:
    state = dict(disease_state or {})
    state.setdefault("score_total", 0)
    state.setdefault("blocked", False)
    state.setdefault("confirmed_by_rule_id", None)
    state.setdefault("status", None)
    state.setdefault("missing_key_facts", [])
    state.setdefault("top_evidence", [])

    if result.matched_state == RULE_MATCH:
        rule_type = _rule_type(rule)
        if rule_type == "exclusion":
            state["blocked"] = True
            state["score_total"] += int(result.score_added)
        elif rule_type == "diagnostic":
            state["confirmed_by_rule_id"] = getattr(rule, "id", None)
            state["status"] = "confirmed"
            state["score_total"] += int(result.score_added)
        else:
            state["score_total"] += int(result.score_added)

        state["top_evidence"].append(
            {
                "rule_id": getattr(rule, "id", None),
                "rule_type": rule_type,
                "score_added": int(result.score_added),
                "matched_conditions": result.matched_conditions,
            }
        )
    elif result.matched_state == RULE_UNKNOWN:
        merged = set(str(x) for x in (state.get("missing_key_facts") or []))
        merged.update(result.missing_findings)
        state["missing_key_facts"] = sorted(merged)

    return state


def evaluate_rule_status(rule, facts: Dict[Any, Any]) -> Dict[str, Any]:
    evaluated = eval_rule(rule, facts)
    status = _legacy_status_from_rule_state(evaluated.matched_state)
    group_result = {
        "group": None,
        "status": status,
        "matched": evaluated.matched_conditions,
        "missing": evaluated.unknown_conditions,
        "contradictions": evaluated.no_match_conditions,
        "matched_required": [c for c in evaluated.matched_conditions if c.get("is_required", True)],
        "missing_required": [c for c in evaluated.unknown_conditions if c.get("is_required", True)],
        "contradictions_required": [c for c in evaluated.no_match_conditions if c.get("is_required", True)],
        "matched_optional": [c for c in evaluated.matched_conditions if not c.get("is_required", True)],
        "missing_optional": [c for c in evaluated.unknown_conditions if not c.get("is_required", True)],
        "contradictions_optional": [c for c in evaluated.no_match_conditions if not c.get("is_required", True)],
        "matched_count": len(evaluated.matched_conditions),
        "missing_count": len(evaluated.unknown_conditions),
        "contradiction_count": len(evaluated.no_match_conditions),
        "total_count": evaluated.total_conditions,
        "required_total_weight": evaluated.required_total_weight,
        "required_matched_weight": evaluated.required_matched_weight,
        "optional_total_weight": evaluated.optional_total_weight,
        "optional_matched_weight": evaluated.optional_matched_weight,
    }

    payload = asdict(evaluated)
    payload.update(
        {
            "status": status,
            "matched": evaluated.matched_conditions,
            "missing": evaluated.unknown_conditions,
            "contradictions": evaluated.no_match_conditions,
            "matched_count": len(evaluated.matched_conditions),
            "missing_count": len(evaluated.unknown_conditions),
            "contradiction_count": len(evaluated.no_match_conditions),
            "total_count": evaluated.total_conditions,
            "required_total_weight": evaluated.required_total_weight,
            "required_matched_weight": evaluated.required_matched_weight,
            "optional_total_weight": evaluated.optional_total_weight,
            "optional_matched_weight": evaluated.optional_matched_weight,
            "groups": [group_result],
        }
    )
    return payload


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
