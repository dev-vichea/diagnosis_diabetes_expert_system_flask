from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.inference.rule_eval import evaluate_rule_status


@dataclass
class Condition:
    symptom_id: int
    symptom_code: Optional[str] = None
    finding_code: Optional[str] = None
    operator: str = "=="
    value: Optional[Any] = None
    values: Optional[Any] = None
    logic_group: Optional[str] = None
    is_required: bool = True
    weight: float = 1.0
    score_points: int = 0
    negate: bool = False
    input_type: Optional[str] = None
    parent_symptom_id: Optional[int] = None
    parent_symptom_code: Optional[str] = None
    parent_show_if_operator: Optional[str] = None
    parent_show_if_value: Optional[str] = None
    parent_parent_symptom_code: Optional[str] = None
    show_if_operator: Optional[str] = None
    show_if_value: Optional[str] = None
    is_derived: bool = False


@dataclass
class RulePayload:
    id: int
    name: str
    diagnosis_code: str
    risk_level: str
    rule_type: str = "screening"
    stop_on_match: bool = False
    confidence_cap_if_unconfirmed: Optional[float] = None
    confidence_bonus_max: Optional[float] = None
    min_required_matches: Optional[int] = None
    priority: int = 0
    confidence: Optional[float] = None
    conditions: List[Condition] = field(default_factory=list)


def _safe_confidence(confidence: Optional[float]) -> float:
    if confidence is None:
        return 0.5
    try:
        confidence = float(confidence)
    except Exception:
        return 0.5
    if confidence > 1.0:
        confidence = confidence / 100.0
    return max(0.0, min(1.0, confidence))


def _score_rule(rule: RulePayload, status: str, matched: list, missing: list) -> float:
    conf = _safe_confidence(rule.confidence)
    required_total = sum(float(getattr(c, "weight", 1.0) or 0) for c in rule.conditions if getattr(c, "is_required", True))
    optional_total = sum(float(getattr(c, "weight", 1.0) or 0) for c in rule.conditions if not getattr(c, "is_required", True))

    matched_required = sum(
        float(item.get("weight") or 0)
        for item in matched
        if item.get("is_required", True)
    )
    matched_optional = sum(
        float(item.get("weight") or 0)
        for item in matched
        if not item.get("is_required", True)
    )

    if required_total > 0:
        required_progress = matched_required / required_total
    else:
        required_progress = 1.0 if status == "MATCHED" else 0.0

    if optional_total > 0:
        optional_ratio = matched_optional / optional_total
    else:
        optional_ratio = 1.0 if status == "MATCHED" else 0.0

    score = 0.0
    score += required_progress * 100.0
    score += optional_ratio * 50.0
    score += conf * 10.0
    score += float(rule.priority or 0) * 1.0
    score += (1.0 / (1.0 + float(rule.id))) * 0.001
    return round(score, 4)


def _safe_optional_fraction(value: Optional[float], default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        value = float(value)
    except Exception:
        return default
    if value > 1.0:
        value = value / 100.0
    return max(0.0, min(1.0, value))


def _estimated_confidence(rule: RulePayload, status: str, eval_meta: Dict[str, Any], matched: list) -> float:
    base = _safe_confidence(rule.confidence)
    optional_total = float(eval_meta.get("optional_total_weight", 0.0) or 0.0)
    optional_matched = float(eval_meta.get("optional_matched_weight", 0.0) or 0.0)
    optional_ratio = (optional_matched / optional_total) if optional_total > 0 else 0.0

    bonus_max = _safe_optional_fraction(rule.confidence_bonus_max, default=0.0)
    est = base + (optional_ratio * bonus_max)
    est = max(0.0, min(1.0, est))

    # For unconfirmed screening results, cap confidence if policy is configured.
    if status != "MATCHED" and (rule.rule_type or "screening").lower() == "screening":
        cap = _safe_optional_fraction(rule.confidence_cap_if_unconfirmed, default=1.0)
        est = min(est, cap)

    return est


def _evidence_level(optional_matched: float, optional_total: float, status: str) -> str:
    if optional_total <= 0:
        return "strong" if status == "MATCHED" else "weak"
    ratio = optional_matched / optional_total if optional_total else 0.0
    if ratio >= 0.7:
        return "strong"
    if ratio >= 0.4:
        return "moderate"
    return "weak"


def _build_eval_row(rule: RulePayload, status: str, matched: list, missing: list, eval_meta: Dict[str, Any]) -> Dict[str, Any]:
    optional_total = float(eval_meta.get("optional_total_weight", 0.0) or 0)
    optional_matched = float(eval_meta.get("optional_matched_weight", 0.0) or 0)
    required_total = float(eval_meta.get("required_total_weight", 0.0) or 0)
    required_matched = float(eval_meta.get("required_matched_weight", 0.0) or 0)

    evidence_details = [
        item for item in matched
        if not item.get("is_required", True) and float(item.get("weight") or 0) > 0
    ]
    est_confidence = _estimated_confidence(rule, status, eval_meta, matched)

    score_added = float(eval_meta.get("score_added", 0) or 0)
    base_score = _score_rule(rule, status, matched, missing)
    final_score = round(base_score + score_added, 4)

    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "priority": rule.priority,
        "rule_type": (rule.rule_type or "screening"),
        "stop_on_match": bool(rule.stop_on_match),
        "diagnosis_code": rule.diagnosis_code,
        "risk_level": rule.risk_level,
        "confidence": est_confidence,
        "base_confidence": _safe_confidence(rule.confidence),
        "confidence_cap_if_unconfirmed": _safe_optional_fraction(rule.confidence_cap_if_unconfirmed, default=1.0),
        "confidence_bonus_max": _safe_optional_fraction(rule.confidence_bonus_max, default=0.0),
        "min_required_matches": rule.min_required_matches,
        "status": status,
        "matched_state": eval_meta.get("matched_state"),
        "score_added": score_added,
        "missing_findings": eval_meta.get("missing_findings") or [],
        "matched_required_count": int(eval_meta.get("matched_required_count") or 0),
        "total_required_count": int(eval_meta.get("total_required_count") or 0),
        "explain_text": eval_meta.get("explain_text"),
        "matched_count": len(matched),
        "total_conditions": len(rule.conditions),
        "matched_conditions": matched,
        "missing_conditions": missing,
        "required_total_weight": required_total,
        "required_matched_weight": required_matched,
        "optional_total_weight": optional_total,
        "optional_matched_weight": optional_matched,
        "evidence_level": _evidence_level(optional_matched, optional_total, status),
        "evidence_details": evidence_details,
        "est_confidence": round(est_confidence * 100.0, 1),
        "score": final_score,
    }


def _trigger_ok(parent_code: Optional[str], operator: Optional[str], expected: Any, facts: Dict[str, Any]) -> bool:
    if not parent_code:
        return True
    if parent_code not in facts:
        return False
    actual = facts.get(parent_code)
    operator = (operator or "==").upper()
    if isinstance(actual, bool) and expected is None:
        expected = True
    if isinstance(expected, str) and expected.lower() in {"true", "false"}:
        expected = expected.lower() == "true"
    if isinstance(expected, str) and expected.strip() in {"1", "0"}:
        expected = expected.strip() == "1"

    if operator == "PRESENT":
        if actual is None:
            return False
        if isinstance(actual, bool):
            return actual is True
        return True

    if operator == "ABSENT":
        if actual is None:
            return True
        if isinstance(actual, bool):
            return actual is False
        return False

    if operator == "==":
        return actual == expected
    if operator == "!=":
        return actual != expected
    try:
        actual_num = float(actual)
        expected_num = float(expected)
    except (TypeError, ValueError):
        actual_num = None
        expected_num = None
    if operator == ">":
        return actual_num is not None and expected_num is not None and actual_num > expected_num
    if operator == ">=":
        return actual_num is not None and expected_num is not None and actual_num >= expected_num
    if operator == "<":
        return actual_num is not None and expected_num is not None and actual_num < expected_num
    if operator == "<=":
        return actual_num is not None and expected_num is not None and actual_num <= expected_num
    return False


def _trigger_satisfied(item: Dict[str, Any], facts: Dict[str, Any]) -> bool:
    return _trigger_ok(
        item.get("parent_symptom_code"),
        item.get("show_if_operator"),
        item.get("show_if_value"),
        facts,
    )


def _next_best_question_ids(rows: List[Dict[str, Any]], facts: Dict[str, Any], limit: int = 5) -> List[int]:
    weighted = {}
    for row in rows:
        for item in row.get("missing_conditions", []):
            sid = item.get("symptom_id")
            if sid is None:
                continue
            ask_id = sid
            if item.get("is_derived") and item.get("parent_symptom_id"):
                ask_id = item.get("parent_symptom_id")
            if ask_id is None:
                continue
            ask_code = item.get("symptom_code") if ask_id == sid else item.get("parent_symptom_code")
            if ask_code and ask_code in facts:
                continue
            if ask_id == sid:
                if not _trigger_satisfied(item, facts):
                    continue
            else:
                if not _trigger_ok(
                    item.get("parent_parent_symptom_code"),
                    item.get("parent_show_if_operator"),
                    item.get("parent_show_if_value"),
                    facts,
                ):
                    continue
            weight = float(item.get("weight") or 0)
            weighted[ask_id] = weighted.get(ask_id, 0.0) + weight

    if not weighted:
        return []

    ordered = sorted(weighted.items(), key=lambda x: (-x[1], x[0]))
    return [sid for sid, _ in ordered[:limit]]


def run_inference(facts: Dict[str, Any], rules: List[RulePayload]) -> Dict[str, Any]:
    evaluated = []
    for rule in rules:
        eval_result = evaluate_rule_status(rule, facts)
        status = eval_result.get("status", "IMPOSSIBLE")
        matched = eval_result.get("matched", [])
        missing = eval_result.get("missing", [])
        row = _build_eval_row(rule, status, matched, missing, eval_result)
        evaluated.append(row)
        if row["status"] == "MATCHED" and row.get("stop_on_match"):
            break

    matched_rows = [row for row in evaluated if row["status"] == "MATCHED"]
    stop_rows = [row for row in matched_rows if row.get("stop_on_match")]
    if stop_rows:
        best_row = max(stop_rows, key=lambda x: x["score"])
    else:
        best_row = max(matched_rows, key=lambda x: x["score"]) if matched_rows else None

    finalizable = False
    if best_row and best_row.get("stop_on_match"):
        finalizable = True
    elif best_row:
        for row in evaluated:
            if row["priority"] > best_row["priority"] and row["status"] == "POSSIBLE":
                finalizable = False
                break
        else:
            for row in evaluated:
                if row["priority"] == best_row["priority"] and row["status"] == "POSSIBLE":
                    if row["score"] >= best_row["score"]:
                        break
            else:
                finalizable = True

    candidates = [row for row in evaluated if row["status"] in ("MATCHED", "POSSIBLE")]
    candidates_sorted = sorted(candidates, key=lambda x: x["score"], reverse=True)
    top3 = candidates_sorted[:3]

    next_best_question_ids = _next_best_question_ids(top3, facts)

    return {
        "evaluated": evaluated,
        "top_candidates": top3,
        "best_row": best_row,
        "finalizable": finalizable,
        "next_best_question_ids": next_best_question_ids,
    }
